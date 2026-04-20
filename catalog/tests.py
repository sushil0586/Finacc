from tempfile import TemporaryDirectory
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError

from catalog.models import BarcodeLabelTemplate, HsnSac, PriceList, Product, ProductAttribute, ProductAttributeValue, ProductBarcode, ProductCategory, ProductClassification, ProductGstRate, ProductPrice, UnitOfMeasure
from catalog.serializers import ProductBarcodeManageSerializer, ProductSerializer
from catalog.transaction_products import TransactionProductCatalogService
from catalog.views import ProductBarcodeDownloadPDFAPIView
from commerce.services import BarcodeResolutionService
from entity.models import Entity, GstRegistrationType, SubEntity


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

    def _create_product(self, **overrides):
        payload = {
            "entity": self.entity,
            "productname": "Inventory Ready Product",
            "sku": "IRP-001",
            "productdesc": "Phase 1 product",
            "productcategory": self.category,
            "brand": None,
            "base_uom": self.uom,
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
            "product_status": "active",
            "isactive": True,
        }
        payload.update(overrides)
        return Product.objects.create(**payload)

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

    def test_product_serializer_preserves_explicit_barcode_value(self):
        explicit_barcode = "8901234567890"
        serializer = ProductSerializer(
            data=self._valid_payload(
                sku="IRP-BC-001",
                barcodes=[
                    {
                        "uom": self.uom.id,
                        "pack_size": 1,
                        "isprimary": True,
                        "barcode": explicit_barcode,
                    }
                ],
            ),
            context={"entity": self.entity},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        product = serializer.save(entity=self.entity)

        barcode = product.barcode_details.get()
        self.assertEqual(barcode.barcode, explicit_barcode)
        self.assertTrue(barcode.barcode_image)

    def test_product_serializer_rejects_duplicate_barcodes_in_same_payload(self):
        serializer = ProductSerializer(
            data=self._valid_payload(
                sku="IRP-BC-DUP",
                barcodes=[
                    {
                        "uom": self.uom.id,
                        "pack_size": 1,
                        "isprimary": True,
                        "barcode": "8901234567891",
                    },
                    {
                        "uom": self.alt_uom.id,
                        "pack_size": 2,
                        "isprimary": False,
                        "barcode": "8901234567891",
                    },
                ],
            ),
            context={"entity": self.entity},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("barcodes", serializer.errors)

    def test_product_serializer_updates_existing_barcode_value(self):
        initial_barcode = "8901234567000"
        updated_barcode = "8901234567999"
        serializer = ProductSerializer(
            data=self._valid_payload(
                sku="IRP-BC-002",
                barcodes=[
                    {
                        "uom": self.uom.id,
                        "pack_size": 1,
                        "isprimary": True,
                        "barcode": initial_barcode,
                    }
                ],
            ),
            context={"entity": self.entity},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        product = serializer.save(entity=self.entity)
        barcode = product.barcode_details.get()
        with barcode.barcode_image.open("rb") as fh:
            before_bytes = fh.read()

        update_serializer = ProductSerializer(
            product,
            data=self._valid_payload(
                sku="IRP-BC-002",
                productname="Inventory Ready Product Updated",
                barcodes=[
                    {
                        "id": barcode.id,
                        "uom": self.uom.id,
                        "pack_size": 1,
                        "isprimary": True,
                        "barcode": updated_barcode,
                    }
                ],
            ),
            context={"entity": self.entity},
        )

        self.assertTrue(update_serializer.is_valid(), update_serializer.errors)
        updated = update_serializer.save(entity=self.entity)

        updated_barcode_row = updated.barcode_details.get()
        self.assertEqual(updated_barcode_row.barcode, updated_barcode)
        with updated_barcode_row.barcode_image.open("rb") as fh:
            after_bytes = fh.read()
        self.assertNotEqual(before_bytes, after_bytes)

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

    def test_barcode_manage_serializer_accepts_manual_barcode_value(self):
        product = Product.objects.create(
            entity=self.entity,
            productname="Managed Barcode Product",
            sku="MBP-001",
            productdesc="Managed barcode",
            productcategory=self.category,
            base_uom=self.uom,
            item_classification=ProductClassification.TRADING,
            is_service=False,
            product_status="active",
            isactive=True,
        )

        serializer = ProductBarcodeManageSerializer(
            data={
                "uom": self.uom.id,
                "pack_size": 1,
                "isprimary": True,
                "barcode": "9988776655443",
                "mrp": "250.00",
                "selling_price": "200.00",
            },
            context={"product": product},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        barcode = serializer.save()

        self.assertEqual(barcode.barcode, "9988776655443")
        self.assertEqual(barcode.entity_id, product.entity_id)
        self.assertTrue(barcode.barcode_image)

    def test_barcode_manage_serializer_rejects_duplicate_barcode_within_entity(self):
        first_product = Product.objects.create(
            entity=self.entity,
            productname="First Barcode Product",
            sku="FBP-001",
            productdesc="First barcode",
            productcategory=self.category,
            base_uom=self.uom,
            item_classification=ProductClassification.TRADING,
            is_service=False,
            product_status="active",
            isactive=True,
        )
        second_product = Product.objects.create(
            entity=self.entity,
            productname="Second Barcode Product",
            sku="SBP-001",
            productdesc="Second barcode",
            productcategory=self.category,
            base_uom=self.uom,
            item_classification=ProductClassification.TRADING,
            is_service=False,
            product_status="active",
            isactive=True,
        )

        first_serializer = ProductBarcodeManageSerializer(
            data={
                "uom": self.uom.id,
                "pack_size": 1,
                "isprimary": True,
                "barcode": "8899001122334",
            },
            context={"product": first_product},
        )
        self.assertTrue(first_serializer.is_valid(), first_serializer.errors)
        first_serializer.save()

        duplicate_serializer = ProductBarcodeManageSerializer(
            data={
                "uom": self.uom.id,
                "pack_size": 1,
                "isprimary": True,
                "barcode": "8899001122334",
            },
            context={"product": second_product},
        )

        self.assertFalse(duplicate_serializer.is_valid())
        self.assertIn("barcode", duplicate_serializer.errors)

    def test_barcode_manage_serializer_allows_same_code_in_other_entity(self):
        product = Product.objects.create(
            entity=self.other_entity,
            productname="Other Entity Barcode Product",
            sku="OEBP-001",
            productdesc="Other entity barcode",
            productcategory=ProductCategory.objects.create(
                entity=self.other_entity,
                pcategoryname="Other Finished Goods",
            ),
            base_uom=self.other_uom,
            item_classification=ProductClassification.TRADING,
            is_service=False,
            product_status="active",
            isactive=True,
        )

        serializer = ProductBarcodeManageSerializer(
            data={
                "uom": self.other_uom.id,
                "pack_size": 1,
                "isprimary": True,
                "barcode": "8899001122334",
            },
            context={"product": product},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        barcode = serializer.save()
        self.assertEqual(barcode.barcode, "8899001122334")
        self.assertEqual(barcode.entity_id, product.entity_id)

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

    def test_barcode_image_refreshes_when_code_changes(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            barcode = ProductBarcode.objects.create(
                product=self._create_product(productname="Image Refresh Product", sku="IR-001"),
                uom=self.uom,
                pack_size=1,
                isprimary=True,
                barcode="1111111111111",
            )

            with barcode.barcode_image.open("rb") as fh:
                before_bytes = fh.read()

            barcode.barcode = "2222222222222"
            barcode.save()
            barcode.refresh_from_db()

            with barcode.barcode_image.open("rb") as fh:
                after_bytes = fh.read()

            self.assertNotEqual(before_bytes, after_bytes)
            self.assertEqual(barcode.barcode, "2222222222222")

    def test_barcode_resolution_rejects_duplicate_codes(self):
        first_product = Product.objects.create(
            entity=self.entity,
            productname="Resolver One",
            sku="RES-001",
            productdesc="Resolver one",
            productcategory=self.category,
            base_uom=self.uom,
            item_classification=ProductClassification.TRADING,
            is_service=False,
            product_status="active",
            isactive=True,
        )
        second_product = Product.objects.create(
            entity=self.entity,
            productname="Resolver Two",
            sku="RES-002",
            productdesc="Resolver two",
            productcategory=self.category,
            base_uom=self.uom,
            item_classification=ProductClassification.TRADING,
            is_service=False,
            product_status="active",
            isactive=True,
        )

        ProductBarcode.objects.bulk_create([
            ProductBarcode(product=first_product, uom=self.uom, pack_size=1, isprimary=True, barcode="7777777777777"),
            ProductBarcode(product=second_product, uom=self.uom, pack_size=1, isprimary=True, barcode="7777777777777"),
        ])

        with self.assertRaises(ValidationError) as ctx:
            BarcodeResolutionService.resolve(entity_id=self.entity.id, code="7777777777777")

        self.assertIn("barcode", getattr(ctx.exception, "detail", ctx.exception))


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


class CatalogBarcodeLabelTemplateTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="catalog-template-user",
            email="catalog-template@example.com",
            password="testpass123",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.gst_type = GstRegistrationType.objects.create(Name="Regular", Description="Regular")
        self.entity = Entity.objects.create(
            entityname="Catalog Template Entity",
            GstRegitrationType=self.gst_type,
            createdby=self.user,
        )
        self.subentity = SubEntity.objects.create(
            entity=self.entity,
            subentityname="Catalog Branch",
            branch_type=SubEntity.BranchType.BRANCH,
            sort_order=1,
            is_head_office=False,
        )

    def _template_payload(self, **overrides):
        payload = {
            "name": "25 x 15 Sticker",
            "output_mode": "browser",
            "pdf_layout": None,
            "label_width_mm": 25,
            "label_height_mm": 15,
            "padding_mm": 1.2,
            "show_border": True,
            "special_text": "Special note",
            "print_fields": ["product_name", "barcode", "uom", "pack_size"],
            "attribute_ids": [],
            "copies": 1,
            "isdefault": True,
            "isactive": True,
        }
        payload.update(overrides)
        return payload

    def test_create_and_list_barcode_label_templates(self):
        response = self.client.post(
            f"{reverse('barcode-label-template-list-create')}?entity={self.entity.id}",
            self._template_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "25 x 15 Sticker")
        self.assertTrue(response.json()["isdefault"])

        list_response = self.client.get(
            reverse("barcode-label-template-list-create"),
            {"entity": self.entity.id},
        )
        self.assertEqual(list_response.status_code, 200)
        rows = list_response.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "25 x 15 Sticker")

    def test_default_template_is_unique_per_entity(self):
        first = BarcodeLabelTemplate.objects.create(
            entity=self.entity,
            name="First",
            output_mode="browser",
            label_width_mm=25,
            label_height_mm=15,
            padding_mm=Decimal("1.20"),
            show_border=True,
            special_text="",
            print_fields=["barcode"],
            attribute_ids=[],
            copies=1,
            isdefault=True,
        )
        second = BarcodeLabelTemplate.objects.create(
            entity=self.entity,
            name="Second",
            output_mode="browser",
            label_width_mm=30,
            label_height_mm=20,
            padding_mm=Decimal("1.00"),
            show_border=False,
            special_text="",
            print_fields=["barcode"],
            attribute_ids=[],
            copies=1,
            isdefault=True,
        )

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertFalse(first.isdefault)
        self.assertTrue(second.isdefault)

    def test_default_template_endpoint_returns_selected_template(self):
        template = BarcodeLabelTemplate.objects.create(
            entity=self.entity,
            name="Browser Default",
            output_mode="browser",
            label_width_mm=25,
            label_height_mm=15,
            padding_mm=Decimal("1.20"),
            show_border=True,
            special_text="",
            print_fields=["barcode"],
            attribute_ids=[],
            copies=1,
            isdefault=True,
        )

        response = self.client.get(
            reverse("barcode-label-template-default"),
            {"entity": self.entity.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], template.id)
        self.assertEqual(response.json()["name"], "Browser Default")

    def test_default_template_prefers_subentity_scope_when_requested(self):
        global_template = BarcodeLabelTemplate.objects.create(
            entity=self.entity,
            name="Entity PDF",
            output_mode="pdf",
            pdf_layout=4,
            label_width_mm=25,
            label_height_mm=15,
            padding_mm=Decimal("1.20"),
            show_border=True,
            special_text="",
            print_fields=["barcode"],
            attribute_ids=[],
            copies=1,
            isdefault=True,
        )
        branch_template = BarcodeLabelTemplate.objects.create(
            entity=self.entity,
            subentity=self.subentity,
            name="Branch PDF",
            output_mode="pdf",
            pdf_layout=8,
            label_width_mm=30,
            label_height_mm=20,
            padding_mm=Decimal("1.20"),
            show_border=True,
            special_text="",
            print_fields=["barcode"],
            attribute_ids=[],
            copies=1,
            isdefault=True,
        )

        response = self.client.get(
            reverse("barcode-label-template-default"),
            {"entity": self.entity.id, "subentity": self.subentity.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], branch_template.id)
        self.assertNotEqual(response.json()["id"], global_template.id)

    def test_barcode_pdf_download_uses_selected_template(self):
        uom = UnitOfMeasure.objects.create(
            entity=self.entity,
            code="PCS",
            description="Pieces",
        )
        product = Product.objects.create(
            entity=self.entity,
            productname="Template PDF Product",
            sku="TP-001",
            productdesc="PDF template product",
            productcategory=ProductCategory.objects.create(entity=self.entity, pcategoryname="Templates"),
            base_uom=uom,
            item_classification=ProductClassification.TRADING,
            product_status="active",
            is_service=False,
            isactive=True,
        )
        barcode = ProductBarcode.objects.create(
            product=product,
            uom=uom,
            pack_size=1,
            isprimary=True,
            barcode="7894561230001",
            mrp="250.00",
            selling_price="220.00",
        )
        template = BarcodeLabelTemplate.objects.create(
            entity=self.entity,
            name="PDF Default",
            output_mode="pdf",
            pdf_layout=4,
            label_width_mm=50,
            label_height_mm=30,
            padding_mm=Decimal("1.00"),
            show_border=True,
            special_text="Handle with care",
            print_fields=["product_name", "barcode", "mrp", "selling_price"],
            attribute_ids=[],
            copies=1,
            isdefault=True,
        )

        response = self.client.post(
            f"{reverse('barcode-download-pdf')}?entity={self.entity.id}",
            [
                {
                    "ids": [barcode.id],
                    "layout": 16,
                    "copies": 1,
                    "template_id": template.id,
                }
            ],
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        content = b"".join(response.streaming_content)
        self.assertGreater(len(content), 0)


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
