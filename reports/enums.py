# common/enums.py
from django.db import models


class StockValuationMethod(models.TextChoices):
    FIFO = "FIFO", "FIFO (First In First Out)"
    WAVG = "WAVG", "Weighted Average"
    STANDARD = "STANDARD", "Standard Cost"


class NegativeValuationPolicy(models.TextChoices):
    LAST_COST = "LAST_COST", "Last Known Cost"
    ZERO = "ZERO", "Zero Value"
    STANDARD_COST = "STANDARD_COST", "Standard Cost"
    ERROR = "ERROR", "Raise Error"
