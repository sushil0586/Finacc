from django.contrib import admin
from entity.models import (
    unitType, Entity, entity_details, entityfinancialyear, Constitution,
    entityconstitution, subentity, Rolepriv, Role, Userrole,
    GstAccountsdetails, Mastergstdetails,Bankdetails,GstRegitrationTypes,OwnerShipTypes
)
from import_export.admin import ImportExportMixin

# Admin classes
class UnitTypeAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['UnitName', 'UnitDesc']
    search_fields = ['UnitName', 'UnitDesc']
    list_per_page = 50

class GstRegitrationTypesAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['Name', 'Description']
    search_fields = ['Name', 'Description']
    list_per_page = 50

class OwnerShipTypesAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ['Name', 'Description']
    search_fields = ['Name', 'Description']
    list_per_page = 50


class EntityAdmin(admin.ModelAdmin):
    list_display = ['entityname', 'address']
    search_fields = ['entityname', 'address']
    list_per_page = 50

class SubEntityAdmin(admin.ModelAdmin):
    list_display = ['subentityname', 'address','entity']
    search_fields = ['subentityname', 'address']
    list_per_page = 50


class MenuAdmin(admin.ModelAdmin):
    list_display = ['role', 'submenu', 'entity']
    list_filter = [
        ('entity', admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = ['role', 'submenu']
    list_per_page = 50


class RoleAdmin(admin.ModelAdmin):
    list_display = ['rolename', 'roledesc', 'rolelevel', 'entity']
    list_filter = [
        ('entity', admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = ['rolename', 'roledesc']
    list_per_page = 50


class UserRoleAdmin(admin.ModelAdmin):
    list_display = ['entity', 'role', 'user']
    list_filter = [
        ('entity', admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = ['role__rolename', 'user__username']
    list_per_page = 50


class GstAccountAdmin(admin.ModelAdmin):
    list_display = ['gstin', 'tradeName', 'legalName']
    search_fields = ['gstin', 'tradeName', 'legalName']
    list_per_page = 50


# Register models with admin site
admin.site.register(unitType, UnitTypeAdmin)
admin.site.register(GstRegitrationTypes, GstRegitrationTypesAdmin)
admin.site.register(OwnerShipTypes, OwnerShipTypesAdmin)
admin.site.register(Entity, EntityAdmin)
admin.site.register(entity_details)
admin.site.register(entityfinancialyear)
admin.site.register(entityconstitution)
admin.site.register(Constitution)
admin.site.register(subentity,SubEntityAdmin)
admin.site.register(Rolepriv, MenuAdmin)
admin.site.register(Role, RoleAdmin)
admin.site.register(Userrole, UserRoleAdmin)
admin.site.register(GstAccountsdetails, GstAccountAdmin)
admin.site.register(Mastergstdetails)
admin.site.register(Bankdetails)
