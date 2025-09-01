from django.db import models
from .base import TimeStampedModel
from entity.models import Entity


class BusinessUnit(TimeStampedModel):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="business_units")
    name = models.CharField(max_length=128)
    class Meta: unique_together = [("entity", "name")]
    def __str__(self): return f"{self.entity.entityname}:{self.name}"

class Department(TimeStampedModel):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="departments", null=True)
    name   = models.CharField(max_length=128, null=True, blank=True)

    class Meta:
        # temporarily remove unique_together to break the bad op chain
        # unique_together = [("entity", "name")]
        pass

    def __str__(self):
        return f"{self.entity.entityname}:{self.name}"


class Location(TimeStampedModel):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="locations")
    name = models.CharField(max_length=128)
    city = models.CharField(max_length=128, blank=True, default="")
    state = models.CharField(max_length=128, blank=True, default="")
    country = models.CharField(max_length=128, blank=True, default="India")
    class Meta: unique_together = [("entity", "name")]
    def __str__(self): return f"{self.entity.entityname}:{self.name}"

class CostCenter(TimeStampedModel):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="cost_centers")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=128)
    class Meta: unique_together = [("entity", "code")]
    def __str__(self): return f"{self.entity.entityname}:{self.code} — {self.name}"
