from django.test import TestCase

from geography.models import City, Country, District, State
from geography.seeding import GeographySeedService


class GeographySeedServiceTests(TestCase):
    def test_seed_india_baseline_is_idempotent(self):
        first = GeographySeedService.seed_india_baseline()
        second = GeographySeedService.seed_india_baseline()

        self.assertEqual(first, second)
        self.assertEqual(Country.objects.filter(countrycode="IN").count(), 1)
        self.assertEqual(State.objects.filter(country__countrycode="IN").count(), first["state_count"])
        self.assertEqual(District.objects.count(), first["district_count"])
        self.assertEqual(City.objects.count(), first["city_count"])

    def test_seed_india_baseline_creates_expected_rows(self):
        GeographySeedService.seed_india_baseline()

        country = Country.objects.get(countrycode="IN")
        punjab = State.objects.get(country=country, statecode="PB")
        fatehgarh = District.objects.get(state=punjab, districtcode="FGS")
        sirhind = City.objects.get(distt=fatehgarh, citycode="SRH")

        self.assertEqual(country.countryname, "India")
        self.assertEqual(punjab.statename, "Punjab")
        self.assertEqual(fatehgarh.districtname, "Fatehgarh Sahib")
        self.assertEqual(sirhind.cityname, "Sirhind")
        self.assertEqual(sirhind.pincode, "140406")
