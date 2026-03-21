from django.urls import path

from posting import views

app_name = "posting"

urlpatterns = [
    path(
        "entities/<int:entity_id>/static-account-settings/",
        views.StaticAccountSettingsView.as_view(),
        name="static-account-settings",
    ),
    path(
        "entities/<int:entity_id>/static-account-settings/validate/",
        views.StaticAccountSettingsValidateView.as_view(),
        name="static-account-settings-validate",
    ),
    path(
        "entities/<int:entity_id>/static-account-settings/bulk-upsert/",
        views.StaticAccountSettingsBulkUpsertView.as_view(),
        name="static-account-settings-bulk-upsert",
    ),
    path(
        "entities/<int:entity_id>/static-account-settings/<str:static_account_code>/",
        views.StaticAccountSettingDetailView.as_view(),
        name="static-account-settings-detail",
    ),
]
