from django.shortcuts import render
from rest_framework.generics import (
    CreateAPIView, ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
)
from rest_framework import permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction

from inventory.models import (
    Album, Product, Track, ProductCategory, gsttype, typeofgoods, Ratecalculate,
    UnitofMeasurement, HsnCode
)
from inventory.serializers import (
    ProductSerializer, AlbumSerializer, TrackSerializer, ProductCategorySerializer,
    GSTSerializer, TOGSerializer, UOMSerializer, RateCalculateSerializer, HSNSerializer
)


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
        return serializer.save(owner=self.request.user)

    def get_queryset(self):
        return Album.objects.filter(owner=self.request.user)


class AlbumUpdateDeleteApiView(RetrieveUpdateDestroyAPIView):
    serializer_class = AlbumSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "id"

    def get_queryset(self):
        return Album.objects.filter(owner=self.request.user)


class TrackApiView(ListCreateAPIView):
    serializer_class = TrackSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['id', 'album', 'order', 'title', 'duration']

    def perform_create(self, serializer):
        return serializer.save(owner=self.request.user)

    def get_queryset(self):
        return Track.objects.filter(owner=self.request.user)


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
