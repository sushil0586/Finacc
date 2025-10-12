# numbering/management/commands/seed_doc_sequences.py
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from numbering.models import DocumentSequenceSettings
from financial.models import doctype  # adjust import to your project
from master.models import Entity, entityfinancialyear, subentity  # adjust paths

DEFAULT_DOCTYPE_CODES = {
    # code      prefix   reset     pad include_year include_month
    "SI": ("INV",  "yearly", 5, True,  False),  # Sales Invoice
    "SR": ("SR",   "yearly", 5, True,  False),  # Sales Return
    "PI": ("PINV", "yearly", 5, True,  False),  # Purchase Invoice
    "PR": ("PR",   "yearly", 5, True,  False),  # Purchase Return
    "RC": ("RCPT", "yearly", 5, True,  False),  # Receipt
    "PM": ("PMT",  "yearly", 5, True,  False),  # Payment
    "JV": ("JV",   "yearly", 5, True,  False),  # Journal
}

# For which doctypes we want series rows
DEFAULT_SERIES = {
    # code: list of series keys
    "RC": ["CASH", "BANK"],
    "PM": ["CASH", "BANK"],
    # others typically don't need series by default
}

def get_doctype_obj(code: str):
    try:
        return doctype.objects.get(code=code)
    except doctype.DoesNotExist:
        raise CommandError(f"Doctype with code='{code}' not found. Please seed doctypes first.")


class Command(BaseCommand):
    help = "Seed default document sequences for a given entity & financial year (and optional subentity)."

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID")
        parser.add_argument("--finyear", type=int, required=True, help="entityfinancialyear ID")
        parser.add_argument("--subentity", type=int, default=None, help="Optional subentity ID")
        parser.add_argument("--start", type=int, default=1, help="Starting number (default 1)")
        parser.add_argument("--intstart", type=int, default=1, help="Starting integer counter (default 1)")
        parser.add_argument("--yearly", action="store_true", help="Force yearly reset for all")
        parser.add_argument("--monthly", action="store_true", help="Force monthly reset for all")
        parser.add_argument("--preview", action="store_true", help="Preview only (no writes)")

    @transaction.atomic
    def handle(self, *args, **opts):
        ent_id = opts["entity"]
        fy_id = opts["finyear"]
        sub_id = opts.get("subentity")
        start = opts["start"]
        intstart = opts["intstart"]
        preview = opts["preview"]

        reset_policy = "none"
        if opts["yearly"]:
            reset_policy = "yearly"
        elif opts["monthly"]:
            reset_policy = "monthly"

        try:
            ent = Entity.objects.get(id=ent_id)
        except Entity.DoesNotExist:
            raise CommandError(f"Entity id={ent_id} not found.")

        try:
            fin = entityfinancialyear.objects.get(id=fy_id)
        except entityfinancialyear.DoesNotExist:
            raise CommandError(f"entityfinancialyear id={fy_id} not found.")

        se = None
        if sub_id:
            try:
                se = subentity.objects.get(id=sub_id)
            except subentity.DoesNotExist:
                raise CommandError(f"subentity id={sub_id} not found.")

        created = 0
        skipped = 0
        today = timezone.localdate()
        year_key  = f"{today:%Y}"
        month_key = f"{today:%Y}{today:%m}"

        for code, (prefix, default_reset, pad, inc_year, inc_month) in DEFAULT_DOCTYPE_CODES.items():
            dt = get_doctype_obj(code)
            series_list = DEFAULT_SERIES.get(code, [None])  # None creates a row without series_key

            for series_key in series_list:
                obj, is_new = DocumentSequenceSettings.objects.get_or_create(
                    entity=ent, entityfinid=fin, subentity=se, doctype=dt, series_key=series_key,
                    defaults=dict(
                        starting_number=start,
                        current_number=start,
                        next_integer=intstart,
                        prefix=prefix,
                        suffix="",
                        number_padding=pad,
                        include_year=inc_year,
                        include_month=inc_month,
                        separator="-",
                        reset_frequency=reset_policy if reset_policy != "none" else default_reset,
                        last_reset_key=year_key if (reset_policy == "yearly" or default_reset == "yearly") else (
                            month_key if (reset_policy == "monthly" or default_reset == "monthly") else None
                        ),
                        last_reset_date=today,
                        custom_format="",  # use default join format
                    )
                )
                if is_new:
                    created += 1
                    self.stdout.write(self.style.SUCCESS(
                        f"Created {code} seq (series={series_key or '-'}) for Entity={ent_id}, FY={fy_id}."
                    ))
                else:
                    skipped += 1
                    self.stdout.write(self.style.WARNING(
                        f"Exists {code} seq (series={series_key or '-'}) for Entity={ent_id}, FY={fy_id} — skipped."
                    ))

                if preview:
                    raise CommandError("Preview mode aborts transaction intentionally (no writes).")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created={created}, Skipped={skipped} for Entity={ent_id}, FY={fy_id}."
        ))
