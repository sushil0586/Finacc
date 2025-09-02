from typing import Dict, List, Optional, Tuple
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Model
from django.utils.text import slugify

# Adjust imports to your project layout:
from payroll.models import OptionSet, Option
try:
    # If Entity lives in another app, change this import accordingly
    from entity.models import Entity
except Exception:
    Entity = None  # allow global-only loads if Entity app isn't installed


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
    "pay_cycle": [
        ("monthly", "Monthly"),
        ("weekly", "Weekly"),
        ("biweekly", "Bi-Weekly"),
        ("semimonthly", "Semi-Monthly"),
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
    "employee_status": [
        ("active", "Active"),
        ("probation", "Probation"),
        ("inactive", "Inactive"),
        ("resigned", "Resigned"),
        ("terminated", "Terminated"),
    ],
}


class Command(BaseCommand):
    help = (
        "Load default OptionSet/Option data. "
        "By default loads GLOBAL (entity=NULL) sets. "
        "Use --entity <id> to load for a specific entity. "
        "Use --only gender,employment_type to restrict which sets to load."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--entity",
            type=int,
            default=None,
            help="Entity ID to load options for (omit for GLOBAL).",
        )
        parser.add_argument(
            "--only",
            type=str,
            default=None,
            help="Comma-separated list of keys to load (e.g. 'gender,employment_type').",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="If provided, deletes existing Options for the targeted sets before reloading (only within the targeted entity/global).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be done without writing to the DB.",
        )

    def _get_entity(self, entity_id: Optional[int]) -> Optional[Model]:
        if entity_id is None:
            return None
        if Entity is None:
            raise CommandError("Entity model not available; cannot use --entity.")
        try:
            return Entity.objects.get(pk=entity_id)
        except Entity.DoesNotExist:
            raise CommandError(f"Entity id={entity_id} not found.")

    @transaction.atomic
    def handle(self, *args, **options):
        entity_id = options.get("entity")
        only = options.get("only")
        reset = options.get("reset")
        dry_run = options.get("dry_run")

        entity = self._get_entity(entity_id)
        scope = f"ENTITY:{entity.id}" if entity else "GLOBAL"

        # pick data
        data = DEFAULT_DATA
        if only:
            keys = {k.strip() for k in only.split(",") if k.strip()}
            data = {k: v for k, v in DEFAULT_DATA.items() if k in keys}
            missing = keys - set(data.keys())
            if missing:
                self.stdout.write(self.style.WARNING(f"Unknown keys ignored: {sorted(missing)}"))

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
                set_obj = None  # placeholder
            else:
                set_obj, created = OptionSet.objects.get_or_create(
                    entity=entity,
                    key=key,
                    defaults={},
                )
                self.stdout.write(("%s OptionSet: %s" % ("Created" if created else "Found", key)))

            # optional reset of options under this set (scoped to this set only)
            if reset and not dry_run:
                Option.objects.filter(set=set_obj).delete()
                self.stdout.write(self.style.WARNING(f"Cleared existing options for set '{key}'"))

            # insert/update options
            for idx, (code, label) in enumerate(items):
                sort_order = idx  # stable, 0-based
                norm_code = slugify(code).replace("-", "_") or code  # keep simple, underscore-safe

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
                # keep label & order up to date on re-runs
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
