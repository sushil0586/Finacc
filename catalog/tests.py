from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import HsnSac, PriceList, Product, ProductAttribute, ProductAttributeValue, ProductBarcode, ProductCategory, ProductClassification, ProductGstRate, ProductPrice, UnitOfMeasure
from catalog.serializers import ProductSerializer
from catalog.transaction_products import TransactionProductCatalogService
from catalog.views import ProductBarcodeDownloadPDFAPIView
from entity.models import Entity, GstRegistrationType


class CatalogPhase1Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="catalog-phase1",
            email="catalog-phase1@example.com",
            password="testpass123",
        )
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Catalog Phase1 Entity",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.category = ProductCategory.objects.create(
            entity=self.entity,
            pcategoryname="Finished Goods",
        )
        self.uom = UnitOfMeasure.objects.create(
            entity=self.entity,
            code="PCS",
            description="Pieces",
        )
        self.hsn = HsnSac.objects.create(
            entity=self.entity,
            code="9983",
            description="Services",
        )
        self.other_entity = Entity.objects.create(
            entityname="Catalog Other Entity",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.other_uom = UnitOfMeasure.objects.create(
            entity=self.other_entity,
            code="BOX",
            description="Boxes",
        )
        self.alt_uom = UnitOfMeasure.objects.create(
            entity=self.entity,
            code="BOX",
            description="Boxes",
        )

    def _valid_payload(self, **overrides):
        payload = {
            "entity": self.entity.id,
            "productname": "Inventory Ready Product",
            "sku": "IRP-001",
            "productdesc": "Phase 1 product",
            "productcategory": self.category.id,
            "brand": None,
            "base_uom": self.uom.id,
            "sales_account": None,
            "purchase_account": None,
            "is_service": False,
            "item_classification": ProductClassification.TRADING,
            "is_batch_managed": False,
            "is_serialized": False,
            "is_expiry_tracked": True,
            "shelf_life_days": 180,
            "expiry_warning_days": 30,
            "is_ecomm_9_5_service": False,
            "default_is_rcm": False,
            "is_itc_eligible": True,
            "product_status": "active",
            "launch_date": "2026-04-12",
            "discontinue_date": None,
            "isactive": True,
        }
        payload.update(overrides)
        return payload

    def test_product_serializer_accepts_classification_and_expiry_fields(self):
        serializer = ProductSerializer(
            data=self._valid_payload(),
            context={"entity": self.entity},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        product = serializer.save(entity=self.entity)

        self.assertEqual(product.item_classification, ProductClassification.TRADING)
        self.assertTrue(product.is_expiry_tracked)
        self.assertEqual(product.shelf_life_days, 180)
        self.assertEqual(product.expiry_warning_days, 30)

    def test_service_classification_normalizes_service_and_clears_stock_controls(self):
        serializer = ProductSerializer(
            data=self._valid_payload(
                sku="SRV-001",
                item_classification=ProductClassification.SERVICE,
                is_service=False,
                is_batch_managed=True,
                is_serialized=True,
                is_expiry_tracked=True,
                shelf_life_days=180,
                expiry_warning_days=30,
            ),
            context={"entity": self.entity},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        product = serializer.save(entity=self.entity)

        self.assertTrue(product.is_service)
        self.assertEqual(product.item_classification, ProductClassification.SERVICE)
        self.assertFalse(product.is_batch_managed)
        self.assertFalse(product.is_serialized)
        self.assertFalse(product.is_expiry_tracked)
        self.assertIsNone(product.shelf_life_days)
        self.assertEqual(product.expiry_warning_days, 0)

    def test_ecomm_95_requires_service_item(self):
        serializer = ProductSerializer(
            data=self._valid_payload(
                is_service=False,
                item_classification=ProductClassification.TRADING,
                is_ecomm_9_5_service=True,
            ),
            context={"entity": self.entity},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("is_ecomm_9_5_service", serializer.errors)

    def test_expiry_warning_cannot_exceed_shelf_life(self):
        serializer = ProductSerializer(
            data=self._valid_payload(expiry_warning_days=365, shelf_life_days=180),
            context={"entity": self.entity},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("expiry_warning_days", serializer.errors)

    def test_expiry_tracking_requires_shelf_life(self):
        serializer = ProductSerializer(
            data=self._valid_payload(is_expiry_tracked=True, shelf_life_days=None),
            context={"entity": self.entity},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("shelf_life_days", serializer.errors)

    def test_product_serializer_rejects_barcode_uom_from_other_entity(self):
        serializer = ProductSerializer(
            data=self._valid_payload(
                barcodes=[
                    {
                        "uom": self.other_uom.id,
                        "pack_size": 1,
                        "isprimary": True,
                    }
                ]
            ),
            context={"entity": self.entity},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("barcodes", serializer.errors)

    def test_product_serializer_marks_first_barcode_primary_when_none_selected(self):
        serializer = ProductSerializer(
            data=self._valid_payload(
                barcodes=[
                    {
                        "uom": self.uom.id,
                        "pack_size": 1,
                        "isprimary": False,
                    },
                    {
                        "uom": self.uom.id,
                        "pack_size": 2,
                        "isprimary": False,
                    },
                ]
            ),
            context={"entity": self.entity},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        product = serializer.save(entity=self.entity)

        barcodes = list(product.barcode_details.order_by("id"))
        self.assertEqual(len(barcodes), 2)
        self.assertEqual(sum(1 for row in barcodes if row.isprimary), 1)
        self.assertTrue(barcodes[0].isprimary)
        self.assertFalse(barcodes[1].isprimary)

    def test_product_update_recreates_default_primary_barcode_when_all_removed(self):
        serializer = ProductSerializer(
            data=self._valid_payload(
                barcodes=[
                    {
                        "uom": self.uom.id,
                        "pack_size": 1,
                        "isprimary": True,
                    }
                ]
            ),
            context={"entity": self.entity},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        product = serializer.save(entity=self.entity)

        update_serializer = ProductSerializer(
            product,
            data=self._valid_payload(productname="Inventory Ready Product Updated", barcodes=[]),
            context={"entity": self.entity},
        )
        self.assertTrue(update_serializer.is_valid(), update_serializer.errors)
        updated = update_serializer.save(entity=self.entity)

        barcodes = list(updated.barcode_details.order_by("id"))
        self.assertEqual(len(barcodes), 1)
        self.assertTrue(barcodes[0].isprimary)
        self.assertEqual(barcodes[0].uom_id, self.uom.id)

    def test_product_serializer_rejects_barcode_for_uom_outside_product_uom_scope(self):
        serializer = ProductSerializer(
            data=self._valid_payload(
                barcodes=[
                    {
                        "uom": self.alt_uom.id,
                        "pack_size": 2,
                        "isprimary": True,
                    }
                ]
            ),
            context={"entity": self.entity},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("barcodes", serializer.errors)

    def test_product_serializer_accepts_barcode_for_converted_uom(self):
        serializer = ProductSerializer(
            data=self._valid_payload(
                uom_conversions=[
                    {
                        "from_uom": self.uom.id,
                        "to_uom": self.alt_uom.id,
                        "factor": 10,
                    }
                ],
                barcodes=[
                    {
                        "uom": self.alt_uom.id,
                        "pack_size": 1,
                        "isprimary": True,
                    }
                ]
            ),
            context={"entity": self.entity},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_service_items_do_not_accept_barcode_rows(self):
        serializer = ProductSerializer(
            data=self._valid_payload(
                sku="SRV-BC-001",
                item_classification=ProductClassification.SERVICE,
                is_service=True,
                barcodes=[
                    {
                        "uom": self.uom.id,
                        "pack_size": 1,
                        "isprimary": True,
                    }
                ]
            ),
            context={"entity": self.entity},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("barcodes", serializer.errors)

    def test_product_serializer_rejects_uom_conversion_without_base_uom(self):
        serializer = ProductSerializer(
            data=self._valid_payload(
                uom_conversions=[
                    {
                        "from_uom": self.alt_uom.id,
                        "to_uom": self.other_uom.id,
                        "factor": 10,
                    }
                ]
            ),
            context={"entity": self.entity},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("uom_conversions", serializer.errors)

    def test_product_base_uom_cannot_change_while_conversions_exist(self):
        serializer = ProductSerializer(
            data=self._valid_payload(
                uom_conversions=[
                    {
                        "from_uom": self.uom.id,
                        "to_uom": self.alt_uom.id,
                        "factor": 10,
                    }
                ]
            ),
            context={"entity": self.entity},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        product = serializer.save(entity=self.entity)

        kg_uom = UnitOfMeasure.objects.create(
            entity=self.entity,
            code="KG",
            description="Kilogram",
        )
        update_serializer = ProductSerializer(
            product,
            data=self._valid_payload(base_uom=kg_uom.id, sku="IRP-002"),
            context={"entity": self.entity},
        )

        self.assertFalse(update_serializer.is_valid())
        self.assertIn("base_uom", update_serializer.errors)


class CatalogTransactionProductContractTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="catalog-transaction",
            email="catalog-transaction@example.com",
            password="testpass123",
        )
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Catalog Transaction Entity",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.category = ProductCategory.objects.create(
            entity=self.entity,
            pcategoryname="Finished Goods",
        )
        self.base_uom = UnitOfMeasure.objects.create(entity=self.entity, code="PCS", description="Pieces")
        self.alt_uom = UnitOfMeasure.objects.create(entity=self.entity, code="BOX", description="Boxes")
        self.price_list = PriceList.objects.create(entity=self.entity, name="Default", description="Default", isdefault=True)
        self.hsn = HsnSac.objects.create(
            entity=self.entity,
            code="9983",
            description="Service-like HSN",
            is_service=True,
            default_cgst=9,
            default_sgst=9,
            default_igst=18,
        )

    def test_transaction_product_payload_exposes_explicit_defaults(self):
        product = Product.objects.create(
            entity=self.entity,
            productname="Retail Product",
            sku="RTL-001",
            productdesc="Retail-ready product",
            productcategory=self.category,
            base_uom=self.base_uom,
            item_classification=ProductClassification.TRADING,
            product_status="active",
            is_service=False,
            isactive=True,
        )
        ProductGstRate.objects.create(
            product=product,
            hsn=self.hsn,
            gst_type="regular",
            cgst=9,
            sgst=9,
            igst=18,
            cess=0,
            cess_type="none",
            valid_from="2026-04-01",
            isdefault=True,
        )
        ProductPrice.objects.create(
            product=product,
            pricelist=self.price_list,
            uom=self.base_uom,
            purchase_rate=80,
            selling_price=100,
            mrp=110,
            effective_from="2026-04-01",
        )
        ProductBarcode.objects.create(product=product, uom=self.base_uom, pack_size=1, isprimary=True)

        payload = TransactionProductCatalogService.get_product(entity_id=self.entity.id, product_id=product.id)

        self.assertEqual(payload["item_classification"], ProductClassification.TRADING)
        self.assertEqual(payload["product_status"], "active")
        self.assertEqual(payload["default_uom_id"], product.base_uom_id)
        self.assertEqual(payload["default_uom_code"], "PCS")
        self.assertTrue(payload["default_barcode"]["isprimary"])
        self.assertEqual(payload["default_barcode"]["uom_id"], product.base_uom_id)
        self.assertTrue(payload["uom_options"][0]["primary_barcode"]["isprimary"])
        self.assertTrue(payload["hsn_is_service"])

    def test_barcode_pdf_builder_supports_selected_fields_and_attributes(self):
        product = Product.objects.create(
            entity=self.entity,
            productname="Jewellery Tag",
            sku="JW-001",
            productdesc="Jewellery-ready product",
            productcategory=self.category,
            base_uom=self.base_uom,
            item_classification=ProductClassification.TRADING,
            product_status="active",
            is_service=False,
            isactive=True,
        )
        weight_attr = ProductAttribute.objects.create(entity=self.entity, name="Weight", data_type="number")
        ProductAttributeValue.objects.create(product=product, attribute=weight_attr, value_number="12.50")
        barcode = ProductBarcode.objects.create(
            product=product,
            uom=self.base_uom,
            pack_size=1,
            isprimary=True,
            mrp="1200.00",
            selling_price="1180.00",
        )

        pdf_view = ProductBarcodeDownloadPDFAPIView()
        pdf_file = pdf_view._build_pdf(
            [barcode],
            layout=16,
            show_createdon=False,
            print_fields={"product_name", "barcode", "mrp", "selling_price"},
            attribute_ids=[weight_attr.id],
        )

        self.assertGreater(len(pdf_file.getvalue()), 0)


class CatalogProductListApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="catalog-list-user",
            email="catalog-list@example.com",
            password="testpass123",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Catalog List Entity",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.category = ProductCategory.objects.create(entity=self.entity, pcategoryname="Packaged Goods")
        self.uom = UnitOfMeasure.objects.create(entity=self.entity, code="PCS", description="Pieces")

    def _create_product(self, **overrides):
        payload = {
            "entity": self.entity,
            "productname": "Chana 1 KG",
            "sku": "CH-1KG",
            "productdesc": "Retail pack",
            "productcategory": self.category,
            "brand": None,
            "base_uom": self.uom,
            "item_classification": ProductClassification.FINISHED_GOOD,
            "is_service": False,
            "product_status": "active",
            "isactive": True,
        }
        payload.update(overrides)
        return Product.objects.create(**payload)

    def test_product_list_supports_search_across_identity_fields(self):
        self._create_product(productname="Toor Dal 5 KG", sku="TD-5KG")
        self._create_product(productname="Repair Service", sku="SRV-01", item_classification=ProductClassification.SERVICE, is_service=True)

        response = self.client.get(reverse("product-list-create"), {"entity": self.entity.id, "search": "toor"})

        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sku"], "TD-5KG")

    def test_product_list_supports_classification_and_service_filters(self):
        self._create_product(productname="Resin", sku="RM-01", item_classification=ProductClassification.RAW_MATERIAL)
        self._create_product(productname="Installation", sku="SRV-01", item_classification=ProductClassification.SERVICE, is_service=True)

        raw_response = self.client.get(reverse("product-list-create"), {"entity": self.entity.id, "item_classification": ProductClassification.RAW_MATERIAL})
        service_response = self.client.get(reverse("product-list-create"), {"entity": self.entity.id, "is_service": "true"})

        self.assertEqual(raw_response.status_code, 200)
        self.assertEqual(service_response.status_code, 200)
        self.assertEqual(len(raw_response.json()), 1)
        self.assertEqual(raw_response.json()[0]["item_classification"], ProductClassification.RAW_MATERIAL)
        self.assertEqual(len(service_response.json()), 1)
        self.assertTrue(service_response.json()[0]["is_service"])
