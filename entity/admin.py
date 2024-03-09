from io import UnsupportedOperation
from django.contrib import admin
from entity.models import unitType,Entity,entity_details,entityfinancialyear,Constitution,entityconstitution,subentity,Rolepriv,Role,Userrole,GstAccountsdetails


# Register your models here.



class unitTypeAdmin(admin.ModelAdmin):
    list_display = ['UnitName','UnitDesc','createdby']

class entityeAdmin(admin.ModelAdmin):
    list_display = ['entityname','address']

class menuadmin(admin.ModelAdmin):
    list_display = ['role','submenu','entity']
    list_filter = (
        ('entity', admin.RelatedOnlyFieldListFilter),
    )

class roleadmin(admin.ModelAdmin):
    list_display = ['role','submenu','entity']
    list_filter = (
        ('entity', admin.RelatedOnlyFieldListFilter),
    )

class rolesadmin(admin.ModelAdmin):
    list_display = ['rolename','roledesc','rolelevel','entity']
    list_filter = (
        ('entity', admin.RelatedOnlyFieldListFilter),
    )

class userrolesadmin(admin.ModelAdmin):
    list_display = ['entity','role','user']
    list_filter = (
        ('entity', admin.RelatedOnlyFieldListFilter),
    )

class gstaccountadmin(admin.ModelAdmin):
    list_display = ['gstin','tradeName','legalName']
    
    

admin.site.register(unitType,unitTypeAdmin)

admin.site.register(Entity,entityeAdmin)
admin.site.register(entity_details)
admin.site.register(entityfinancialyear)
admin.site.register(entityconstitution)
admin.site.register(Constitution)
admin.site.register(subentity)
admin.site.register(Rolepriv,menuadmin)
admin.site.register(Role,rolesadmin)
admin.site.register(Userrole,userrolesadmin)
admin.site.register(GstAccountsdetails,gstaccountadmin)



