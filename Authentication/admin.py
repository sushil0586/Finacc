from django.contrib import admin
from Authentication.models import User,userRole,MainMenu,submenu,rolepriv


class submenusAdmin(admin.ModelAdmin):
    list_display = ('mainmenu', 'submenu','subMenuurl','order',)
    list_filter = (
        ('mainmenu', admin.RelatedOnlyFieldListFilter),
    )

admin.site.register(User)

admin.site.register(userRole)
admin.site.register(MainMenu)
admin.site.register(submenu,submenusAdmin)
admin.site.register(rolepriv)



# Register your models here.
