from __future__ import annotations

import re

from django.core.management.base import BaseCommand
from django.db import transaction

from geography.gst_state_codes import INDIA_STATES_GST, STATE_NAME_ALIASES
from geography.models import Country, State


def _norm(value: str) -> str:
    value = (value or "").strip().lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return STATE_NAME_ALIASES.get(value, value)


class Command(BaseCommand):
    help = "Seed/repair India country and GST state codes in geography tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without saving.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        created = 0
        updated = 0
        untouched = 0

        india_qs = Country.objects.filter(countrycode__iexact="IN")
        india = india_qs.first()
        if india is None:
            india = Country(countryname="India", countrycode="IN")
            if dry_run:
                self.stdout.write(self.style.WARNING("[DRY RUN] Would create Country(IN, India)"))
            else:
                india.save()
            created += 1
        else:
            desired_name = "India"
            if india.countryname != desired_name:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[DRY RUN] Would update country name '{india.countryname}' -> '{desired_name}'"
                        )
                    )
                else:
                    india.countryname = desired_name
                    india.save(update_fields=["countryname", "updated_at"])
                updated += 1
            else:
                untouched += 1

        existing_states_qs = (
            State.objects.filter(country=india)
            if india.pk
            else State.objects.filter(country__countrycode__iexact="IN")
        )

        state_by_code = {
            str(st.statecode or "").strip().zfill(2): st
            for st in existing_states_qs
            if str(st.statecode or "").strip()
        }
        state_by_name = {
            _norm(st.statename): st
            for st in existing_states_qs
            if _norm(st.statename)
        }

        for gst_code, canonical_name in INDIA_STATES_GST:
            existing = state_by_code.get(gst_code)
            if existing is None:
                existing = state_by_name.get(_norm(canonical_name))

            if existing is None:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(f"[DRY RUN] Would create state {canonical_name} ({gst_code})")
                    )
                else:
                    State.objects.create(
                        country=india,
                        statename=canonical_name,
                        statecode=gst_code,
                        isactive=True,
                    )
                created += 1
                continue

            needs_change = (
                str(existing.statecode or "").strip().zfill(2) != gst_code
                or _norm(existing.statename) != _norm(canonical_name)
                or existing.country_id != india.id
                or not existing.isactive
            )
            if not needs_change:
                untouched += 1
                continue

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"[DRY RUN] Would update state id={existing.id}: "
                        f"name='{existing.statename}' code='{existing.statecode}' -> "
                        f"name='{canonical_name}' code='{gst_code}'"
                    )
                )
            else:
                existing.statename = canonical_name
                existing.statecode = gst_code
                existing.country = india
                existing.isactive = True
                existing.save(update_fields=["statename", "statecode", "country", "isactive", "updated_at"])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"India geography seed complete. created={created}, updated={updated}, untouched={untouched}, dry_run={dry_run}"
            )
        )

        if dry_run:
            transaction.set_rollback(True)
