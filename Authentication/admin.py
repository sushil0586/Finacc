from django.contrib import admin
from Authentication.models import User,MainMenu,Submenu,AuthSession,AuthAuditLog,AuthOTP
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


@admin.register(AuthSession)
class AuthSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "session_key", "issued_at", "expires_at", "refresh_expires_at", "revoked_at", "ip_address")
    search_fields = ("user__email", "session_key", "jti")
    list_filter = ("revoked_at",)


@admin.register(AuthAuditLog)
class AuthAuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event", "email", "user", "ip_address")
    search_fields = ("email", "user__email", "event")
    list_filter = ("event",)


@admin.register(AuthOTP)
class AuthOTPAdmin(admin.ModelAdmin):
    list_display = ("email", "purpose", "code", "expires_at", "consumed_at", "attempts")
    search_fields = ("email", "code")
    list_filter = ("purpose", "consumed_at")


admin.site.register(User,userAdmin)


admin.site.register(MainMenu,MainMenuAdmin)
admin.site.register(Submenu,submenusAdmin)




# Register your models here.
