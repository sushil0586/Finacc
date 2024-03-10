from django.db import models
from helpers.models import TrackingModel
from django.utils.translation import gettext as _



# Create your models here.



class country(TrackingModel):
    countryname =    models.CharField(max_length= 255)
    countrycode =    models.CharField(max_length= 25)

    class Meta:
        verbose_name = _('country')
        verbose_name_plural = _('countries')


    
    def __str__(self):
        return f'{self.countrycode} , {self.countryname}'







class state(TrackingModel):
    statename =    models.CharField(max_length= 255)
    statecode =    models.CharField(max_length= 255)
    country = models.ForeignKey(country, related_name='state', on_delete=models.CASCADE)

    
    class Meta:
        verbose_name = _('State')
        verbose_name_plural = _('States')


    
    def __str__(self):
        return f'{self.statecode} , {self.statename}'




class district(TrackingModel):
    districtname =    models.CharField(max_length= 255)
    districtcode =    models.CharField(max_length= 25)
    state = models.ForeignKey(state, related_name='district', on_delete=models.CASCADE,null = True)

    
    def __str__(self):
        return f'{self.districtcode} , {self.districtname}'




class city(TrackingModel):
    cityname =    models.CharField(max_length= 255)
    citycode =    models.CharField(max_length= 25)
    pincode =    models.CharField(max_length= 25)
    distt = models.ForeignKey(district, related_name='city', on_delete=models.CASCADE,null = True)


    
    class Meta:
        verbose_name = _('City')
        verbose_name_plural = _('Cities')


    def __str__(self):
        return f'{self.citycode} , {self.cityname}'
