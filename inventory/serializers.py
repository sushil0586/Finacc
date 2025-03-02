from django.db import transaction
from rest_framework import serializers
from inventory.models import Product, Album, Track, ProductCategory, Ratecalculate, UnitofMeasurement, typeofgoods, gsttype, HsnCode
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
            "entity", "productname", "productdesc", "openingstockqty",
            "productcategory", "openingstockvalue", "purchaserate", "prlesspercentage",
            "mrp", "mrpless", "salesprice", "totalgst", "cgst", "igst", "sgst",
            "cesstype", "cess", "purchaseaccount", "saleaccount", "ratecalculate",
            "unitofmeasurement",  "hsn", "is_pieces", "is_product"
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
        productcategory = self.get_object_or_error(ProductCategory, "pcategoryname", validated_data.pop("productcategory", None), "productcategory")
        purchaseaccount = self.get_object_or_error(account, "accountname", validated_data.pop("purchaseaccount", None), "purchaseaccount")
        saleaccount = self.get_object_or_error(account, "accountname", validated_data.pop("saleaccount", None), "saleaccount")
        hsn = self.get_object_or_error(HsnCode, "hsnCode", validated_data.pop("hsn", None), "hsn")
        ratecalculate = self.get_object_or_error(Ratecalculate, "rname", validated_data.pop("ratecalculate", None), "ratecalculate")
        unitofmeasurement = self.get_object_or_error(UnitofMeasurement, "unitcode", validated_data.pop("unitofmeasurement", None), "unitofmeasurement")
      
        product = Product.objects.create(
            productcategory=productcategory,
            purchaseaccount=purchaseaccount,
            saleaccount=saleaccount,
            hsn=hsn,
            ratecalculate=ratecalculate,
            unitofmeasurement=unitofmeasurement,
            **validated_data
        )
        return product