from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget

from .models import Language, LocalizedStringKey, LocalizedStringValue
from entity.models import Entity  # adjust app import


class LanguageResource(resources.ModelResource):
    class Meta:
        model = Language
        import_id_fields = ("code",)
        fields = ("code", "name", "is_active", "sort_order")
        skip_unchanged = True
        report_skipped = True


class LocalizedStringKeyResource(resources.ModelResource):
    class Meta:
        model = LocalizedStringKey
        import_id_fields = ("key",)
        fields = ("key", "module", "description", "default_text", "is_active", "is_system")
        skip_unchanged = True
        report_skipped = True


class LocalizedStringValueResource(resources.ModelResource):
    string_key = fields.Field(
        column_name="string_key",
        attribute="string_key",
        widget=ForeignKeyWidget(LocalizedStringKey, "key"),
    )
    language = fields.Field(
        column_name="language",
        attribute="language",
        widget=ForeignKeyWidget(Language, "code"),
    )
    entity = fields.Field(
        column_name="entity",
        attribute="entity",
        widget=ForeignKeyWidget(Entity, "entityname"),
    )

    class Meta:
        model = LocalizedStringValue
        import_id_fields = ("string_key", "language", "entity")
        fields = ("string_key", "language", "entity", "text", "is_approved")
        skip_unchanged = True
        report_skipped = True

    def before_import_row(self, row, **kwargs):
        # blank entity means global translation
        if "entity" in row and (row["entity"] is None or str(row["entity"]).strip() == ""):
            row["entity"] = None

    def dehydrate_entity(self, obj):
        return obj.entity.entityname if obj.entity else ""
