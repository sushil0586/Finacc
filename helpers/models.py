from django.db import models



class TrackingModel(models.Model):
    created_at = models.DateTimeField(auto_now_add = True,null=True,blank=True)
    updated_at = models.DateTimeField(auto_now = True)
    isactive =   models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ('created_at',)