from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class HrmsQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, deleted_at__isnull=True)

    def inactive(self):
        return self.filter(is_active=False, deleted_at__isnull=True)

    def deleted(self):
        return self.filter(deleted_at__isnull=False)

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def for_entity(self, *, entity_id, subentity_id=None):
        queryset = self.filter(entity_id=entity_id)
        if subentity_id is not None:
            queryset = queryset.filter(models.Q(subentity_id=subentity_id) | models.Q(subentity__isnull=True))
        return queryset

    def soft_delete(self, *, deleted_by=None):
        timestamp = timezone.now()
        return self.update(
            is_active=False,
            deleted_at=timestamp,
            deleted_by=deleted_by,
            updated_at=timestamp,
        )


class HrmsManager(models.Manager.from_queryset(HrmsQuerySet)):
    def get_queryset(self):
        return HrmsQuerySet(self.model, using=self._db).alive()


class AllHrmsManager(models.Manager.from_queryset(HrmsQuerySet)):
    def get_queryset(self):
        return HrmsQuerySet(self.model, using=self._db)


class HrmsBaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField(default=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="%(class)s_hrms_created",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="%(class)s_hrms_updated",
    )
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        editable=False,
        related_name="%(class)s_hrms_deleted",
    )

    objects = HrmsManager()
    all_objects = AllHrmsManager()

    class Meta:
        abstract = True

    def soft_delete(self, *, user=None, save=True):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.deleted_by = user
        if save:
            self.save(update_fields=["is_active", "deleted_at", "deleted_by", "updated_at"])


class EntityScopedHrmsModel(HrmsBaseModel):
    entity = models.ForeignKey(
        "entity.Entity",
        on_delete=models.PROTECT,
        related_name="%(class)s_hrms_entity",
        db_index=True,
    )
    subentity = models.ForeignKey(
        "entity.SubEntity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)s_hrms_subentity",
        db_index=True,
    )

    class Meta:
        abstract = True
