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
        constraints = [
            models.UniqueConstraint(fields=['countrycode'], condition=models.Q(isactive=True), name='uq_country_active_code'),
        ]
        indexes = [
            models.Index(fields=['countrycode', 'countryname']),  # Index for search queries
        ]

    def __str__(self):
        return f'{self.countrycode}, {self.countryname}'

    def save(self, *args, **kwargs):
        self.countryname = (self.countryname or '').strip()
        self.countrycode = (self.countrycode or '').strip().upper()
        super().save(*args, **kwargs)


class State(TrackingModel):
    statename = models.CharField(max_length=255)
    statecode = models.CharField(max_length=2)
    country = models.ForeignKey(Country, related_name='state', on_delete=models.PROTECT)

    # Adding index on statecode for faster lookups
    class Meta:
        verbose_name = _('State')
        verbose_name_plural = _('States')
        constraints = [
            models.UniqueConstraint(fields=['country', 'statecode'], condition=models.Q(isactive=True), name='uq_state_active_country_code'),
        ]
        indexes = [
            models.Index(fields=['statecode', 'statename']),  # Index for faster state filtering
        ]

    def __str__(self):
        return f'{self.statecode}, {self.statename}'

    def save(self, *args, **kwargs):
        self.statename = (self.statename or '').strip()
        self.statecode = str(self.statecode or '').strip().zfill(2)[:2]
        super().save(*args, **kwargs)


class District(TrackingModel):
    districtname = models.CharField(max_length=255)
    districtcode = models.CharField(max_length=25)
    state = models.ForeignKey(State, related_name='districts', on_delete=models.PROTECT, null=True)

    class Meta:
        verbose_name = _('District')
        verbose_name_plural = _('Districts')
        constraints = [
            models.UniqueConstraint(fields=['state', 'districtcode'], condition=models.Q(isactive=True), name='uq_district_active_state_code'),
            models.UniqueConstraint(fields=['state', 'districtname'], condition=models.Q(isactive=True), name='uq_district_active_state_name'),
        ]
        indexes = [
            models.Index(fields=['districtcode', 'districtname']),
        ]

    def __str__(self):
        return f'{self.districtcode}, {self.districtname}'

    def save(self, *args, **kwargs):
        self.districtname = (self.districtname or '').strip()
        self.districtcode = (self.districtcode or '').strip().upper()
        super().save(*args, **kwargs)


class City(TrackingModel):
    cityname = models.CharField(max_length=255)
    citycode = models.CharField(max_length=25)
    pincode = models.CharField(max_length=25)
    latitude = models.FloatField(default=0.0) 
    longitude = models.FloatField(default=0.0)
    distt = models.ForeignKey(District, related_name='cities', on_delete=models.PROTECT, null=True, db_index=True)

    class Meta:
        verbose_name = _('City')
        verbose_name_plural = _('Cities')
        constraints = [
            models.UniqueConstraint(fields=['distt', 'citycode'], condition=models.Q(isactive=True), name='uq_city_active_district_code'),
            models.UniqueConstraint(fields=['distt', 'cityname', 'pincode'], condition=models.Q(isactive=True), name='uq_city_active_district_name_pin'),
        ]
        indexes = [
            models.Index(fields=['citycode', 'pincode']),
        ]

    def __str__(self):
        return f'{self.citycode}, {self.cityname}'

    def save(self, *args, **kwargs):
        self.cityname = (self.cityname or '').strip()
        self.citycode = (self.citycode or '').strip().upper()
        self.pincode = (self.pincode or '').strip()
        super().save(*args, **kwargs)
