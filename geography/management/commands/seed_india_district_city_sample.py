from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from geography.models import City, Country, District, State


SAMPLE_DATA = [
    {
        "state_code": "29",
        "district_name": "Bengaluru Urban",
        "district_code": "IN-KA-BLRU",
        "cities": [
            {"name": "Bengaluru", "code": "BLR", "pincode": "560001", "lat": 12.9716, "lng": 77.5946},
            {"name": "Yelahanka", "code": "YEL", "pincode": "560064", "lat": 13.1005, "lng": 77.5963},
            {"name": "Electronic City", "code": "ELC", "pincode": "560100", "lat": 12.8399, "lng": 77.6770},
        ],
    },
    {
        "state_code": "27",
        "district_name": "Pune",
        "district_code": "IN-MH-PUNE",
        "cities": [
            {"name": "Pune", "code": "PUN", "pincode": "411001", "lat": 18.5204, "lng": 73.8567},
            {"name": "Pimpri-Chinchwad", "code": "PCMC", "pincode": "411018", "lat": 18.6298, "lng": 73.7997},
            {"name": "Talegaon Dabhade", "code": "TLG", "pincode": "410507", "lat": 18.7350, "lng": 73.6817},
        ],
    },
    {
        "state_code": "24",
        "district_name": "Ahmedabad",
        "district_code": "IN-GJ-AHD",
        "cities": [
            {"name": "Ahmedabad", "code": "AHD", "pincode": "380001", "lat": 23.0225, "lng": 72.5714},
            {"name": "Sanand", "code": "SND", "pincode": "382110", "lat": 22.9923, "lng": 72.3817},
            {"name": "Dholka", "code": "DHK", "pincode": "382225", "lat": 22.7357, "lng": 72.4413},
        ],
    },
    {
        "state_code": "36",
        "district_name": "Hyderabad",
        "district_code": "IN-TS-HYD",
        "cities": [
            {"name": "Hyderabad", "code": "HYD", "pincode": "500001", "lat": 17.3850, "lng": 78.4867},
            {"name": "Secunderabad", "code": "SEC", "pincode": "500003", "lat": 17.4399, "lng": 78.4983},
            {"name": "Uppal", "code": "UPL", "pincode": "500039", "lat": 17.4058, "lng": 78.5591},
        ],
    },
    {
        "state_code": "33",
        "district_name": "Chennai",
        "district_code": "IN-TN-CHE",
        "cities": [
            {"name": "Chennai", "code": "CHE", "pincode": "600001", "lat": 13.0827, "lng": 80.2707},
            {"name": "Tambaram", "code": "TMB", "pincode": "600045", "lat": 12.9249, "lng": 80.1000},
            {"name": "Avadi", "code": "AVD", "pincode": "600054", "lat": 13.1143, "lng": 80.1097},
        ],
    },
]


class Command(BaseCommand):
    help = "Seed sample India districts and cities for testing (5 districts, 3 cities each)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview changes without saving.")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        country = Country.objects.filter(countrycode__iexact="IN").first()
        if not country:
            raise CommandError("India country not found. Run `python manage.py seed_india_geography` first.")

        created_districts = 0
        updated_districts = 0
        created_cities = 0
        updated_cities = 0

        for item in SAMPLE_DATA:
            state = State.objects.filter(country=country, statecode=item["state_code"]).first()
            if not state:
                raise CommandError(
                    f"State with GST code '{item['state_code']}' not found for India. "
                    "Run `python manage.py seed_india_geography` first."
                )

            district, created = District.objects.get_or_create(
                state=state,
                districtname=item["district_name"],
                defaults={"districtcode": item["district_code"], "isactive": True},
            )
            if created:
                created_districts += 1
            else:
                should_update = district.districtcode != item["district_code"] or not district.isactive
                if should_update:
                    district.districtcode = item["district_code"]
                    district.isactive = True
                    district.save(update_fields=["districtcode", "isactive", "updated_at"])
                    updated_districts += 1

            for c in item["cities"]:
                city, c_created = City.objects.get_or_create(
                    distt=district,
                    cityname=c["name"],
                    pincode=c["pincode"],
                    defaults={
                        "citycode": c["code"],
                        "latitude": c["lat"],
                        "longitude": c["lng"],
                    },
                )
                if c_created:
                    created_cities += 1
                    continue

                c_update = (
                    city.citycode != c["code"]
                    or float(city.latitude or 0.0) != float(c["lat"])
                    or float(city.longitude or 0.0) != float(c["lng"])
                )
                if c_update:
                    city.citycode = c["code"]
                    city.latitude = c["lat"]
                    city.longitude = c["lng"]
                    city.save(update_fields=["citycode", "latitude", "longitude"])
                    updated_cities += 1

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                "Sample geography seed complete. "
                f"districts(created={created_districts}, updated={updated_districts}), "
                f"cities(created={created_cities}, updated={updated_cities}), dry_run={dry_run}"
            )
        )
