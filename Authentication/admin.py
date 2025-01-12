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
   

admin.site.register(User)


admin.site.register(MainMenu,MainMenuAdmin)
admin.site.register(Submenu,submenusAdmin)




# Register your models here.
