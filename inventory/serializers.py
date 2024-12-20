from rest_framework import serializers
from inventory.models import Product,Album,Track,ProductCategory,Ratecalculate,UnitofMeasurement,stkcalculateby,typeofgoods,stkvaluationby,gsttype,HsnCode
from invoice.models import entry,StockTransactions
from financial.models import account
from entity.models import entityfinancialyear



class ProductCategoryMainSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProductCategory
        fields = ('id','pcategoryname','maincategory','entity',)

    def create(self, validated_data):

        catcount = ProductCategory.objects.filter(entity__isnull=True).count()

        if catcount > 8:
            return 1
        
        category = ProductCategory.objects.create(**validated_data)
        


        
        return category


class ProductCategorySerializer(serializers.ModelSerializer):

    maincategoryname = serializers.SerializerMethodField()

    class Meta:
        model = ProductCategory
        fields = ('id','pcategoryname','maincategory','entity','maincategoryname',)

    def get_maincategoryname(self,obj):
       # acc =  obj.accountHeadSr.name
        if obj.maincategory is None:
            return 'null'   
        else :
            return obj.maincategory.pcategoryname
        
    

class ProductSerializer(serializers.ModelSerializer):


   # pcategoryname = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields ='__all__'

    def create(self, validated_data):
        #print(validated_data)
        #journaldetails_data = validated_data.pop('journaldetails')
        detail = Product.objects.create(**validated_data)
       # entryid,created  = entry.objects.get_or_create(entrydate1 = detail.created_at,entity=detail.entity)
        os = account.objects.get(entity =detail.entity,accountcode = 9000)

        accountdate1 = entityfinancialyear.objects.get(entity = detail.entity).finstartyear

        entryid,created  = entry.objects.get_or_create(entrydate1 = accountdate1,entity=detail.entity)



        if detail.openingstockvalue is not None:
            if (detail.openingstockqty ==0.00):
                    qty = detail.openingstockboxqty
            else:
                    qty = detail.openingstockqty
            details = StockTransactions.objects.create(accounthead = os.accounthead,account= os,stock=detail,transactiontype = 'O',transactionid = detail.id,desc = 'Opening Stock ' + detail.productname,stockttype = 'R',quantity = qty,drcr = 1,debitamount = detail.openingstockvalue,entrydate = accountdate1,entity = detail.entity,createdby = detail.createdby,entry = entryid,entrydatetime = accountdate1,accounttype = 'DD',isactive = 1,rate = detail.purchaserate)
            #return detail
        return detail

  


class Trackserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = Track
        fields = ('id','order','title','duration',)

class Ratecalculateserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = Ratecalculate
        fields = ('id','rname','rcode',)

class UOMserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = UnitofMeasurement
        fields = ('id','unitname','unitcode',)

class TOGserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = typeofgoods
        fields = ('id','goodstype','goodscode',)

class GSTserializer(serializers.ModelSerializer):
    #id = serializers.IntegerField()
    class Meta:
        model = gsttype
        fields = ('id','gsttypename','gsttypecode',)


class HSNserializer(serializers.ModelSerializer):
    class Meta:
        model = HsnCode
        fields = ('id','hsnCode','Hsndescription',)



        
        

class AlbumSerializer(serializers.ModelSerializer):
    tracks = Trackserializer(many=True)

    class Meta:
        model = Album
        fields = ['id','album_name', 'artist', 'tracks',]


    def create(self, validated_data):
        print(validated_data)
        tracks_data = validated_data.pop('tracks')
        album = Album.objects.create(**validated_data)
        print(tracks_data)
        for track_data in tracks_data:
            Track.objects.create(album = album, **track_data)
        return album

    def update(self, instance, validated_data):
        instance.album_name = validated_data.get('album_name', instance.album_name)
        instance.artist = validated_data.get('artist', instance.artist)
        instance.save()

        tracks = validated_data.get('tracks')

        print(tracks)

        product_items_dict = dict((i.id, i) for i in instance.tracks.all())

       # print(product_items_dict)
        

        for track in tracks:
            track_id = track.get('id', None)
            print(track_id)
            if track_id:
                track_item = Track.objects.get(id=track_id)
                track_item.order = track.get('order', track_item.order)
                track_item.title = track.get('title', track_item.title)
                track_item.duration = track.get('duration', track_item.duration)
                track_item.save()
            else:
                Track.objects.create(album = instance, **track)

        # if len(product_items_dict) > 0:
        #     for item not in product_items_dict.values():
        #         item.delete()

        return instance

   



