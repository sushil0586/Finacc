from django.db import transaction

from geography.models import City, Country, District, State
from geography.seed_catalogs import INDIA_GEOGRAPHY_CATALOG


class GeographySeedService:
    """
    Seed a small, reusable India geography baseline for fresh environments.

    The service is intentionally idempotent so local setup and repeated bootstrap
    runs do not create duplicate countries, states, districts, or cities.
    """

    @classmethod
    @transaction.atomic
    def seed_india_baseline(cls, *, include_inactive=False):
        country_spec = INDIA_GEOGRAPHY_CATALOG["country"]
        country, _ = Country.objects.get_or_create(
            countrycode=country_spec["code"],
            defaults={"countryname": country_spec["name"]},
        )
        country.countryname = country_spec["name"]
        country.save(update_fields=["countryname"])

        state_rows = []
        district_rows = []
        city_rows = []

        for state_spec in INDIA_GEOGRAPHY_CATALOG["states"]:
            state, _ = State.objects.get_or_create(
                country=country,
                statecode=state_spec["code"],
                defaults={"statename": state_spec["name"]},
            )
            state.statename = state_spec["name"]
            state.save(update_fields=["statename"])
            state_rows.append(state)

            for district_spec in state_spec["districts"]:
                district, _ = District.objects.get_or_create(
                    state=state,
                    districtcode=district_spec["code"],
                    defaults={"districtname": district_spec["name"]},
                )
                district.districtname = district_spec["name"]
                district.save(update_fields=["districtname"])
                district_rows.append(district)

                for city_spec in district_spec["cities"]:
                    city, _ = City.objects.get_or_create(
                        distt=district,
                        citycode=city_spec["code"],
                        defaults={
                            "cityname": city_spec["name"],
                            "pincode": city_spec["pincode"],
                        },
                    )
                    city.cityname = city_spec["name"]
                    city.pincode = city_spec["pincode"]
                    city.save(update_fields=["cityname", "pincode"])
                    city_rows.append(city)

        if not include_inactive:
            cls._reactivate_seeded_rows(country, state_rows, district_rows, city_rows)

        return {
            "country_count": 1,
            "state_count": len(state_rows),
            "district_count": len(district_rows),
            "city_count": len(city_rows),
            "country_id": country.id,
        }

    @staticmethod
    def _reactivate_seeded_rows(country, states, districts, cities):
        for row in [country, *states, *districts, *cities]:
            if hasattr(row, "isactive") and not row.isactive:
                row.isactive = True
                row.save(update_fields=["isactive"])
