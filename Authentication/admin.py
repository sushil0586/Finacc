from django.contrib import admin
from Authentication.models import User,MainMenu,Submenu
from import_export.admin import ImportExportMixin


class submenusAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ('mainmenu', 'submenu','subMenuurl','order',)
    list_filter = (
        ('mainmenu', admin.RelatedOnlyFieldListFilter),
    )



class MainMenuAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ('mainmenu', 'menuurl','menucode','order',)


class userAdmin(ImportExportMixin,admin.ModelAdmin):
    list_display = ( 'id','username', 'email',)
   
admin.site.register(User,userAdmin)


admin.site.register(MainMenu,MainMenuAdmin)
admin.site.register(Submenu,submenusAdmin)




# Register your models here.
