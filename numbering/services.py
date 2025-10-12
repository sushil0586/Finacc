# numbering/services.py
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from numbering.models import DocumentSequenceSettings, DocumentType
from entity.models import entityfinancialyear  # adjust if your app label differs

# Defaults; tweak as you like
DEFAULT_DOCTYPE_DEFS = {
    # code: (name, prefix, default_reset, padding, include_year, include_month)
    "SI": ("Sales Invoice",       "INV",  "yearly", 5, True,  False),
    "SR": ("Sales Return",        "SR",   "yearly", 5, True,  False),
    "PI": ("Purchase Invoice",    "PINV", "yearly", 5, True,  False),
    "PR": ("Purchase Return",     "PR",   "yearly", 5, True,  False),
    "RC": ("Receipt",             "RCPT", "yearly", 5, True,  False),
    "PM": ("Payment",             "PMT",  "yearly", 5, True,  False),
    "JV": ("Journal Voucher",     "JV",   "yearly", 5, True,  False),
}

DEFAULT_SERIES = {
    "RC": ["CASH", "BANK"],  # separate sequences for receipts
    "PM": ["CASH", "BANK"],  # separate sequences for payments
}

def _get_or_create_doctype(doccode: str, entity=None) -> DocumentType:
    """
    Prefer an entity-scoped DocumentType; fall back to global; create global if missing.
    """
    doccode = (doccode or "").strip().upper()
    dt = None
    if entity:
        dt = DocumentType.objects.filter(doccode=doccode, entity=entity).first()
    if not dt:
        dt = DocumentType.objects.filter(doccode=doccode, entity__isnull=True).first()
    if not dt:
        name = DEFAULT_DOCTYPE_DEFS.get(doccode, (doccode, "", "none", 0, False, False))[0]
        dt = DocumentType.objects.create(doccode=doccode, docname=name, entity=None, createdby=None)
    return dt

def active_fy_for_entity(entity):
    # choose active/latest FY — adjust if you track an "active" flag
    return entityfinancialyear.objects.filter(entity=entity).order_by("-id").first()

@transaction.atomic
def seed_sequences_for_entity(entity, finyear=None, subentity=None,
                              start=1, intstart=1, override_reset: str | None = None):
    """
    Create default sequences (idempotent) for an entity (+FY, optional subentity).
    Returns (created_count, skipped_count, message)
    """
    fin = finyear or active_fy_for_entity(entity)
    if not fin:
        raise ValueError("No financial year found for this entity.")

    created = skipped = 0
    today = timezone.localdate()
    year_key  = f"{today:%Y}"
    month_key = f"{today:%Y}{today:%m}"

    for code, (name, prefix, default_reset, pad, inc_year, inc_month) in DEFAULT_DOCTYPE_DEFS.items():
        dt = _get_or_create_doctype(code, entity=entity)
        series_list = DEFAULT_SERIES.get(code, [None])

        for series_key in series_list:
            reset = override_reset if override_reset else default_reset
            last_key = year_key if reset == "yearly" else (month_key if reset == "monthly" else None)

            obj, is_new = DocumentSequenceSettings.objects.get_or_create(
                entity=entity, entityfinid=fin, subentity=subentity, doctype=dt, series_key=series_key,
                defaults=dict(
                    starting_number=start, current_number=start, next_integer=intstart,
                    prefix=prefix, suffix="", number_padding=pad,
                    include_year=inc_year, include_month=inc_month, separator="-",
                    reset_frequency=reset, last_reset_key=last_key, last_reset_date=today,
                    custom_format="",
                )
            )
            if is_new:
                created += 1
            else:
                skipped += 1

    return created, skipped, f"Sequences ready for FY={fin.id}"
