# management/commands/load_default_options.py

from typing import Dict, List, Optional, Tuple
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Model
from django.utils.text import slugify

from payroll.models import OptionSet, Option
try:
    from entity.models import Entity
except Exception:
    Entity = None  # allow global-only loads if Entity app isn't installed

# Try importing TextChoices so we mirror them exactly if present
try:
    from payroll.models import EmployeeStatus, PayCycle
except Exception:
    EmployeeStatus = None
    PayCycle = None

# NEW: optional enums for these sets (import if you’ve defined them)
try:
    from payroll.models import TaxRegime
except Exception:
    TaxRegime = None
try:
    from payroll.models import ExitStatus
except Exception:
    ExitStatus = None
try:
    from payroll.models import PaymentPreference
except Exception:
    PaymentPreference = None
try:
    from payroll.models import WorkCalendar
except Exception:
    WorkCalendar = None


# --------------------------
# Base (non-enum) seed data
# --------------------------
DEFAULT_DATA: Dict[str, List[Tuple[str, str]]] = {
    # key: list of (code, label)
    "gender": [
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
    ],
    "employment_type": [
        ("permanent", "Permanent"),
        ("contract", "Contract"),
        ("intern", "Intern"),
        ("trainee", "Trainee"),
    ],
    "work_type": [
        ("onsite", "Onsite"),
        ("remote", "Remote"),
        ("hybrid", "Hybrid"),
    ],
    "marital_status": [
        ("single", "Single"),
        ("married", "Married"),
        ("divorced", "Divorced"),
        ("widowed", "Widowed"),
    ],
    "blood_group": [
        ("a_pos", "A+"),
        ("a_neg", "A-"),
        ("b_pos", "B+"),
        ("b_neg", "B-"),
        ("ab_pos", "AB+"),
        ("ab_neg", "AB-"),
        ("o_pos", "O+"),
        ("o_neg", "O-"),
    ],
    # These will be overridden from TextChoices if available
    "pay_cycle": [
        ("monthly", "Monthly"),
        ("weekly", "Weekly"),
    ],
    "employee_status": [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ],

    # NEW: sensible fallbacks if you don’t define TextChoices
    "tax_regime": [
        ("old", "Old Regime"),
        ("new", "New Regime"),
    ],
    "exit_status": [
        ("resignation", "Resignation"),
        ("termination", "Termination"),
        ("retirement", "Retirement"),
        ("absconded", "Absconded"),
        ("deceased", "Deceased"),
    ],
    "payment_preference": [
        ("bank_transfer", "Bank Transfer"),
        ("upi", "UPI"),
        ("cheque", "Cheque"),
        ("cash", "Cash"),
    ],
    "work_calendar": [
        ("ind_std", "India Standard"),
        ("five_day", "5-Day Week"),
        ("six_day", "6-Day Week"),
        ("shift_a", "Shift A"),
        ("shift_b", "Shift B"),
    ],

    "relationship": [
        ("father", "Father"),
        ("mother", "Mother"),
        ("spouse", "Spouse"),
        ("son", "Son"),
        ("daughter", "Daughter"),
        ("other", "Other"),
    ],
    "account_type": [
        ("savings", "Savings"),
        ("current", "Current"),
    ],
    "yes_no": [
        ("yes", "Yes"),
        ("no", "No"),
    ],
}



def _choices_from_textchoices(tc) -> List[Tuple[str, str]]:
    """Convert a Django TextChoices class into [(value, label), ...]."""
    return [(value, label) for value, label in getattr(tc, "choices", [])]


class Command(BaseCommand):
    help = (
        "Load default OptionSet/Option data.\n"
        "By default loads GLOBAL (entity=NULL) sets.\n"
        "Use --entity <id> to load for a specific entity.\n"
        "Use --only gender,employment_type to restrict which sets to load.\n"
        "Note: pay_cycle, employee_status, tax_regime, exit_status, payment_preference, work_calendar\n"
        "will mirror TextChoices if defined; otherwise defaults are used."
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, default=None,
                            help="Entity ID to load options for (omit for GLOBAL).")
        parser.add_argument("--only", type=str, default=None,
                            help="Comma-separated list of keys to load (e.g. 'gender,employment_type').")
        parser.add_argument("--reset", action="store_true",
                            help="Delete existing Options for targeted sets before reloading (scoped).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Print what would be done without writing to the DB.")

    def _get_entity(self, entity_id: Optional[int]) -> Optional[Model]:
        if entity_id is None:
            return None
        if Entity is None:
            raise CommandError("Entity model not available; cannot use --entity.")
        try:
            return Entity.objects.get(pk=entity_id)
        except Entity.DoesNotExist:
            raise CommandError(f"Entity id={entity_id} not found.")

    def _build_data(self) -> Dict[str, List[Tuple[str, str]]]:
        """
        Start from DEFAULT_DATA, then override from TextChoices so they always match your enums exactly.
        Keys aligned to your limit_choices_to keys:
          - pay_cycle           → PayCycle
          - employee_status     → EmployeeStatus
          - tax_regime          → TaxRegime
          - exit_status         → ExitStatus
          - payment_preference  → PaymentPreference
          - work_calendar       → WorkCalendar
        """
        data = {k: list(v) for k, v in DEFAULT_DATA.items()}  # shallow copy

        if PayCycle is not None:
            data["pay_cycle"] = _choices_from_textchoices(PayCycle)
        if EmployeeStatus is not None:
            data["employee_status"] = _choices_from_textchoices(EmployeeStatus)

        # NEW overrides if enums exist
        if TaxRegime is not None:
            data["tax_regime"] = _choices_from_textchoices(TaxRegime)
        if ExitStatus is not None:
            data["exit_status"] = _choices_from_textchoices(ExitStatus)
        if PaymentPreference is not None:
            data["payment_preference"] = _choices_from_textchoices(PaymentPreference)
        if WorkCalendar is not None:
            data["work_calendar"] = _choices_from_textchoices(WorkCalendar)

        return data

    @transaction.atomic
    def handle(self, *args, **options):
        entity_id = options.get("entity")
        only = options.get("only")
        reset = options.get("reset")
        dry_run = options.get("dry_run")

        entity = self._get_entity(entity_id)
        scope = f"ENTITY:{entity.id}" if entity else "GLOBAL"

        merged_data = self._build_data()

        if only:
            keys = {k.strip() for k in only.split(",") if k.strip()}
            data = {k: v for k, v in merged_data.items() if k in keys}
            missing = keys - set(data.keys())
            if missing:
                self.stdout.write(self.style.WARNING(f"Unknown keys ignored: {sorted(missing)}"))
        else:
            data = merged_data

        if not data:
            self.stdout.write(self.style.WARNING("Nothing to load (no matching keys)."))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(f"Loading default options for {scope}"))
        if reset:
            self.stdout.write(self.style.WARNING("RESET mode: existing options for targeted sets will be deleted."))

        for key, items in data.items():
            # upsert OptionSet
            if dry_run:
                self.stdout.write(f"[dry-run] Ensure OptionSet key='{key}' entity={entity.id if entity else 'NULL'}")
                set_obj = None
            else:
                set_obj, created = OptionSet.objects.get_or_create(
                    entity=entity,
                    key=key,
                    defaults={},
                )
                self.stdout.write(("%s OptionSet: %s" % ("Created" if created else "Found", key)))

            # optional reset of options under this set (scoped)
            if reset and not dry_run and set_obj:
                Option.objects.filter(set=set_obj).delete()
                self.stdout.write(self.style.WARNING(f"Cleared existing options for set '{key}'"))

            # insert/update options
            for idx, (code, label) in enumerate(items):
                sort_order = idx  # stable, 0-based
                norm_code = slugify(code).replace("-", "_") or code

                if dry_run:
                    self.stdout.write(
                        f"[dry-run]  - upsert Option code='{norm_code}' label='{label}' sort={sort_order} active=True"
                    )
                    continue

                opt, created = Option.objects.get_or_create(
                    set=set_obj,
                    code=norm_code,
                    defaults={
                        "label": label,
                        "sort_order": sort_order,
                        "is_active": True,
                        "extra": {},
                    },
                )
                changed = False
                if opt.label != label:
                    opt.label = label
                    changed = True
                if opt.sort_order != sort_order:
                    opt.sort_order = sort_order
                    changed = True
                if not opt.is_active:
                    opt.is_active = True
                    changed = True
                if changed:
                    opt.save()
                    self.stdout.write(f"  Updated Option: {norm_code}")
                else:
                    if created:
                        self.stdout.write(f"  Created Option: {norm_code}")
                    else:
                        self.stdout.write(f"  Kept Option:    {norm_code}")

        self.stdout.write(self.style.SUCCESS("Default options load complete."))
