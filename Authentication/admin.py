from django.contrib import admin
from Authentication.models import User,userRole,MainMenu,Submenu,rolepriv
from import_export.admin import ImportExportMixin


class submenusAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ('mainmenu', 'submenu','subMenuurl','order',)
    list_filter = (
        ('mainmenu', admin.RelatedOnlyFieldListFilter),
    )

class userRoleAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ('rolename', 'roledesc',)
    # list_filter = (
    #     ('entity', admin.RelatedOnlyFieldListFilter),
    # )

class MainMenuAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ('rolename', 'roledesc','entity',)
    list_filter = (
        ('entity', admin.RelatedOnlyFieldListFilter),
    )

admin.site.register(User)

admin.site.register(userRole,userRoleAdmin)
admin.site.register(MainMenu)
admin.site.register(Submenu,submenusAdmin)
admin.site.register(rolepriv)



# Register your models here.
