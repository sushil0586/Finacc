from django.test import TestCase

from Authentication.models import User
from entity.models import Entity, GstRegistrationType, UnitType, Constitution
from geography.models import City, Country, District, State

from .models import CustomerSubscription, UserEntityAccess
from .services import SubscriptionService


class SubscriptionServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="secret123",
            first_name="Owner",
        )
        self.country = Country.objects.create(countryname="India", countrycode="IN")
        self.state = State.objects.create(statename="Punjab", statecode="PB", country=self.country)
        self.district = District.objects.create(districtname="Fatehgarh", districtcode="FGS", state=self.state)
        self.city = City.objects.create(cityname="Sirhind", citycode="SRH", pincode="140406", distt=self.district)
        self.unit_type = UnitType.objects.create(UnitName="Unit", UnitDesc="Unit")
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.constitution = Constitution.objects.create(
            constitutionname="Proprietorship",
            constitutiondesc="Proprietorship",
            constcode="01",
            createdby=self.user,
        )

    def test_signup_creates_customer_account_and_subscription(self):
        account = SubscriptionService.handle_signup(user=self.user)

        self.assertEqual(account.primary_user, self.user)
        self.assertTrue(CustomerSubscription.objects.filter(customer_account=account).exists())

    def test_register_entity_creation_links_customer_account_and_access(self):
        entity = Entity.objects.create(
            entityname="Demo Entity",
            legalname="Demo Entity",
            unitType=self.unit_type,
            GstRegitrationType=self.gst_type,
            address="Address",
            ownername="Owner",
            country=self.country,
            state=self.state,
            district=self.district,
            city=self.city,
            phoneoffice="1234567890",
            phoneresidence="1234567890",
            const=self.constitution,
            createdby=self.user,
        )

        account = SubscriptionService.register_entity_creation(entity=entity, owner=self.user)

        entity.refresh_from_db()
        self.assertEqual(entity.customer_account, account)
        self.assertTrue(UserEntityAccess.objects.filter(entity=entity, user=self.user, is_owner=True).exists())

