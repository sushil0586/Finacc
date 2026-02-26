from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class TrackingModel(models.Model):
    """
    Common audit fields for non-transactional config tables too.
    """
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)s_created",
        editable=False,
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
        editable=False,
    )

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True


class EntityScopeQuerySet(models.QuerySet):
    def for_scope(self, *, entity_id: int, entityfinid_id: int | None = None, subentity_id: int | None = None):
        qs = self.filter(entity_id=entity_id)
        if entityfinid_id is not None:
            qs = qs.filter(entityfinid_id=entityfinid_id)
        # subentity can be NULL in your system → treat None as NULL match
        qs = qs.filter(subentity_id=subentity_id)
        return qs


class EntityScopedModel(TrackingModel):
    """
    Base model for transactional modules (Purchase/Sales/Inventory/Posting).

    Scope fields:
      - entity: tenant root
      - entityfinid: financial year (or finance book) scope
      - subentity: optional branch/plant/warehouse/entity unit

    Notes:
      - Keep 'subentity' nullable to allow entity-wide docs
      - All queries for business documents should filter by this scope
    """

    entity = models.ForeignKey(
        "entity.Entity",
        on_delete=models.PROTECT,
        related_name="%(class)s_entity",
        db_index=True,
    )

    # IMPORTANT: keep same field name you already use: entityfinid_id in your Purchase module
    entityfinid = models.ForeignKey(
        "entity.EntityFinancialYear",  # adjust if your model name differs
        on_delete=models.PROTECT,
        related_name="%(class)s_entityfin",
        db_index=True,
    )

    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)s_SubEntity",
        db_index=True,
    )

    objects = EntityScopeQuerySet.as_manager()

    class Meta:
        abstract = True
        indexes = [
            # Helps all list/search APIs
            models.Index(fields=["entity", "entityfinid", "subentity"], name="ix_%(class)s_scope"),
        ]

    # Optional: convenience for logging/debug
    def scope_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entityfinid_id": self.entityfinid_id,
            "subentity_id": self.subentity_id,
        }
