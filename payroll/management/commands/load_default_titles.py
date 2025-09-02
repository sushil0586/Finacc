from typing import List, Tuple
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from payroll.models import GradeBand, Designation, OptionSet, Option
from entity.models import Entity

DEFAULT_GRADE_BANDS: List[Tuple[str, str, int]] = [
    # code, name, level
    ("L1", "Junior",            10),
    ("L2", "Associate",         20),
    ("L3", "Senior",            30),
    ("M1", "Manager",           40),
    ("M2", "Senior Manager",    50),
    ("D1", "Director",          60),
]

DEFAULT_DESIGNATIONS: List[Tuple[str, str]] = [
    # name, grade_code
    ("Software Engineer", "L2"),
    ("Senior Software Engineer", "L3"),
    ("Lead Engineer", "M1"),
    ("Engineering Manager", "M1"),
    ("Senior Engineering Manager", "M2"),
    ("Accountant", "L2"),
    ("Senior Accountant", "L3"),
    ("HR Executive", "L2"),
    ("HR Manager", "M1"),
]

class Command(BaseCommand):
    help = (
        "Load default GradeBand and Designation for an entity. "
        "Optionally mirror to OptionSet/Option with keys 'grade_band' and 'designation'."
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity", type=int, required=True, help="Entity ID.")
        parser.add_argument("--reset", action="store_true", help="Delete existing grades/designations for this entity before loading.")
        parser.add_argument("--dry-run", action="store_true", help="No writes; show actions.")
        parser.add_argument("--mirror-to-options", action="store_true", help="Also create/update OptionSet/Option.")
        parser.add_argument("--reset-options", action="store_true", help="When mirroring, delete existing options in those sets first.")

    def _entity(self, entity_id: int) -> Entity:
        try:
            return Entity.objects.get(pk=entity_id)
        except Entity.DoesNotExist:
            raise CommandError(f"Entity id={entity_id} not found.")

    @transaction.atomic
    def handle(self, *args, **opts):
        entity = self._entity(opts["entity"])
        reset  = opts["reset"]
        dry    = opts["dry_run"]
        mirror = opts["mirror_to_options"]
        reset_opts = opts["reset_options"]

        self.stdout.write(self.style.MIGRATE_HEADING(f"Loading GradeBand/Designation for ENTITY:{entity.id}"))

        if reset and not dry:
            Designation.objects.filter(entity=entity).delete()
            GradeBand.objects.filter(entity=entity).delete()
            self.stdout.write(self.style.WARNING("  Reset: cleared existing grades/designations."))

        # Upsert GradeBands
        code_to_gb = {}
        for code, name, level in DEFAULT_GRADE_BANDS:
            if dry:
                self.stdout.write(f"[dry-run] GradeBand {code} — {name} (level={level})")
                continue
            gb, created = GradeBand.objects.get_or_create(
                entity=entity, code=code,
                defaults={"name": name, "level": level}
            )
            changed = False
            if gb.name != name:
                gb.name = name; changed = True
            if gb.level != level:
                gb.level = level; changed = True
            if changed:
                gb.save()
                self.stdout.write(f"  Updated GradeBand: {code}")
            else:
                self.stdout.write(f"  {'Created' if created else 'Kept'} GradeBand: {code}")
            code_to_gb[code] = gb

        # Upsert Designations
        for name, gb_code in DEFAULT_DESIGNATIONS:
            if dry:
                self.stdout.write(f"[dry-run] Designation '{name}' -> {gb_code}")
                continue
            gb = code_to_gb.get(gb_code)
            desig, created = Designation.objects.get_or_create(
                entity=entity, name=name,
                defaults={"grade_band": gb}
            )
            changed = False
            if desig.grade_band_id != (gb.id if gb else None):
                desig.grade_band = gb; changed = True
            if changed:
                desig.save()
                self.stdout.write(f"  Updated Designation: {name}")
            else:
                self.stdout.write(f"  {'Created' if created else 'Kept'} Designation: {name}")

        if mirror:
            self._mirror_to_options(entity, dry=dry, reset=reset_opts)

        self.stdout.write(self.style.SUCCESS("Default titles load complete."))

    # --- Mirror to OptionSet/Option (keys: 'grade_band', 'designation') ---

    def _ensure_set(self, entity: Entity, key: str, dry: bool):
        if dry:
            self.stdout.write(f"[dry-run] ensure OptionSet key='{key}' entity={entity.id}")
            return None
        s, _ = OptionSet.objects.get_or_create(entity=entity, key=key)
        return s

    def _reset_options(self, set_obj, dry: bool):
        if dry or not set_obj:
            return
        Option.objects.filter(set=set_obj).delete()
        self.stdout.write(self.style.WARNING(f"  Cleared options for set '{set_obj.key}'"))

    def _mirror_to_options(self, entity: Entity, dry: bool, reset: bool):
        # grade_band
        gb_set = self._ensure_set(entity, "grade_band", dry)
        if reset: self._reset_options(gb_set, dry)
        gb_qs = GradeBand.objects.filter(entity=entity).order_by("level", "code")
        for i, gb in enumerate(gb_qs):
            code = gb.code  # keep original, already compact
            label = f"{gb.code} — {gb.name}"
            extra = {"source_model": "GradeBand", "source_id": gb.id, "level": gb.level}
            if dry:
                self.stdout.write(f"[dry-run] option grade_band: {code} -> {label}")
            else:
                opt, created = Option.objects.get_or_create(
                    set=gb_set, code=code,
                    defaults={"label": label, "sort_order": i, "is_active": True, "extra": extra}
                )
                changed = False
                if opt.label != label:
                    opt.label = label; changed = True
                if opt.sort_order != i:
                    opt.sort_order = i; changed = True
                if (opt.extra or {}) != extra:
                    opt.extra = extra; changed = True
                if not opt.is_active:
                    opt.is_active = True; changed = True
                if changed: opt.save()

        # designation
        ds_set = self._ensure_set(entity, "designation", dry)
        if reset: self._reset_options(ds_set, dry)
        ds_qs = Designation.objects.filter(entity=entity).select_related("grade_band").order_by("name")
        for i, d in enumerate(ds_qs):
            from django.utils.text import slugify
            code = slugify(d.name).replace("-", "_")
            label = d.name
            extra = {
                "source_model": "Designation",
                "source_id": d.id,
                "grade_band": d.grade_band.code if d.grade_band_id else None
            }
            if dry:
                self.stdout.write(f"[dry-run] option designation: {code} -> {label}")
            else:
                opt, created = Option.objects.get_or_create(
                    set=ds_set, code=code,
                    defaults={"label": label, "sort_order": i, "is_active": True, "extra": extra}
                )
                changed = False
                if opt.label != label:
                    opt.label = label; changed = True
                if opt.sort_order != i:
                    opt.sort_order = i; changed = True
                if (opt.extra or {}) != extra:
                    opt.extra = extra; changed = True
                if not opt.is_active:
                    opt.is_active = True; changed = True
                if changed: opt.save()
