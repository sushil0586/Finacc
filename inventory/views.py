from django.http import request
from django.shortcuts import render

from rest_framework.generics import CreateAPIView,ListAPIView,ListCreateAPIView,RetrieveUpdateDestroyAPIView
from inventory.models import Album, Product, Track,ProductCategory,gsttype,typeofgoods,Ratecalculate,UnitofMeasurement
from inventory.serializers import ProductSerializer,AlbumSerializer,Trackserializer,ProductCategorySerializer,GSTserializer,TOGserializer,UOMserializer,Ratecalculateserializer
from rest_framework import permissions,filters
from django_filters.rest_framework import DjangoFilterBackend




class productcategoryApiView(ListCreateAPIView):

    serializer_class = ProductCategorySerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
   # filterset_fields = ['id','ProductName','is_stockable']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):

        entity = self.request.query_params.get('entity')
        q1 = ProductCategory.objects.filter(entity__isnull=True)
        q2 = ProductCategory.objects.filter(entity = entity)

        q3 = q1.union(q2)
        return q3

class productcategoryupdatedelApiView(RetrieveUpdateDestroyAPIView):

    serializer_class = ProductCategorySerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')

        if entity:
            return ProductCategory.objects.filter()
        else:
            return ProductCategory.objects.filter()


         


class CreateTodoApiView(CreateAPIView):
    serializer_class = ProductSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def perform_create(self, serializer):
        return serializer.save(owner = self.request.user)


class ListproductApiView(ListAPIView):

    serializer_class = ProductSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return Product.objects.filter(entity = entity)

class productApiView(ListCreateAPIView):

    serializer_class = ProductSerializer
    permission_classes = (permissions.IsAuthenticated,)

    # filter_backends = [DjangoFilterBackend]
    # filterset_fields = ['id','productname',]

    filter_backends = [filters.SearchFilter,filters.OrderingFilter]
    search_fields = ['productname', 'productdesc','id']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return Product.objects.filter(entity = entity)

class productupdatedel(RetrieveUpdateDestroyAPIView):

    serializer_class = ProductSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        entity = self.request.query_params.get('entity')
        return Product.objects.filter()


class AlbumApiView(ListCreateAPIView):

    serializer_class = AlbumSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id','album_name', 'artist', 'tracks']

    def perform_create(self, serializer):
        return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        return Album.objects.filter(owner = self.request.user)


class Albumupdatedel(RetrieveUpdateDestroyAPIView):

    serializer_class = AlbumSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        return Album.objects.filter(owner = self.request.user)


class TrackApiView(ListCreateAPIView):

    serializer_class = Trackserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id','album','order','title','duration']

    def perform_create(self, serializer):
        return serializer.save(owner = self.request.user)
    
    def get_queryset(self):
        return Track.objects.filter(owner = self.request.user)

class uomApiView(ListCreateAPIView):

    serializer_class = UOMserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
   # filterset_fields = ['id','ProductName','is_stockable']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):

        entity = self.request.query_params.get('entity')
        return UnitofMeasurement.objects.filter(entity = entity)



class gstApiView(ListCreateAPIView):

    serializer_class = GSTserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
   # filterset_fields = ['id','ProductName','is_stockable']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):

        entity = self.request.query_params.get('entity')
        return gsttype.objects.filter(entity = entity)

class togApiView(ListCreateAPIView):

    serializer_class = TOGserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
   # filterset_fields = ['id','ProductName','is_stockable']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):

        entity = self.request.query_params.get('entity')
        return typeofgoods.objects.filter(entity = entity)


class rateApiView(ListCreateAPIView):

    serializer_class = Ratecalculateserializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
   # filterset_fields = ['id','ProductName','is_stockable']

    def perform_create(self, serializer):
        return serializer.save(createdby = self.request.user)
    
    def get_queryset(self):

        entity = self.request.query_params.get('entity')
        return Ratecalculate.objects.filter(entity = entity)







