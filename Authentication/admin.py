from django.contrib import admin
from Authentication.models import User,userRole,MainMenu,submenu,rolepriv

admin.site.register(User)

admin.site.register(userRole)
admin.site.register(MainMenu)
admin.site.register(submenu)
admin.site.register(rolepriv)

# Register your models here.
