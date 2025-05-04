from django.db import transaction
from rest_framework import serializers
from inventory.models import Product,ProductCategory, Ratecalculate, UnitofMeasurement, typeofgoods, gsttype, HsnCode,BillOfMaterial, BOMItem,ProductionOrder, ProductionConsumption,BarcodeDetail
from invoice.models import entry, StockTransactions
from financial.models import account
from entity.models import entityfinancialyear
from PIL import Image, ImageDraw, ImageFont
from barcode import Code128
from barcode.writer import ImageWriter
from io import BytesIO
from django.core.files.base import ContentFile
import random


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


# class ProductSerializer(serializers.ModelSerializer):
#     barcode_image_url = serializers.SerializerMethodField()

#     class Meta:
#         model = Product
#         fields = '__all__'

#     def get_barcode_image_url(self, obj):
#         request = self.context.get('request')
#         if obj.barcode_image and request:
#             return request.build_absolute_uri(obj.barcode_image.url)
#         return None

#     def generate_unique_barcode(self):
#         while True:
#             number = f'{random.randint(100000000000, 999999999999)}'  # 12-digit
#             if not Product.objects.filter(barcode_number=number).exists():
#                 return number

#     def create(self, validated_data):
#         with transaction.atomic():
#             # Auto-generate barcode number if not provided
#             barcode_number = validated_data.get('barcode_number') or self.generate_unique_barcode()
#             validated_data['barcode_number'] = barcode_number

#             mrp = validated_data.get('mrp')
#             salesprice = validated_data.get('salesprice')

#             # Create product without barcode_image first
#             product = Product.objects.create(**validated_data)

#             # Generate barcode image
#             # Generate barcode image
#             buffer = BytesIO()
#             barcode = Code128(barcode_number, writer=ImageWriter())
#             barcode.write(buffer, {
#                 'module_width': 0.4,        # thicker bars
#                 'module_height': 20.0,      # taller bars
#                 'quiet_zone': 6.5,          # better margins
#                 'write_text': False         # disables default barcode text
#             })
#             barcode_img = Image.open(buffer)

#             # Prepare for adding text below barcode
#             width, height = barcode_img.size
#             extra_height = 60  # more space for text
#             new_image = Image.new('RGB', (width, height + extra_height), 'white')
#             new_image.paste(barcode_img, (0, 0))

#             # Draw text on the new image
#             draw = ImageDraw.Draw(new_image)
#             try:
#                 font = ImageFont.truetype("arial.ttf", 16)
#             except:
#                 font = ImageFont.load_default()

#             # Compose text
#             line1 = f"{product.productname} | {barcode_number}"
#             line2 = f"MRP: ₹{mrp or 0:.2f} | Sale: ₹{salesprice or 0:.2f}"

#             # Calculate X-position to center-align
#             def center_text(text, width, font):
#                 text_width = draw.textlength(text, font=font)
#                 return (width - text_width) // 2

#             draw.text((center_text(line1, width, font), height + 5), line1, fill='black', font=font)
#             draw.text((center_text(line2, width, font), height + 30), line2, fill='black', font=font)

#             # Save final image
#             final_buffer = BytesIO()
#             new_image.save(final_buffer, format='PNG')
#             file_name = f'{barcode_number}.png'
#             product.barcode_image.save(file_name, ContentFile(final_buffer.getvalue()), save=False)

#             product.save()

#             # Handle stock transactions
#             os = account.objects.get(entity=product.entity, accountcode=9000)
#             accountdate1 = entityfinancialyear.objects.get(entity=product.entity, isactive=True).finstartyear
#             entryid, _ = entry.objects.get_or_create(entrydate1=accountdate1, entity=product.entity)

#             if product.openingstockvalue and (product.openingstockqty or product.openingstockboxqty):
#                 qty = product.openingstockqty or product.openingstockboxqty
#                 StockTransactions.objects.create(
#                     accounthead=os.accounthead,
#                     account=os,
#                     stock=product,
#                     transactiontype='O',
#                     transactionid=product.id,
#                     desc=f'Opening Stock {product.productname}',
#                     stockttype='R',
#                     quantity=qty,
#                     drcr=1,
#                     debitamount=product.openingstockvalue,
#                     entrydate=accountdate1,
#                     entity=product.entity,
#                     createdby=product.createdby,
#                     entry=entryid,
#                     entrydatetime=accountdate1,
#                     accounttype='DD',
#                     isactive=True,
#                     rate=product.purchaserate
#                 )

#             return product
        

class ProductSerializer(serializers.ModelSerializer):
    mrp = serializers.SerializerMethodField()
    salesprice = serializers.SerializerMethodField()
    barcode_number = serializers.SerializerMethodField()
    barcode_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = '__all__'  # Or list explicitly for more control

    def get_latest_barcode(self, obj):
        return obj.barcode_detail.order_by('-created_on').first()

    def get_mrp(self, obj):
        latest = self.get_latest_barcode(obj)
        return latest.mrp if latest else None

    def get_salesprice(self, obj):
        latest = self.get_latest_barcode(obj)
        return latest.salesprice if latest else None

    def get_barcode_number(self, obj):
        latest = self.get_latest_barcode(obj)
        return latest.barcode_number if latest else None

    def get_barcode_image(self, obj):
        latest = self.get_latest_barcode(obj)
        request = self.context.get('request')
        if latest and latest.barcode_image and request:
            return request.build_absolute_uri(latest.barcode_image.url)
        return None

    def generate_unique_barcode(self):
        while True:
            number = f'{random.randint(100000000000, 999999999999)}'
            if not BarcodeDetail.objects.filter(barcode_number=number).exists():
                return number

    def create(self, validated_data):
        with transaction.atomic():
            # Extract and remove fields that belong to BarcodeDetail
            mrp = validated_data.pop('mrp', None)
            salesprice = validated_data.pop('salesprice', None)
            barcode_number = validated_data.pop('barcode_number', None) or self.generate_unique_barcode()

            # Create product
            product = Product.objects.create(**validated_data)

            # If barcode is required, create BarcodeDetail
            if product.isbarcoderequired:
                barcode_image = self.generate_barcode_image(barcode_number, product, mrp, salesprice)
                barcode_detail = BarcodeDetail.objects.create(
                    product=product,
                    mrp=mrp,
                    salesprice=salesprice,
                    barcode_number=barcode_number,
                )
                file_name = f'{barcode_number}.png'
                barcode_detail.barcode_image.save(file_name, barcode_image, save=True)

            return product

    def generate_barcode_image(self, barcode_number, product, mrp, salesprice):
        buffer = BytesIO()
        barcode = Code128(barcode_number, writer=ImageWriter())
        barcode.write(buffer, {
            'module_width': 0.4,
            'module_height': 20.0,
            'quiet_zone': 6.5,
            'write_text': False
        })
        barcode_img = Image.open(buffer)

        width, height = barcode_img.size
        extra_height = 60
        new_image = Image.new('RGB', (width, height + extra_height), 'white')
        new_image.paste(barcode_img, (0, 0))

        draw = ImageDraw.Draw(new_image)
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()

        line1 = f"{product.productname} | {barcode_number}"
        line2 = f"MRP: ₹{mrp or 0:.2f} | Sale: ₹{salesprice or 0:.2f}"

        def center_text(text, width, font):
            text_width = draw.textlength(text, font=font)
            return (width - text_width) // 2

        draw.text((center_text(line1, width, font), height + 5), line1, fill='black', font=font)
        draw.text((center_text(line2, width, font), height + 30), line2, fill='black', font=font)

        final_buffer = BytesIO()
        new_image.save(final_buffer, format='PNG')
        return ContentFile(final_buffer.getvalue())
    


class ProductByBarcodeSerializer(serializers.ModelSerializer):
    mrp = serializers.SerializerMethodField()
    salesprice = serializers.SerializerMethodField()
    barcode_number = serializers.SerializerMethodField()
    barcode_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [field.name for field in Product._meta.fields] + [
            'mrp', 'salesprice', 'barcode_number', 'barcode_image'
        ]

    def get_cached_barcode_detail(self, obj):
        if not hasattr(self, '_barcode_detail_cache'):
            barcode = self.context.get('barcode')
            self._barcode_detail_cache = obj.barcode_detail.filter(barcode_number=barcode).first()
        return self._barcode_detail_cache

    def get_mrp(self, obj):
        bd = self.get_cached_barcode_detail(obj)
        return bd.mrp if bd and bd.mrp else obj.mrp

    def get_salesprice(self, obj):
        bd = self.get_cached_barcode_detail(obj)
        return bd.salesprice if bd and bd.salesprice else obj.salesprice

    def get_barcode_number(self, obj):
        bd = self.get_cached_barcode_detail(obj)
        return bd.barcode_number if bd else None

    def get_barcode_image(self, obj):
        bd = self.get_cached_barcode_detail(obj)
        request = self.context.get('request')
        if bd and bd.barcode_image and request:
            return request.build_absolute_uri(bd.barcode_image.url)
        return None




# class TrackSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Track
#         fields = ('id', 'order', 'title', 'duration',)


class BarcodeDetailSerializer(serializers.ModelSerializer):
    barcode_image_url = serializers.SerializerMethodField()

    class Meta:
        model = BarcodeDetail
        fields = '__all__'

    def get_barcode_image_url(self, obj):
        request = self.context.get('request')
        if obj.barcode_image and request:
            return request.build_absolute_uri(obj.barcode_image.url)
        return None

    def generate_unique_barcode(self):
        while True:
            number = f'{random.randint(100000000000, 999999999999)}'
            if not BarcodeDetail.objects.filter(barcode_number=number).exists():
                return number

    def generate_barcode_image(self, barcode_number, product, mrp, salesprice):
        buffer = BytesIO()
        barcode = Code128(barcode_number, writer=ImageWriter())
        barcode.write(buffer, {
            'module_width': 0.4,
            'module_height': 20.0,
            'quiet_zone': 6.5,
            'write_text': False
        })
        barcode_img = Image.open(buffer)

        width, height = barcode_img.size
        extra_height = 60
        new_image = Image.new('RGB', (width, height + extra_height), 'white')
        new_image.paste(barcode_img, (0, 0))

        draw = ImageDraw.Draw(new_image)
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()

        line1 = f"{product.productname} | {barcode_number}"
        line2 = f"MRP: ₹{mrp or 0:.2f} | Sale: ₹{salesprice or 0:.2f}"

        def center_text(text, width, font):
            text_width = draw.textlength(text, font=font)
            return (width - text_width) // 2

        draw.text((center_text(line1, width, font), height + 5), line1, fill='black', font=font)
        draw.text((center_text(line2, width, font), height + 30), line2, fill='black', font=font)

        final_buffer = BytesIO()
        new_image.save(final_buffer, format='PNG')
        return ContentFile(final_buffer.getvalue())

    def create(self, validated_data):
        with transaction.atomic():
            product = validated_data.get('product')
            mrp = validated_data.get('mrp')
            salesprice = validated_data.get('salesprice')

            barcode_number = validated_data.get('barcode_number') or self.generate_unique_barcode()
            barcode_image = self.generate_barcode_image(barcode_number, product, mrp, salesprice)

            barcode_detail = BarcodeDetail.objects.create(
                product=product,
                mrp=mrp,
                salesprice=salesprice,
                barcode_number=barcode_number,
            )

            file_name = f'{barcode_number}.png'
            barcode_detail.barcode_image.save(file_name, barcode_image, save=True)

            return barcode_detail


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


# class AlbumSerializer(serializers.ModelSerializer):
#     tracks = TrackSerializer(many=True)

#     class Meta:
#         model = Album
#         fields = ['id', 'album_name', 'artist', 'tracks']

#     def create(self, validated_data):
#         with transaction.atomic():  # Start transaction block
#             tracks_data = validated_data.pop('tracks')
#             album = Album.objects.create(**validated_data)

#             # Bulk create tracks associated with this album
#             Track.objects.bulk_create([Track(album=album, **track_data) for track_data in tracks_data])

#             return album

#     def update(self, instance, validated_data):
#         with transaction.atomic():  # Start transaction block
#             instance.album_name = validated_data.get('album_name', instance.album_name)
#             instance.artist = validated_data.get('artist', instance.artist)
#             instance.save()

#             # Handle updating or creating tracks
#             tracks = validated_data.get('tracks', [])
#             track_ids = {track['id'] for track in tracks if 'id' in track}

#             existing_tracks = {track.id: track for track in instance.tracks.all()}
#             new_tracks = []

#             for track_data in tracks:
#                 track_id = track_data.get('id')
#                 if track_id and track_id in existing_tracks:
#                     track = existing_tracks[track_id]
#                     track.order = track_data.get('order', track.order)
#                     track.title = track_data.get('title', track.title)
#                     track.duration = track_data.get('duration', track.duration)
#                     track.save()
#                 else:
#                     new_tracks.append(Track(album=instance, **track_data))

#             # Bulk create new tracks
#             if new_tracks:
#                 Track.objects.bulk_create(new_tracks)

#             # Delete tracks that no longer exist in the incoming data
#             track_ids_to_delete = set(existing_tracks.keys()) - track_ids
#             if track_ids_to_delete:
#                 instance.tracks.filter(id__in=track_ids_to_delete).delete()

#             return instance
        

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
    wastage_sku_name = serializers.CharField(source='wastage_sku.productname', read_only=True)
    class Meta:
        model = ProductionConsumption
        fields = ['raw_material','raw_material_name', 'quantity_consumed','wastage_sku','scrap_or_wastage','wastage_sku_name', 'batch_number', 'expiry_date']

class ProductionOrderSerializer(serializers.ModelSerializer):
    consumptions = ProductionConsumptionSerializer(many=True)
    

    class Meta:
        model = ProductionOrder
        fields = ['id','voucherno','finished_good', 'bom', 'quantity_to_produce', 'status', 'production_date', 'created_by', 'updated_by', 'updated_at','entity','consumptions']

    def create(self, validated_data):
        consumptions_data = validated_data.pop('consumptions')
        production_order = ProductionOrder.objects.create(**validated_data)

        entryid, _ = entry.objects.get_or_create(entrydate1=production_order.updated_at, entity=production_order.entity)

        StockTransactions.objects.create(account= production_order.finished_good.purchaseaccount,stock=production_order.finished_good,transactiontype = 'R',transactionid = production_order.id,drcr = True,quantity = production_order.quantity_to_produce,entrydate = production_order.updated_at,entrydatetime = production_order.updated_at,entity = production_order.entity,createdby = production_order.created_by,entry = entryid,stockttype= 'R',accounttype = 'DD',voucherno = production_order.voucherno,desc = 'Production Order V.No ' + str(production_order.voucherno))

        for consumption_data in consumptions_data:
            details = ProductionConsumption.objects.create(production_order=production_order, **consumption_data)

            StockTransactions.objects.create(account= details.raw_material.purchaseaccount,stock=details.raw_material,transactiontype = 'I',transactionid = production_order.id,drcr = False,quantity = details.quantity_consumed,entrydate = production_order.updated_at,entrydatetime = production_order.updated_at,entity = production_order.entity,createdby = production_order.created_by,entry = entryid,stockttype= 'I',accounttype = 'DD',voucherno = production_order.voucherno,desc = 'Production Order V.No ' + str(production_order.voucherno))

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
            'voucherno',
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
    

class BillOfMaterialListbyentitySerializer(serializers.ModelSerializer):
    finished_good_name = serializers.CharField(source='finished_good.productname', read_only=True)

    class Meta:
        model = BillOfMaterial
        fields = ['id','finished_good_name', 'version', 'is_active']