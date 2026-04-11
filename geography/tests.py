from django.db import IntegrityError
from django.db import transaction
from django.test import TestCase
from rest_framework.test import APIClient

from geography.models import City, Country, District, State


class GeographyIntegrityTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_country_and_state_codes_are_normalized(self):
        country = Country.objects.create(countryname=" India ", countrycode="in")
        state = State.objects.create(statename=" Punjab ", statecode="3", country=country)

        self.assertEqual(country.countryname, "India")
        self.assertEqual(country.countrycode, "IN")
        self.assertEqual(state.statename, "Punjab")
        self.assertEqual(state.statecode, "03")

    def test_state_code_is_unique_per_country_for_active_rows(self):
        country = Country.objects.create(countryname="India", countrycode="IN")
        State.objects.create(statename="Punjab", statecode="03", country=country)

        with self.assertRaises(IntegrityError):
            State.objects.create(statename="Duplicate Punjab", statecode="3", country=country)

    def test_district_code_and_name_are_unique_within_state_for_active_rows(self):
        country = Country.objects.create(countryname="India", countrycode="IN")
        state = State.objects.create(statename="Punjab", statecode="03", country=country)
        District.objects.create(districtname="Fatehgarh Sahib", districtcode="FGS", state=state)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                District.objects.create(districtname="Another Name", districtcode="fgs", state=state)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                District.objects.create(districtname="Fatehgarh Sahib", districtcode="FGS2", state=state)

    def test_city_code_and_name_plus_pincode_are_unique_within_district_for_active_rows(self):
        country = Country.objects.create(countryname="India", countrycode="IN")
        state = State.objects.create(statename="Punjab", statecode="03", country=country)
        district = District.objects.create(districtname="Fatehgarh Sahib", districtcode="FGS", state=state)
        City.objects.create(cityname="Sirhind", citycode="SRH", pincode="140406", distt=district)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                City.objects.create(cityname="Another Sirhind", citycode="srh", pincode="140406", distt=district)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                City.objects.create(cityname="Sirhind", citycode="SRH2", pincode="140406", distt=district)

    def test_district_and_city_values_are_normalized(self):
        country = Country.objects.create(countryname="India", countrycode="IN")
        state = State.objects.create(statename="Punjab", statecode="03", country=country)
        district = District.objects.create(districtname=" Fatehgarh Sahib ", districtcode="fgs", state=state)
        city = City.objects.create(cityname=" Sirhind ", citycode="srh", pincode=" 140406 ", distt=district)

        self.assertEqual(district.districtname, "Fatehgarh Sahib")
        self.assertEqual(district.districtcode, "FGS")
        self.assertEqual(city.cityname, "Sirhind")
        self.assertEqual(city.citycode, "SRH")
        self.assertEqual(city.pincode, "140406")

    def test_geography_api_views_return_only_active_rows(self):
        active_country = Country.objects.create(countryname="India", countrycode="IN")
        inactive_country = Country.objects.create(countryname="Old Country", countrycode="OC", isactive=False)
        active_state = State.objects.create(statename="Punjab", statecode="03", country=active_country)
        inactive_state = State.objects.create(statename="Retired State", statecode="09", country=active_country, isactive=False)
        active_district = District.objects.create(districtname="Fatehgarh Sahib", districtcode="FGS", state=active_state)
        inactive_district = District.objects.create(districtname="Old District", districtcode="OLD", state=active_state, isactive=False)
        City.objects.create(cityname="Sirhind", citycode="SRH", pincode="140406", distt=active_district)
        City.objects.create(cityname="Old City", citycode="OLD", pincode="999999", distt=active_district, isactive=False)

        countries = self.client.get("/api/geography/country")
        states = self.client.get("/api/geography/state")
        districts = self.client.get("/api/geography/district")
        cities = self.client.get("/api/geography/city")

        self.assertEqual(countries.status_code, 200)
        self.assertEqual(states.status_code, 200)
        self.assertEqual(districts.status_code, 200)
        self.assertEqual(cities.status_code, 200)

        self.assertEqual(len(countries.data), 1)
        self.assertEqual(countries.data[0]["id"], active_country.id)
        self.assertNotIn(inactive_country.id, [row["id"] for row in countries.data])
        self.assertNotIn(inactive_state.id, [row["id"] for row in states.data])
        self.assertNotIn(inactive_district.id, [row["id"] for row in districts.data])
        self.assertEqual(len(cities.data), 1)

    def test_city_api_exposes_district_id_and_accepts_compatibility_filter(self):
        country = Country.objects.create(countryname="India", countrycode="IN")
        state = State.objects.create(statename="Punjab", statecode="03", country=country)
        district = District.objects.create(districtname="Fatehgarh Sahib", districtcode="FGS", state=state)
        other_district = District.objects.create(districtname="Ludhiana", districtcode="LDH", state=state)
        city = City.objects.create(cityname="Sirhind", citycode="SRH", pincode="140406", distt=district)
        City.objects.create(cityname="Khanna", citycode="KHA", pincode="141401", distt=other_district)

        by_district = self.client.get(f"/api/geography/city?district_id={district.id}")
        by_legacy = self.client.get(f"/api/geography/city?distt={district.id}")

        self.assertEqual(by_district.status_code, 200)
        self.assertEqual(by_legacy.status_code, 200)
        self.assertEqual(len(by_district.data), 1)
        self.assertEqual(len(by_legacy.data), 1)
        self.assertEqual(by_district.data[0]["id"], city.id)
        self.assertEqual(by_district.data[0]["district_id"], district.id)
        self.assertEqual(by_district.data[0]["distt"], district.id)

    def test_geography_api_supports_search_filters(self):
        country = Country.objects.create(countryname="India", countrycode="IN")
        state = State.objects.create(statename="Punjab", statecode="03", country=country)
        other_state = State.objects.create(statename="Haryana", statecode="06", country=country)
        district = District.objects.create(districtname="Fatehgarh Sahib", districtcode="FGS", state=state)
        other_district = District.objects.create(districtname="Ludhiana", districtcode="LDH", state=state)
        City.objects.create(cityname="Sirhind", citycode="SRH", pincode="140406", distt=district)
        City.objects.create(cityname="Khanna", citycode="KHA", pincode="141401", distt=other_district)

        country_search = self.client.get("/api/geography/country?search=ind")
        state_search = self.client.get(f"/api/geography/state?country={country.id}&search=pun")
        district_search = self.client.get(f"/api/geography/district?state={state.id}&search=fateh")
        city_search = self.client.get(f"/api/geography/city?district_id={district.id}&search=sir")

        self.assertEqual(country_search.status_code, 200)
        self.assertEqual(state_search.status_code, 200)
        self.assertEqual(district_search.status_code, 200)
        self.assertEqual(city_search.status_code, 200)

        self.assertEqual(len(country_search.data), 1)
        self.assertEqual(country_search.data[0]["id"], country.id)

        self.assertEqual(len(state_search.data), 1)
        self.assertEqual(state_search.data[0]["id"], state.id)
        self.assertNotIn(other_state.id, [row["id"] for row in state_search.data])

        self.assertEqual(len(district_search.data), 1)
        self.assertEqual(district_search.data[0]["id"], district.id)
        self.assertNotIn(other_district.id, [row["id"] for row in district_search.data])

        self.assertEqual(len(city_search.data), 1)
        self.assertEqual(city_search.data[0]["id"], district.cities.first().id)
