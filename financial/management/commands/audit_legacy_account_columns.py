from django.core.management.base import BaseCommand
from django.db.models import Q

from financial.models import account


class Command(BaseCommand):
    help = "Audit legacy account columns and report how many rows still have data before DB-drop migration."

    CHAR_FIELDS = [
        "gstno",
        "pan",
        "gstintype",
        "gstregtype",
        "cin",
        "msme",
        "gsttdsno",
        "tdsno",
        "tdssection",
        "tcscode",
        "partytype",
        "paymentterms",
        "currency",
        "blockstatus",
        "blockedreason",
        "agent",
        "address1",
        "address2",
        "addressfloorno",
        "addressstreet",
        "pincode",
    ]

    NUMERIC_FIELDS = [
        "tdsrate",
        "tds_threshold",
        "creditlimit",
        "creditdays",
        "reminders",
    ]

    BOOL_FIELDS = [
        "is_sez",
        "istcsapplicable",
        "approved",
    ]

    FK_ID_FIELDS = [
        "country_id",
        "state_id",
        "district_id",
        "city_id",
    ]

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, default=None)

    def handle(self, *args, **options):
        qs = account.objects.all()
        entity_id = options.get("entity_id")
        if entity_id:
            qs = qs.filter(entity_id=entity_id)

        total = qs.count()
        self.stdout.write(self.style.SUCCESS("Legacy account column audit"))
        self.stdout.write(f"Accounts scanned: {total}")
        if entity_id:
            self.stdout.write(f"Entity filter: {entity_id}")

        results = []

        for field in self.CHAR_FIELDS:
            count = qs.exclude(**{f"{field}__isnull": True}).exclude(**{field: ""}).count()
            results.append((field, count))

        for field in self.NUMERIC_FIELDS:
            count = qs.exclude(**{f"{field}__isnull": True}).count()
            results.append((field, count))

        for field in self.BOOL_FIELDS:
            count = qs.filter(**{field: True}).count()
            results.append((field, count))

        for field in self.FK_ID_FIELDS:
            count = qs.exclude(**{f"{field}__isnull": True}).count()
            results.append((field, count))

        non_zero = [(field, count) for field, count in results if count > 0]
        for field, count in sorted(results, key=lambda x: x[0]):
            self.stdout.write(f"{field}: {count}")

        self.stdout.write("")
        if non_zero:
            self.stdout.write(self.style.WARNING("Columns still carrying legacy data:"))
            for field, count in sorted(non_zero, key=lambda x: (-x[1], x[0])):
                self.stdout.write(f"- {field}: {count}")
        else:
            self.stdout.write(self.style.SUCCESS("All audited legacy columns are empty/false/null-safe for drop."))
