from typing import Dict, List, Tuple, Optional
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

# Adjust imports if your app names differ
from payroll.models import BusinessUnit, Department, Location, CostCenter
from entity.models import Entity


# ---- Defaults (edit to taste) ----
DEFAULT_BUSINESS_UNITS: List[str] = [
    "Head Office", "Sales", "Operations", "Human Resources", "Finance", "IT", "R&D",
]

DEFAULT_DEPARTMENTS: List[str] = [
    "Administration", "Sales", "Marketing", "Finance", "Human Resources",
    "Engineering", "Support", "Operations", "Procurement", "Logistics",
]

# name, city, state, country
DEFAULT_LOCATIONS: List[Tuple[str, str, str, str]] = [
    ("HQ", "New Delhi", "Delhi", "India"),
    ("Mumbai Office", "Mumbai", "Maharashtra", "India"),
    ("Bengaluru Office", "Bengaluru", "Karnataka", "India"),
    ("Hyderabad Office", "Hyderabad", "Telangana", "India"),
]

# code, name
DEFAULT_COST_CENTERS: List[Tuple[str, str]] = [
    ("ADM", "Administration"),
    ("HR",  "Human Resources"),
    ("FIN", "Finance"),
    ("SAL", "Sales"),
    ("MKT", "Marketing"),
    ("OPS", "Operations"),
    ("IT",  "Information Technology"),
    ("RND", "Research & Development"),
]


CHOICE_KEYS = {
    "business_unit": {"business_unit", "business_units", "bu", "bunit"},
    "department":    {"department", "departments", "dept"},
    "location":      {"location", "locations", "loc"},
    "cost_center":   {"cost_center", "cost_centers", "cc", "costcentre", "cost_centres"},
}


class Command(BaseCommand):
    help = (
        "Load default masters for an Entity: BusinessUnit, Department, Location, CostCenter.\n"
        "Usage examples:\n"
        "  python manage.py load_default_masters --entity 1\n"
        "  python manage.py load_default_masters --entity 1 --only bu,dept\n"
        "  python manage.py load_default_masters --entity 1 --reset\n"
        "  python manage.py load_default_masters --entity 1 --dry-run\n"
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True,
                            help="Entity ID to load data for (required).")
        parser.add_argument("--only", type=str, default=None,
                            help="Comma list to restrict which sets to load. "
                                 "Accepted: business_unit(bu), department(dept), location(loc), cost_center(cc)")
        parser.add_argument("--reset", action="store_true",
                            help="Delete existing rows for the targeted sets (for this entity) before loading.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Print actions without writing to DB.")

    def _parse_only(self, only: Optional[str]) -> Dict[str, bool]:
        """Return which groups to load based on --only."""
        keys = {"business_unit": True, "department": True, "location": True, "cost_center": True}
        if not only:
            return keys
        wanted = {p.strip().lower() for p in only.split(",") if p.strip()}
        # resolve synonyms
        resolved = {k: any(x in wanted for x in CHOICE_KEYS[k]) for k in keys}
        if not any(resolved.values()):
            raise CommandError("No valid names in --only. "
                               f"Use any of: {', '.join(sorted(sum((list(v) for v in CHOICE_KEYS.values()), [])))}")
        return resolved

    def _get_entity(self, entity_id: int) -> Entity:
        try:
            return Entity.objects.get(pk=entity_id)
        except Entity.DoesNotExist:
            raise CommandError(f"Entity id={entity_id} not found.")

    @transaction.atomic
    def handle(self, *args, **opts):
        entity = self._get_entity(opts["entity"])
        only = self._parse_only(opts["only"])
        reset = opts["reset"]
        dry_run = opts["dry_run"]

        self.stdout.write(self.style.MIGRATE_HEADING(f"Loading masters for ENTITY:{entity.id}"))

        if only["business_unit"]:
            self._load_business_units(entity, reset=reset, dry_run=dry_run)
        if only["department"]:
            self._load_departments(entity, reset=reset, dry_run=dry_run)
        if only["location"]:
            self._load_locations(entity, reset=reset, dry_run=dry_run)
        if only["cost_center"]:
            self._load_cost_centers(entity, reset=reset, dry_run=dry_run)

        self.stdout.write(self.style.SUCCESS("Master data load complete."))

    # ---------- Loaders ----------

    def _load_business_units(self, entity: Entity, reset: bool, dry_run: bool):
        self.stdout.write(self.style.HTTP_INFO("BusinessUnit"))
        if reset and not dry_run:
            BusinessUnit.objects.filter(entity=entity).delete()
            self.stdout.write(self.style.WARNING("  Reset: deleted existing BusinessUnit rows for this entity."))

        for name in DEFAULT_BUSINESS_UNITS:
            clean = name.strip()
            if dry_run:
                self.stdout.write(f"  [dry-run] upsert BU name='{clean}'")
                continue
            bu, created = BusinessUnit.objects.get_or_create(entity=entity, name=clean)
            self.stdout.write(f"  {'Created' if created else 'Kept'}: {clean}")

    def _load_departments(self, entity: Entity, reset: bool, dry_run: bool):
        self.stdout.write(self.style.HTTP_INFO("Department"))
        if reset and not dry_run:
            Department.objects.filter(entity=entity).delete()
            self.stdout.write(self.style.WARNING("  Reset: deleted existing Department rows for this entity."))

        for name in DEFAULT_DEPARTMENTS:
            clean = name.strip()
            if dry_run:
                self.stdout.write(f"  [dry-run] upsert Department name='{clean}'")
                continue
            dep, created = Department.objects.get_or_create(entity=entity, name=clean)
            self.stdout.write(f"  {'Created' if created else 'Kept'}: {clean}")

    def _load_locations(self, entity: Entity, reset: bool, dry_run: bool):
        self.stdout.write(self.style.HTTP_INFO("Location"))
        if reset and not dry_run:
            Location.objects.filter(entity=entity).delete()
            self.stdout.write(self.style.WARNING("  Reset: deleted existing Location rows for this entity."))

        for name, city, state, country in DEFAULT_LOCATIONS:
            if dry_run:
                self.stdout.write(
                    f"  [dry-run] upsert Location name='{name}', city='{city}', state='{state}', country='{country}'"
                )
                continue
            loc, created = Location.objects.get_or_create(
                entity=entity,
                name=name.strip(),
                defaults={"city": city.strip(), "state": state.strip(), "country": country.strip()},
            )
            changed = False
            if loc.city != city:
                loc.city = city
                changed = True
            if loc.state != state:
                loc.state = state
                changed = True
            if loc.country != country:
                loc.country = country
                changed = True
            if changed and not dry_run:
                loc.save()
                self.stdout.write(f"  Updated: {name}")
            else:
                self.stdout.write(f"  {'Created' if created else 'Kept'}: {name}")

    def _load_cost_centers(self, entity: Entity, reset: bool, dry_run: bool):
        self.stdout.write(self.style.HTTP_INFO("CostCenter"))
        if reset and not dry_run:
            CostCenter.objects.filter(entity=entity).delete()
            self.stdout.write(self.style.WARNING("  Reset: deleted existing CostCenter rows for this entity."))

        for code, name in DEFAULT_COST_CENTERS:
            # Keep codes uppercase & underscore-safe
            norm_code = slugify(code, allow_unicode=False).upper().replace("-", "_")
            if not norm_code:
                norm_code = code.upper()

            if dry_run:
                self.stdout.write(f"  [dry-run] upsert CostCenter code='{norm_code}', name='{name}'")
                continue

            cc, created = CostCenter.objects.get_or_create(
                entity=entity,
                code=norm_code,
                defaults={"name": name.strip()},
            )
            if not created and cc.name != name.strip():
                cc.name = name.strip()
                cc.save()
                self.stdout.write(f"  Updated: {norm_code} — {cc.name}")
            else:
                self.stdout.write(f"  {'Created' if created else 'Kept'}: {norm_code} — {cc.name}")
