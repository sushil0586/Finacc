from django.db import transaction
from rest_framework import serializers
from inventory.models import Product, Album, Track, ProductCategory, Ratecalculate, UnitofMeasurement, typeofgoods, gsttype, HsnCode,BillOfMaterial, BOMItem,ProductionOrder, ProductionConsumption
from invoice.models import entry, StockTransactions
from financial.models import account
from entity.models import entityfinancialyear


class ProductCategoryMainSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ('id', 'pcategoryname', 'maincategory', 'entity',)

    def create(self, validated_data):
        # Limit to 8 categories where entity is null
        # if ProductCategory.objects.filter(entity__isnull=True).count() > 8:
        #     raise serializers.ValidationError("Maximum category limit reached.")
        
        return ProductCategory.objects.create(**validated_data)


class ProductCategorySerializer(serializers.ModelSerializer):
    maincategoryname = serializers.SerializerMethodField()

    class Meta:
        model = ProductCategory
        fields = ('id', 'pcategoryname', 'maincategory', 'entity', 'maincategoryname',)

    def get_maincategoryname(self, obj):
        return obj.maincategory.pcategoryname if obj.maincategory else 'null'


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'

    def create(self, validated_data):
        with transaction.atomic():  # Start transaction block
            product = Product.objects.create(**validated_data)

            # Fetch associated account and entry data
            os = account.objects.get(entity=product.entity, accountcode=9000)
            accountdate1 = entityfinancialyear.objects.get(entity=product.entity,isactive = True).finstartyear

            
            entryid, _ = entry.objects.get_or_create(entrydate1=accountdate1, entity=product.entity)

            if product.openingstockvalue and (product.openingstockqty or product.openingstockboxqty):
                qty = product.openingstockqty or product.openingstockboxqty
                StockTransactions.objects.create(
                    accounthead=os.accounthead, account=os, stock=product, transactiontype='O', 
                    transactionid=product.id, desc=f'Opening Stock {product.productname}', stockttype='R', 
                    quantity=qty, drcr=1, debitamount=product.openingstockvalue, entrydate=accountdate1, 
                    entity=product.entity, createdby=product.createdby, entry=entryid, entrydatetime=accountdate1, 
                    accounttype='DD', isactive=True, rate=product.purchaserate
                )

            return product


class TrackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Track
        fields = ('id', 'order', 'title', 'duration',)


class RateCalculateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ratecalculate
        fields = ('id', 'rname', 'rcode',)


class UOMSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitofMeasurement
        fields = ('id', 'unitname', 'unitcode',)


class TOGSerializer(serializers.ModelSerializer):
    class Meta:
        model = typeofgoods
        fields = ('id', 'goodstype', 'goodscode',)


class GSTSerializer(serializers.ModelSerializer):
    class Meta:
        model = gsttype
        fields = ('id', 'gsttypename', 'gsttypecode',)


class HSNSerializer(serializers.ModelSerializer):
    class Meta:
        model = HsnCode
        fields = ('id', 'hsnCode', 'Hsndescription',)


class AlbumSerializer(serializers.ModelSerializer):
    tracks = TrackSerializer(many=True)

    class Meta:
        model = Album
        fields = ['id', 'album_name', 'artist', 'tracks']

    def create(self, validated_data):
        with transaction.atomic():  # Start transaction block
            tracks_data = validated_data.pop('tracks')
            album = Album.objects.create(**validated_data)

            # Bulk create tracks associated with this album
            Track.objects.bulk_create([Track(album=album, **track_data) for track_data in tracks_data])

            return album

    def update(self, instance, validated_data):
        with transaction.atomic():  # Start transaction block
            instance.album_name = validated_data.get('album_name', instance.album_name)
            instance.artist = validated_data.get('artist', instance.artist)
            instance.save()

            # Handle updating or creating tracks
            tracks = validated_data.get('tracks', [])
            track_ids = {track['id'] for track in tracks if 'id' in track}

            existing_tracks = {track.id: track for track in instance.tracks.all()}
            new_tracks = []

            for track_data in tracks:
                track_id = track_data.get('id')
                if track_id and track_id in existing_tracks:
                    track = existing_tracks[track_id]
                    track.order = track_data.get('order', track.order)
                    track.title = track_data.get('title', track.title)
                    track.duration = track_data.get('duration', track.duration)
                    track.save()
                else:
                    new_tracks.append(Track(album=instance, **track_data))

            # Bulk create new tracks
            if new_tracks:
                Track.objects.bulk_create(new_tracks)

            # Delete tracks that no longer exist in the incoming data
            track_ids_to_delete = set(existing_tracks.keys()) - track_ids
            if track_ids_to_delete:
                instance.tracks.filter(id__in=track_ids_to_delete).delete()

            return instance
        

# Serializer for Product model
class ProductListSerializer(serializers.ModelSerializer):
    hsn = serializers.CharField(source='hsn.hsnCode', read_only=True)
    class Meta:
        model = Product
        fields = [
            'id', 'productname', 'productdesc', 'mrp', 'salesprice',
            'cesstype', 'cgst', 'sgst', 'igst', 'is_pieces', 'cess','hsn'
        ]


class ProductBulkSerializer(serializers.ModelSerializer):
    productcategoryName = serializers.CharField(write_only=True)  # Accept productcategoryName instead of ID
    entity = serializers.PrimaryKeyRelatedField(read_only=True)  # Exclude from required input
    # purchaseaccountcode = serializers.IntegerField(write_only=True)
    # saleaccountcode = serializers.IntegerField(write_only=True)

    class Meta:
        model = Product
        fields = '__all__'  # Include all fields + productcategoryName

    def validate_productcategoryName(self, value):
        """ Validate and fetch the ProductCategory based on productcategoryName. """
        try:
            return ProductCategory.objects.get(pcategoryname=value)  # Adjust field if needed
        except ProductCategory.DoesNotExist:
            raise serializers.ValidationError(f"ProductCategory '{value}' does not exist.")

    def create(self, validated_data):
        """ Override create method to use productcategory fetched from name. """
        product_category = validated_data.pop('productcategoryName', None)
        validated_data['productcategory'] = product_category  # Assign category to field
        return Product(**validated_data)  # Create object but don't save yet
    



class ProductBulkSerializerlatest(serializers.ModelSerializer):
    productcategory = serializers.CharField(write_only=True)
    purchaseaccount = serializers.CharField(write_only=True)
    saleaccount = serializers.CharField(write_only=True)
    hsn = serializers.CharField(write_only=True, required=False, allow_null=True)
    ratecalculate = serializers.CharField(write_only=True)
    unitofmeasurement = serializers.CharField(write_only=True)
   
    class Meta:
        model = Product
        fields = [
            "productname", "productdesc", "openingstockqty",
            "productcategory", "openingstockvalue", "purchaserate", "prlesspercentage",
            "mrp", "mrpless", "salesprice", "totalgst", "cgst", "igst", "sgst",
            "cesstype", "cess", "purchaseaccount", "saleaccount", "ratecalculate",
            "unitofmeasurement", "hsn", "is_pieces", "is_product"
        ]

    def get_object_or_error(self, model, field, value, field_name):
        """ Fetch the related object based on field (name/code) or raise an error. """
        if not value:
            raise serializers.ValidationError({field_name: f"{field_name} is required."})
        obj = model.objects.filter(**{field: value}).first()
        if not obj:
            raise serializers.ValidationError({field_name: f"Invalid {field_name}: '{value}' not found."})
        return obj

    def create(self, validated_data):
        entity = self.context["entity"]  # Extract entity from context
        productcategory = self.get_object_or_error(ProductCategory, "pcategoryname", validated_data.pop("productcategory", None), "productcategory")
        purchaseaccount = self.get_object_or_error(account, "accountname", validated_data.pop("purchaseaccount", None), "purchaseaccount")
        saleaccount = self.get_object_or_error(account, "accountname", validated_data.pop("saleaccount", None), "saleaccount")
        hsn = self.get_object_or_error(HsnCode, "hsnCode", validated_data.pop("hsn", None), "hsn")
        ratecalculate = self.get_object_or_error(Ratecalculate, "rname", validated_data.pop("ratecalculate", None), "ratecalculate")
        unitofmeasurement = self.get_object_or_error(UnitofMeasurement, "unitcode", validated_data.pop("unitofmeasurement", None), "unitofmeasurement")
      
        product = Product.objects.create(
            entity=entity,  # Assign entity from context
            productcategory=productcategory,
            purchaseaccount=purchaseaccount,
            saleaccount=saleaccount,
            hsn=hsn,
            ratecalculate=ratecalculate,
            unitofmeasurement=unitofmeasurement,
            **validated_data
        )
        return product
    
class BillOfMaterialSerializerList(serializers.ModelSerializer):

    product_name = serializers.CharField(source='finished_good.productname', read_only=True)
    class Meta:
        model = BillOfMaterial
        fields = ['id', 'finished_good', 'product_name', 'version', 'is_active', 'created_at', 'entity', 'createdby']
    
class BOMItemSerializer(serializers.ModelSerializer):
    raw_material_name = serializers.CharField(source='raw_material.name', read_only=True)

    class Meta:
        model = BOMItem
        fields = ['id', 'raw_material', 'raw_material_name', 'is_percentage',
                  'quantity_required_per_unit','wastage_material','quantity_produced_per_unit']


class BillOfMaterialSerializer(serializers.ModelSerializer):
    finished_good_name = serializers.CharField(source='finished_good.name', read_only=True)
    items = BOMItemSerializer(many=True)

    class Meta:
        model = BillOfMaterial
        fields = ['id', 'finished_good', 'finished_good_name', 'version', 'is_active', 'created_at','entity','createdby', 'items']

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        bom = BillOfMaterial.objects.create(**validated_data)
        for item_data in items_data:
            BOMItem.objects.create(bom=bom, **item_data)
        return bom

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', [])
        instance.finished_good = validated_data.get('finished_good', instance.finished_good)
        instance.version = validated_data.get('version', instance.version)
        instance.is_active = validated_data.get('is_active', instance.is_active)
        instance.save()

        # Optional: Clear old items and recreate new ones
        instance.items.all().delete()
        for item_data in items_data:
            BOMItem.objects.create(bom=instance, **item_data)

        return instance
    

class productionorderVSerializer(serializers.ModelSerializer):
    #entityUser = entityUserSerializer(many=True)
  #  id = serializers.IntegerField(required=False)

    newvoucher = serializers.SerializerMethodField()

    def get_newvoucher(self, obj):
        if not obj.voucherno:
            return 1
        else:
            return obj.voucherno + 1

    class Meta:
        model = ProductionOrder
        fields =  ['newvoucher']

    

class ProductionConsumptionSerializer(serializers.ModelSerializer):

    raw_material_name = serializers.CharField(source='raw_material.productname', read_only=True)
    quantity_consumed_name = serializers.CharField(source='quantity_consumed.productname', read_only=True)
    class Meta:
        model = ProductionConsumption
        fields = ['raw_material','raw_material_name', 'quantity_consumed','quantity_consumed_name', 'scrap_or_wastage', 'batch_number', 'expiry_date']

class ProductionOrderSerializer(serializers.ModelSerializer):
    consumptions = ProductionConsumptionSerializer(many=True)
    

    class Meta:
        model = ProductionOrder
        fields = ['id','voucherno','finished_good', 'bom', 'quantity_to_produce', 'status', 'production_date', 'created_by', 'updated_by', 'updated_at','entity','consumptions']

    def create(self, validated_data):
        consumptions_data = validated_data.pop('consumptions')
        production_order = ProductionOrder.objects.create(**validated_data)

        for consumption_data in consumptions_data:
            ProductionConsumption.objects.create(production_order=production_order, **consumption_data)

        return production_order

    def update(self, instance, validated_data):
        consumptions_data = validated_data.pop('consumptions', None)

        # Update fields of production order
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if consumptions_data:
            instance.consumptions.all().delete()
            for consumption_data in consumptions_data:
                ProductionConsumption.objects.create(production_order=instance, **consumption_data)

        return instance
    

class BillOfMaterialListSerializer(serializers.ModelSerializer):
    bom_id = serializers.IntegerField(source='id')

    class Meta:
        model = BillOfMaterial
        fields = ['bom_id', 'finished_good', 'version']


class BOMItemCalculatedSerializer(serializers.ModelSerializer):
    bom_id = serializers.IntegerField(source='bom.id')
    raw_material_name = serializers.CharField(source='raw_material.productname', read_only=True)
    wastage_material_name = serializers.CharField(source='wastage_material.productname', read_only=True)

    calculated_quantity_required_per_unit = serializers.SerializerMethodField()
    calculated_quantity_produced_per_unit = serializers.SerializerMethodField()

    class Meta:
        model = BOMItem
        fields = [
            'bom_id',
            'raw_material',
            'raw_material_name',
            'wastage_material',
            'wastage_material_name',
            'is_percentage',
            'calculated_quantity_required_per_unit',
            'calculated_quantity_produced_per_unit'
        ]

    def get_calculated_quantity_required_per_unit(self, obj):
        quantity = self.context.get('quantity', 1)
        return float(obj.quantity_required_per_unit) * quantity

    def get_calculated_quantity_produced_per_unit(self, obj):
        quantity = self.context.get('quantity', 1)
        if obj.is_percentage:
            return float(obj.quantity_produced_per_unit) * quantity / 100
        else:
            return float(obj.quantity_produced_per_unit) * quantity
        

class ProductionOrderListSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='finished_good.productname', read_only=True)
    bom_version = serializers.IntegerField(source='bom.version', read_only=True)
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = ProductionOrder
        fields = [
            'id',  # Production Order ID
            'product_name',
            'bom_version',
            'status',
            'status_label',
            'production_date',
        ]

    def get_status_label(self, obj):
        status_dict = {
            1: 'Pending',
            2: 'In Progress',
            3: 'Complete'
        }
        return status_dict.get(obj.status, 'Unknown')