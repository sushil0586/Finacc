from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.generics import (
    CreateAPIView, ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
)
from rest_framework import permissions, filters,generics, status
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status

from inventory.models import (
    Album, Product, Track, ProductCategory, gsttype, typeofgoods, Ratecalculate,
    UnitofMeasurement, HsnCode,BillOfMaterial,ProductionOrder,BOMItem
)
from inventory.serializers import (
    ProductSerializer, AlbumSerializer, TrackSerializer, ProductCategorySerializer,
    GSTSerializer, TOGSerializer, UOMSerializer, RateCalculateSerializer, HSNSerializer,ProductBulkSerializer,ProductListSerializer,ProductBulkSerializerlatest,BillOfMaterialSerializer,ProductionOrderSerializer,BillOfMaterialListSerializer,BOMItemCalculatedSerializer,BillOfMaterialSerializerList,
    ProductionOrderListSerializer,productionorderVSerializer,BillOfMaterialListbyentitySerializer
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
    
    
class ProductBulkCreateAPIView(APIView):
    def post(self, request, entity_id, *args, **kwargs):
        try:
            entity = Entity.objects.get(id=entity_id)
        except Entity.DoesNotExist:
            return Response({"error": "Invalid entity ID"}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = ProductBulkSerializerlatest(data=request.data, many=True, context={"entity": entity})
        if serializer.is_valid():
            with transaction.atomic():
                serializer.save()
            return Response({"message": "Products created successfully!"}, status=status.HTTP_201_CREATED)
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



class BillOfMaterialAPIView(generics.GenericAPIView,EntityFilterMixin):
    queryset = BillOfMaterial.objects.all().order_by('-created_at')
    serializer_class = BillOfMaterialSerializer

    def get(self, request, pk=None):
        if pk:
            try:
                instance = self.get_queryset().get(pk=pk)
                serializer = self.get_serializer(instance)
                return Response(serializer.data)
            except BillOfMaterial.DoesNotExist:
                return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            queryset = self.filter_by_entity(BillOfMaterial.objects.all())
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk=None):
        try:
            instance = self.get_queryset().get(pk=pk)
        except BillOfMaterial.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk=None):
        try:
            instance = self.get_queryset().get(pk=pk)
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except BillOfMaterial.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        

class BillOfMaterialListView(generics.ListAPIView):
    serializer_class = BillOfMaterialSerializer

    def get_queryset(self):
        entity_id = self.request.query_params.get('entity')
        queryset = BillOfMaterial.objects.all()
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)
        return queryset
    

class ProductionOrderlatestview(ListCreateAPIView):

    serializer_class = productionorderVSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = [DjangoFilterBackend]
    def get(self,request):
        entity = self.request.query_params.get('entity')
        entityfy = self.request.query_params.get('entityfinid')
        id = ProductionOrder.objects.filter(entity= entity,entityfinid = entityfy).last()
        serializer = productionorderVSerializer(id)
        return Response(serializer.data)
        

class ProductionOrderAPIView(generics.GenericAPIView,EntityFilterMixin):
    queryset = ProductionOrder.objects.all().order_by('-updated_at')
    serializer_class = ProductionOrderSerializer
   # permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, pk=None):
        if pk:
            try:
                instance = self.get_queryset().get(pk=pk)
                serializer = self.get_serializer(instance)
                return Response(serializer.data)
            except ProductionOrder.DoesNotExist:
                return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            queryset = self.filter_by_entity(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk=None):
        try:
            instance = self.get_queryset().get(pk=pk)
        except ProductionOrder.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk=None):
        try:
            instance = self.get_queryset().get(pk=pk)
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ProductionOrder.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        

class BillOfMaterialListAPIView(APIView):
    def get(self, request):
        entity_id = request.query_params.get('entity')
        finished_good_id = request.query_params.get('finished_good')

        if not entity_id or not finished_good_id:
            return Response({"detail": "entity and finished_good are required parameters."},
                            status=status.HTTP_400_BAD_REQUEST)

        boms = BillOfMaterial.objects.filter(entity_id=entity_id, finished_good_id=finished_good_id)

        serializer = BillOfMaterialListSerializer(boms, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class BOMItemCalculatedAPIView(APIView):
    def get(self, request):
        bom_id = request.query_params.get('bom')
        quantity = request.query_params.get('quantity')
        entity = request.query_params.get('entity')

        if not bom_id or not quantity:
            return Response({"detail": "Both 'bom' and 'quantity' parameters are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            quantity = float(quantity)
        except ValueError:
            return Response({"detail": "Quantity must be a number."},
                            status=status.HTTP_400_BAD_REQUEST)

        items = BOMItem.objects.filter(bom_id=bom_id)
        serializer = BOMItemCalculatedSerializer(items, many=True, context={'quantity': quantity})
        return Response(serializer.data, status=status.HTTP_200_OK)
    

class BillOfMaterialListbyentityView(generics.ListAPIView):
    serializer_class = BillOfMaterialSerializerList

    def get_queryset(self):
        entity_id = self.request.query_params.get('entity')
        queryset = BillOfMaterial.objects.all()
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)
        return queryset
    

class ProductionOrderListView(generics.ListAPIView):
    serializer_class = ProductionOrderListSerializer
  #  permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        queryset = ProductionOrder.objects.select_related('finished_good', 'bom')

        # Filter by entity (required)
        entity_id = self.request.query_params.get('entity')
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)
        else:
            queryset = queryset.none()  # Return empty if no entity provided

        # Optional filter by status
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        return queryset
    
class BillOfMaterialListbyentityView(generics.ListAPIView):
    serializer_class = BillOfMaterialListbyentitySerializer

    def get_queryset(self):
        queryset = BillOfMaterial.objects.all()
        entity_id = self.request.query_params.get('entity')
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)
        return queryset
   
