from django.db import models
from helpers.models import TrackingModel
from django.utils.translation import gettext as _

class Country(TrackingModel):
    countryname = models.CharField(max_length=255)
    countrycode = models.CharField(max_length=25)

    # Adding index on countrycode and countryname for faster lookups
    class Meta:
        verbose_name = _('country')
        verbose_name_plural = _('countries')
        indexes = [
            models.Index(fields=['countrycode', 'countryname']),  # Index for search queries
        ]

    def __str__(self):
        return f'{self.countrycode}, {self.countryname}'


class State(TrackingModel):
    statename = models.CharField(max_length=255)
    statecode = models.CharField(max_length=255)
    country = models.ForeignKey(Country, related_name='state', on_delete=models.PROTECT)

    # Adding index on statecode for faster lookups
    class Meta:
        verbose_name = _('State')
        verbose_name_plural = _('States')
        indexes = [
            models.Index(fields=['statecode', 'statename']),  # Index for faster state filtering
        ]

    def __str__(self):
        return f'{self.statecode}, {self.statename}'


class District(TrackingModel):
    districtname = models.CharField(max_length=255)
    districtcode = models.CharField(max_length=25)
    state = models.ForeignKey(State, related_name='districts', on_delete=models.PROTECT, null=True)

    # Adding index on districtcode for faster lookups
    class Meta:
        verbose_name = _('District')
        verbose_name_plural = _('Districts')
        indexes = [
            models.Index(fields=['districtcode', 'districtname']),  # Index for faster district filtering
        ]

    def __str__(self):
        return f'{self.districtcode}, {self.districtname}'


class City(TrackingModel):
    cityname = models.CharField(max_length=255)
    citycode = models.CharField(max_length=25)
    pincode = models.CharField(max_length=25)
    latitude = models.FloatField(default=0.0) 
    longitude = models.FloatField(default=0.0)
    distt = models.ForeignKey(District, related_name='cities', on_delete=models.PROTECT, null=True, db_index=True)

    # Adding index on citycode and pincode for faster lookups
    class Meta:
        verbose_name = _('City')
        verbose_name_plural = _('Cities')
        indexes = [
            models.Index(fields=['citycode', 'pincode']),  # Index for faster city filtering
        ]

    def __str__(self):
        return f'{self.citycode}, {self.cityname}'
