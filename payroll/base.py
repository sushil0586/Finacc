from django.db import models
from django.utils import timezone

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True,null = True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    class Meta:
        abstract = True

class EffectiveDatedModel(models.Model):
    effective_from = models.DateField(db_index=True)
    effective_to = models.DateField(null=True, blank=True, db_index=True)
    class Meta:
        abstract = True
    @property
    def is_active(self):
        today = timezone.localdate()
        return self.effective_from <= today and (self.effective_to is None or today <= self.effective_to)
