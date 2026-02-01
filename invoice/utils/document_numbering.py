# invoice/utils/document_numbering.py
from datetime import date
from django.shortcuts import get_object_or_404
from invoice.models import doctype
from django.db import transaction


def _maybe_reset(settings_obj, today: date) -> None:
    """
    Apply reset logic to settings_obj based on reset_frequency + last_reset_date.
    Update last_reset_date when reset happens.
    """
    freq = getattr(settings_obj, "reset_frequency", "none")
    last = getattr(settings_obj, "last_reset_date", None)

    if freq == "none":
        return

    if last is None:
        settings_obj.last_reset_date = today
        settings_obj.save(update_fields=["last_reset_date"])
        return

    if freq == "monthly":
        if (last.year, last.month) != (today.year, today.month):
            settings_obj.current_number = settings_obj.starting_number or 1
            settings_obj.last_reset_date = today
            settings_obj.save(update_fields=["current_number", "last_reset_date"])
        return

    if freq == "yearly":
        if last.year != today.year:
            settings_obj.current_number = settings_obj.starting_number or 1
            settings_obj.last_reset_date = today
            settings_obj.save(update_fields=["current_number", "last_reset_date"])
        return


def _format_doc_number(settings_obj, number: int, today: date) -> str:
    """
    Build formatted document number using either custom_format or prefix/year/month/padding/suffix.
    Placeholders supported: {prefix}, {year}, {month}, {number}, {suffix}
    """
    prefix = settings_obj.prefix or ""
    suffix = settings_obj.suffix or ""
    sep = settings_obj.separator or "-"
    pad = int(settings_obj.number_padding or 0)

    year = str(today.year)
    month = f"{today.month:02d}"

    num_str = str(number).zfill(pad) if pad > 0 else str(number)

    # Custom format takes priority
    custom = getattr(settings_obj, "custom_format", None)
    if custom:
        return custom.format(prefix=prefix, year=year, month=month, number=num_str, suffix=suffix)

    parts = [prefix]

    if getattr(settings_obj, "include_year", False):
        parts.append(year)

    if getattr(settings_obj, "include_month", False):
        parts.append(month)

    parts.append(num_str)

    if suffix:
        parts.append(suffix)

    # remove empty parts
    parts = [p for p in parts if p]
    return sep.join(parts)



