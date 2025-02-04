from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.generics import (
    CreateAPIView, ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
)
from rest_framework import permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status

from inventory.models import (
    Album, Product, Track, ProductCategory, gsttype, typeofgoods, Ratecalculate,
    UnitofMeasurement, HsnCode
)
from inventory.serializers import (
    ProductSerializer, AlbumSerializer, TrackSerializer, ProductCategorySerializer,
    GSTSerializer, TOGSerializer, UOMSerializer, RateCalculateSerializer, HSNSerializer,ProductBulkSerializer,ProductListSerializer
)

from Authentication.models import User
from entity.models import Entity


class EntityFilterMixin:
    """Mixin to handle entity filtering across views."""
    def get_entity(self):
        return self.request.query_params.get('entity')

    def filter_by_entity(self, queryset, entity=None):
        """Helper method to filter by entity."""
        if not entity:
            entity = self.get_entity()
        return queryset.filter(entity=entity)


class ProductCategoryApiView(ListCreateAPIView, EntityFilterMixin):
    serializer_class = ProductCategorySerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]

    def perform_create(self, serializer):
        return serializer.save(createdby=self.request.user)

    def get_queryset(self):
        entity = self.get_entity()
        q1 = ProductCategory.objects.filter(entity__isnull=True)
        q2 = ProductCategory.objects.filter(entity=entity)
        return q1.union(q2)


class ProductCategoryUpdateDeleteApiView(RetrieveUpdateDestroyAPIView, EntityFilterMixin):
    serializer_class = ProductCategorySerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        return ProductCategory.objects.all()


class ProductApiView(ListCreateAPIView, EntityFilterMixin):
    serializer_class = ProductSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['productname', 'productdesc', 'id']

    def perform_create(self, serializer):
        return serializer.save(createdby=self.request.user)

    def get_queryset(self):
        entity = self.get_entity()
        return Product.objects.filter(entity=entity)


class ProductUpdateDeleteApiView(RetrieveUpdateDestroyAPIView, EntityFilterMixin):
    serializer_class = ProductSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        return Product.objects.all()


class AlbumApiView(ListCreateAPIView):
    serializer_class = AlbumSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'album_name', 'artist', 'tracks']

    def perform_create(self, serializer):
        return serializer.save(createdby=self.request.user)

    def get_queryset(self):
        return Album.objects.filter(createdby=self.request.user)


class AlbumUpdateDeleteApiView(RetrieveUpdateDestroyAPIView):
    serializer_class = AlbumSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        return Album.objects.filter(createdby=self.request.user)


class TrackApiView(ListCreateAPIView):
    serializer_class = TrackSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'album', 'order', 'title', 'duration']

    def perform_create(self, serializer):
        return serializer.save(createdby=self.request.user)

    def get_queryset(self):
        return Track.objects.filter(createdby=self.request.user)


class UOMApiView(ListCreateAPIView, EntityFilterMixin):
    serializer_class = UOMSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]

    def perform_create(self, serializer):
        return serializer.save(createdby=self.request.user)

    def get_queryset(self):
        return self.filter_by_entity(UnitofMeasurement.objects.all())


class GSTApiView(ListCreateAPIView, EntityFilterMixin):
    serializer_class = GSTSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]

    def perform_create(self, serializer):
        return serializer.save(createdby=self.request.user)

    def get_queryset(self):
        return self.filter_by_entity(gsttype.objects.all())


class HSNApiView(ListAPIView):
    serializer_class = HSNSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        return HsnCode.objects.all()


class TOGApiView(ListCreateAPIView, EntityFilterMixin):
    serializer_class = TOGSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]

    def perform_create(self, serializer):
        return serializer.save(createdby=self.request.user)

    def get_queryset(self):
        return self.filter_by_entity(typeofgoods.objects.all())


class RateApiView(ListCreateAPIView, EntityFilterMixin):
    serializer_class = RateCalculateSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]

    def perform_create(self, serializer):
        return serializer.save(createdby=self.request.user)

    def get_queryset(self):
        return self.filter_by_entity(Ratecalculate.objects.all())
    

class ProductListView(ListAPIView,EntityFilterMixin):

    serializer_class = ProductListSerializer

    def get_queryset(self):
        entity = self.get_entity()
        return self.filter_by_entity(Product.objects.only(
            'id', 'productname', 'productdesc', 'is_pieces', 'mrp', 'mrpless', 'salesprice',
            'cgst', 'sgst', 'igst', 'cesstype', 'cess', 'hsn'
        ).select_related('hsn') )  # Limits fields to reduce query load
    

class BulkProductCreateView(APIView):
    def post(self, request, *args, **kwargs):
        # Extract 'createdby' from headers
        createdby_id = self.request.user
        if not createdby_id:
            return Response({"error": "CreatedBy header is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            createdby = User.objects.get(email=createdby_id)
        except User.DoesNotExist:
            return Response({"error": "Invalid CreatedBy ID"}, status=status.HTTP_400_BAD_REQUEST)

        # Extract 'entity' from query parameters
        entity_id = request.GET.get("entity")
        if not entity_id:
            return Response({"error": "Entity query parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            entity = Entity.objects.get(id=entity_id)
        except Entity.DoesNotExist:
            return Response({"error": "Invalid Entity ID"}, status=status.HTTP_400_BAD_REQUEST)

        # Deserialize and validate data
        serializer = ProductBulkSerializer(data=request.data, many=True)
        if serializer.is_valid():
            with transaction.atomic():
                products = [
                    Product(**data, createdby=createdby, entity=entity)
                    for data in serializer.validated_data
                ]
                Product.objects.bulk_create(products)  # Bulk insert
            return Response({"message": "Products created successfully", "count": len(products)}, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class BulkProductCreateView(APIView,EntityFilterMixin):
#      def post(self, request, *args, **kwargs):
#         # Extract 'createdby' from headers
        # createdby_id = self.request.user
        # if not createdby_id:
        #     return Response({"error": "CreatedBy header is required"}, status=status.HTTP_400_BAD_REQUEST)

        # try:
        #     createdby = User.objects.get(email=createdby_id)
        # except User.DoesNotExist:
        #     return Response({"error": "Invalid CreatedBy ID"}, status=status.HTTP_400_BAD_REQUEST)

#         # # Extract 'entity' from query parameters
#         # entity = self.get_entity()

#         # print(entity)
#         # if not entity:
#         #     return Response({"error": "Entity query parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

       


       

#         # Deserialize and validate data
#         serializer = ProductBulkSerializer(data=request.data, many=True)
#         if serializer.is_valid():
#             with transaction.atomic():
#                 products = Product.objects.bulk_create(
#                     [Product(**data, createdby=createdby) for data in serializer.validated_data]
#                 )
#             return Response({"message": "Products created successfully", "count": len(products)}, status=status.HTTP_201_CREATED)

#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
   
