from django.db import models
from django.db.models.deletion import CASCADE
from helpers.models import TrackingModel
from Authentication.models import User
from django.utils.translation import gettext as _
from entity.models import Entity,entityfinancialyear
from financial.models import account
import barcode                      # additional imports
from barcode.writer import ImageWriter
from io import BytesIO
from django.core.files import File
import os



class TransactionType(TrackingModel):
    transactiontype = models.CharField(max_length= 255,verbose_name=_('Transaction Type'))
    transactioncode = models.CharField(max_length= 2000,verbose_name=_('Transaction Code'))

    def __str__(self):
        return f'{self.transactiontype}'



