from django.contrib import admin
from import_export.admin import ImportExportMixin

from geography.models import City, Country, District, State


class StateInline(admin.TabularInline):
    model = State
    extra = 0
    fields = ("statecode", "statename")


@admin.register(Country)
class CountryAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ("countrycode", "countryname")
    search_fields = ("countrycode", "countryname")
    inlines = [StateInline]


class DistrictInline(admin.TabularInline):
    model = District
    extra = 0
    fields = ("districtcode", "districtname")


@admin.register(State)
class StateAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ("statecode", "statename", "country")
    search_fields = ("statecode", "statename", "country__countryname")
    list_filter = (("country", admin.RelatedOnlyFieldListFilter),)
    inlines = [DistrictInline]


class CityInline(admin.TabularInline):
    model = City
    extra = 0
    fields = ("citycode", "cityname", "pincode")


@admin.register(District)
class DistrictAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ("districtname", "districtcode", "state")
    search_fields = ("districtname", "districtcode", "state__statename")
    list_filter = (("state", admin.RelatedOnlyFieldListFilter),)
    inlines = [CityInline]


@admin.register(City)
class CityAdmin(ImportExportMixin, admin.ModelAdmin):
    list_display = ("cityname", "citycode", "distt", "pincode")
    search_fields = ("cityname", "citycode", "pincode")
    list_filter = (("distt", admin.RelatedOnlyFieldListFilter),)
