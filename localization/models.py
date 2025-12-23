from django.db import models

# Create your models here.
from django.db import models


class Language(models.Model):
    code = models.CharField(max_length=20, unique=True)  # en, hi, en-IN
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.code})"


class LocalizedStringKey(models.Model):
    key = models.CharField(max_length=200, unique=True, db_index=True)  # common.save
    module = models.CharField(max_length=80, blank=True, db_index=True)  # invoice, reports
    description = models.CharField(max_length=500, blank=True)
    default_text = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=True)  # seeded vs user-created
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


class LocalizedStringValue(models.Model):
    string_key = models.ForeignKey(
        LocalizedStringKey, on_delete=models.CASCADE, related_name="translations"
    )
    language = models.ForeignKey(Language, on_delete=models.PROTECT)

    # Optional multi-entity override:
   # entity_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    # If you have Entity model, replace above with:
    entity = models.ForeignKey("entity.Entity", on_delete=models.CASCADE, null=True, blank=True)

    text = models.TextField()
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["string_key", "language", "entity_id"],
                name="uq_localized_value_key_lang_entity",
            )
        ]
        indexes = [
            models.Index(fields=["language", "entity_id"]),
        ]

    def __str__(self):
        scope = f"entity={self.entity_id}" if self.entity_id else "global"
        return f"{self.string_key.key} [{self.language.code}] ({scope})"
