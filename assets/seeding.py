from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from assets.models import (
    AssetCategory,
    AssetSettings,
    default_asset_accounting_controls,
    default_asset_policy_controls,
    default_asset_traceability_controls,
)
from financial.models import Credit, Debit, Ledger, accountHead, accounttype
from financial.seeding import FinancialSeedService


CONTRA_ACCOUNT_TYPE_CODE = "1310"
CONTRA_ACCOUNT_TYPE_NAME = "Fixed Asset Contra"
CONTRA_HEAD_CODE = 2310
NON_CURRENT_ASSET_TYPE_CODE = "1300"
NON_CURRENT_ASSET_TYPE_NAME = "Non Current Assets"
ROU_HEAD_CODE = 2285
ROU_HEAD_NAME = "Right-of-Use Assets"

ACCUMULATED_DEPRECIATION_LEDGER_CODE = 2311
IMPAIRMENT_RESERVE_LEDGER_CODE = 2312
VEHICLE_ACCUMULATED_DEPRECIATION_LEDGER_CODE = 2313
INTANGIBLE_ACCUMULATED_AMORTIZATION_LEDGER_CODE = 2314
ROU_ACCUMULATED_DEPRECIATION_LEDGER_CODE = 2315
DEPRECIATION_EXPENSE_LEDGER_CODE = 8396
AMORTIZATION_EXPENSE_LEDGER_CODE = 8397
GAIN_ON_SALE_LEDGER_CODE = 8405
LOSS_ON_SALE_LEDGER_CODE = 8406
IMPAIRMENT_EXPENSE_LEDGER_CODE = 8407

ASSET_LEDGER_DEFINITIONS = (
    {"key": "land", "ledger_code": 2201, "name": "Land", "accounthead_code": 2210},
    {"key": "building", "ledger_code": 2202, "name": "Building", "accounthead_code": 2220},
    {"key": "plant_machinery", "ledger_code": 2203, "name": "Plant & Machinery", "accounthead_code": 2230},
    {"key": "furniture_fixture", "ledger_code": 2204, "name": "Furniture & Fixtures", "accounthead_code": 2240},
    {"key": "office_equipment", "ledger_code": 2206, "name": "Office Equipment", "accounthead_code": 2260},
    {"key": "vehicles", "ledger_code": 2207, "name": "Vehicles", "accounthead_code": 2270},
    {"key": "cwip", "ledger_code": 2209, "name": "Capital Work In Progress", "accounthead_code": 2290},
    {"key": "computers", "ledger_code": 2210, "name": "Computers and IT Equipment", "accounthead_code": 2250},
    {"key": "peripherals", "ledger_code": 2211, "name": "Printers and Peripherals", "accounthead_code": 2250},
    {"key": "server_network", "ledger_code": 2212, "name": "Servers and Network Equipment", "accounthead_code": 2250},
    {"key": "leasehold_improvement", "ledger_code": 2213, "name": "Leasehold Improvements", "accounthead_code": 2220},
    {"key": "electrical", "ledger_code": 2214, "name": "Electrical Installations", "accounthead_code": 2220},
    {"key": "hvac", "ledger_code": 2215, "name": "Air Conditioners and HVAC", "accounthead_code": 2260},
    {"key": "tools_equipment", "ledger_code": 2216, "name": "Tools and Equipment", "accounthead_code": 2230},
    {"key": "security_equipment", "ledger_code": 2217, "name": "Security and Surveillance Equipment", "accounthead_code": 2260},
    {"key": "lab_medical", "ledger_code": 2218, "name": "Medical and Laboratory Equipment", "accounthead_code": 2230},
    {"key": "software", "ledger_code": 2219, "name": "Intangible Assets - Software", "accounthead_code": 2280},
    {"key": "license", "ledger_code": 2221, "name": "Intangible Assets - Licenses", "accounthead_code": 2280},
    {"key": "website_digital", "ledger_code": 2222, "name": "Website and Digital Assets", "accounthead_code": 2280},
    {"key": "rou_asset", "ledger_code": 2223, "name": "Right-of-Use Assets", "accounthead_code": ROU_HEAD_CODE},
)

CATEGORY_DEFINITIONS = (
    {
        "code": "LAND",
        "name": "Land",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 9999,
        "residual_value_percent": Decimal("0.0000"),
        "asset_ledger_key": "land",
        "accumulated_depreciation_key": None,
        "depreciation_expense_key": None,
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "BUILDING",
        "name": "Building",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 720,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "building",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "LEASEHOLD_IMPROVEMENT",
        "name": "Leasehold Improvement",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 120,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "leasehold_improvement",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "PLANT_MACHINERY",
        "name": "Plant and Machinery",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 180,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "plant_machinery",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "FURNITURE_FIXTURE",
        "name": "Furniture and Fixture",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 120,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "furniture_fixture",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "OFFICE_EQUIPMENT",
        "name": "Office Equipment",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 60,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "office_equipment",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "COMPUTER",
        "name": "Computers",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 36,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "computers",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "PERIPHERAL",
        "name": "Printers and Peripherals",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 24,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "peripherals",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "SERVER_NETWORK",
        "name": "Servers and Network Equipment",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 36,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "server_network",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "VEHICLE",
        "name": "Vehicles",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 96,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "vehicles",
        "accumulated_depreciation_key": "acc_dep_vehicle",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "ELECTRICAL",
        "name": "Electrical Installations",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 120,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "electrical",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "HVAC",
        "name": "Air Conditioners and HVAC",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 84,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "hvac",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "TOOLS_EQUIPMENT",
        "name": "Tools and Equipment",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 60,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "tools_equipment",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "SECURITY_EQUIPMENT",
        "name": "Security Equipment",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 60,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "security_equipment",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "LAB_MEDICAL",
        "name": "Laboratory / Medical Equipment",
        "nature": AssetCategory.AssetNature.TANGIBLE,
        "useful_life_months": 120,
        "residual_value_percent": Decimal("5.0000"),
        "asset_ledger_key": "lab_medical",
        "accumulated_depreciation_key": "acc_dep_tangible",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
    {
        "code": "SOFTWARE",
        "name": "Software",
        "nature": AssetCategory.AssetNature.INTANGIBLE,
        "useful_life_months": 36,
        "residual_value_percent": Decimal("0.0000"),
        "asset_ledger_key": "software",
        "accumulated_depreciation_key": "acc_amortization_intangible",
        "depreciation_expense_key": "amortization_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": None,
    },
    {
        "code": "LICENSE",
        "name": "Licenses",
        "nature": AssetCategory.AssetNature.INTANGIBLE,
        "useful_life_months": 36,
        "residual_value_percent": Decimal("0.0000"),
        "asset_ledger_key": "license",
        "accumulated_depreciation_key": "acc_amortization_intangible",
        "depreciation_expense_key": "amortization_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": None,
    },
    {
        "code": "WEBSITE_DIGITAL",
        "name": "Website / Digital Assets",
        "nature": AssetCategory.AssetNature.INTANGIBLE,
        "useful_life_months": 36,
        "residual_value_percent": Decimal("0.0000"),
        "asset_ledger_key": "website_digital",
        "accumulated_depreciation_key": "acc_amortization_intangible",
        "depreciation_expense_key": "amortization_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": None,
    },
    {
        "code": "ROU_ASSET",
        "name": "Right-of-Use Asset",
        "nature": AssetCategory.AssetNature.ROU,
        "useful_life_months": 60,
        "residual_value_percent": Decimal("0.0000"),
        "asset_ledger_key": "rou_asset",
        "accumulated_depreciation_key": "acc_dep_rou",
        "depreciation_expense_key": "depreciation_expense",
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": None,
    },
    {
        "code": "CWIP_GENERAL",
        "name": "Capital Work-in-Progress",
        "nature": AssetCategory.AssetNature.CAPITAL_WIP,
        "useful_life_months": 9999,
        "residual_value_percent": Decimal("0.0000"),
        "asset_ledger_key": "cwip",
        "accumulated_depreciation_key": None,
        "depreciation_expense_key": None,
        "impairment_expense_key": "impairment_expense",
        "impairment_reserve_key": "impairment_reserve",
        "gain_on_sale_key": "gain_on_sale",
        "loss_on_sale_key": "loss_on_sale",
        "cwip_ledger_key": "cwip",
    },
)


class AssetSeedService:
    @classmethod
    @transaction.atomic
    def seed_entity(cls, *, entity, actor=None):
        summary = {
            "account_types_created": 0,
            "account_types_backfilled": 0,
            "account_heads_created": 0,
            "account_heads_backfilled": 0,
            "ledgers_created": 0,
            "ledgers_backfilled": 0,
            "categories_created": 0,
            "categories_backfilled": 0,
            "settings_created": 0,
            "settings_backfilled": 0,
        }
        financial_summary = FinancialSeedService.seed_entity(
            entity=entity,
            actor=actor,
            template_code="indian_accounting_final",
        )

        contra_type = cls._get_or_create_account_type(entity=entity, actor=actor, summary=summary)
        contra_head = cls._get_or_create_account_head(entity=entity, actor=actor, account_type=contra_type, summary=summary)
        rou_head = cls._get_or_create_standard_account_head(
            entity=entity,
            actor=actor,
            code=ROU_HEAD_CODE,
            name=ROU_HEAD_NAME,
            type_code=NON_CURRENT_ASSET_TYPE_CODE,
            type_name=NON_CURRENT_ASSET_TYPE_NAME,
            summary=summary,
        )

        ledger_map = {}
        for definition in ASSET_LEDGER_DEFINITIONS:
            ledger_map[definition["key"]] = cls._get_or_create_ledger(
                entity=entity,
                actor=actor,
                ledger_code=definition["ledger_code"],
                name=definition["name"],
                accounthead_code=definition["accounthead_code"],
                accounthead=rou_head if definition["accounthead_code"] == ROU_HEAD_CODE else None,
                summary=summary,
            )

        ledger_map["acc_dep_tangible"] = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=ACCUMULATED_DEPRECIATION_LEDGER_CODE,
            name="Accumulated Depreciation - Tangible Assets",
            accounthead_code=contra_head.code,
            accounthead=contra_head,
            summary=summary,
        )
        ledger_map["impairment_reserve"] = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=IMPAIRMENT_RESERVE_LEDGER_CODE,
            name="Impairment Reserve - Assets",
            accounthead_code=contra_head.code,
            accounthead=contra_head,
            summary=summary,
        )
        ledger_map["acc_dep_vehicle"] = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=VEHICLE_ACCUMULATED_DEPRECIATION_LEDGER_CODE,
            name="Accumulated Depreciation - Vehicles",
            accounthead_code=contra_head.code,
            accounthead=contra_head,
            summary=summary,
        )
        ledger_map["acc_amortization_intangible"] = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=INTANGIBLE_ACCUMULATED_AMORTIZATION_LEDGER_CODE,
            name="Accumulated Amortization - Intangible Assets",
            accounthead_code=contra_head.code,
            accounthead=contra_head,
            summary=summary,
        )
        ledger_map["acc_dep_rou"] = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=ROU_ACCUMULATED_DEPRECIATION_LEDGER_CODE,
            name="Accumulated Depreciation - ROU Assets",
            accounthead_code=contra_head.code,
            accounthead=contra_head,
            summary=summary,
        )
        ledger_map["depreciation_expense"] = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=DEPRECIATION_EXPENSE_LEDGER_CODE,
            name="Depreciation Expense",
            accounthead_code=8395,
            summary=summary,
        )
        ledger_map["amortization_expense"] = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=AMORTIZATION_EXPENSE_LEDGER_CODE,
            name="Amortization Expense",
            accounthead_code=8395,
            summary=summary,
        )
        ledger_map["gain_on_sale"] = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=GAIN_ON_SALE_LEDGER_CODE,
            name="Gain on Sale of Asset",
            accounthead_code=7088,
            summary=summary,
        )
        ledger_map["loss_on_sale"] = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=LOSS_ON_SALE_LEDGER_CODE,
            name="Loss on Sale of Asset",
            accounthead_code=8350,
            summary=summary,
        )
        ledger_map["impairment_expense"] = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=IMPAIRMENT_EXPENSE_LEDGER_CODE,
            name="Impairment Expense",
            accounthead_code=8350,
            summary=summary,
        )

        settings_obj, settings_created = AssetSettings.objects.get_or_create(entity=entity, subentity=None)
        settings_updated = False
        if settings_created:
            default_updates = {
                "default_doc_code_asset": "FA",
                "default_doc_code_disposal": "FAD",
                "default_workflow_action": AssetSettings.DefaultWorkflowAction.DRAFT,
                "default_depreciation_method": AssetSettings.DefaultDepreciationMethod.SLM,
                "default_useful_life_months": 36,
                "default_residual_value_percent": Decimal("5.0000"),
                "depreciation_posting_day": 30,
                "allow_multiple_asset_books": False,
                "auto_post_depreciation": False,
                "auto_number_assets": True,
                "require_asset_tag": False,
                "enable_component_accounting": False,
                "enable_impairment_tracking": True,
                "capitalization_threshold": Decimal("0.00"),
                "policy_controls": default_asset_policy_controls(),
            }
            for field_name, value in default_updates.items():
                setattr(settings_obj, field_name, value)
            settings_updated = True
            summary["settings_created"] += 1
        else:
            settings_updates = {
                "default_doc_code_asset": "FA",
                "default_doc_code_disposal": "FAD",
                "policy_controls": default_asset_policy_controls(),
            }
            settings_updated = cls._assign_missing_fields(settings_obj, settings_updates) or settings_updated
            if settings_updated:
                summary["settings_backfilled"] += 1

        if actor and not settings_obj.created_by_id:
            settings_obj.created_by = actor
            settings_updated = True
        if actor:
            settings_obj.updated_by = actor
            settings_updated = True

        if settings_updated:
            settings_obj.save()

        categories = []
        for definition in CATEGORY_DEFINITIONS:
            categories.append(
                cls._get_or_create_category(
                    entity=entity,
                    actor=actor,
                    code=definition["code"],
                    name=definition["name"],
                    nature=definition["nature"],
                    asset_ledger=ledger_map[definition["asset_ledger_key"]],
                    accumulated_depreciation_ledger=cls._get_mapped_ledger(
                        ledger_map,
                        definition["accumulated_depreciation_key"],
                    ),
                    depreciation_expense_ledger=cls._get_mapped_ledger(
                        ledger_map,
                        definition["depreciation_expense_key"],
                    ),
                    impairment_expense_ledger=cls._get_mapped_ledger(
                        ledger_map,
                        definition["impairment_expense_key"],
                    ),
                    impairment_reserve_ledger=cls._get_mapped_ledger(
                        ledger_map,
                        definition["impairment_reserve_key"],
                    ),
                    gain_on_sale_ledger=cls._get_mapped_ledger(
                        ledger_map,
                        definition["gain_on_sale_key"],
                    ),
                    loss_on_sale_ledger=cls._get_mapped_ledger(
                        ledger_map,
                        definition["loss_on_sale_key"],
                    ),
                    cwip_ledger=cls._get_mapped_ledger(
                        ledger_map,
                        definition["cwip_ledger_key"],
                    ),
                    useful_life_months=definition["useful_life_months"],
                    residual_value_percent=definition["residual_value_percent"],
                    summary=summary,
                )
            )

        return {
            "financial_template": financial_summary.get("template_code"),
            "financial_settings_id": financial_summary.get("financial_settings_id"),
            "contra_account_type_id": contra_type.id,
            "contra_account_head_id": contra_head.id,
            "asset_ledger_count": len(ASSET_LEDGER_DEFINITIONS),
            "contra_ledger_count": 4,
            "disposal_ledger_count": 2,
            "category_count": len(categories),
            "asset_settings_id": settings_obj.id,
            **summary,
        }

    @staticmethod
    def _get_account_head(*, entity, code: int):
        return accountHead.objects.filter(entity=entity, code=code).first()

    @classmethod
    def _get_account_type(cls, *, entity, code: str):
        return accounttype.objects.filter(entity=entity, accounttypecode=code).first()

    @classmethod
    def _get_or_create_account_type(cls, *, entity, actor=None, summary=None):
        acc_type, created = accounttype.objects.get_or_create(
            entity=entity,
            accounttypecode=CONTRA_ACCOUNT_TYPE_CODE,
            defaults={
                "accounttypename": CONTRA_ACCOUNT_TYPE_NAME,
                "balanceType": False,
                "createdby": actor,
            },
        )
        if created and summary is not None:
            summary["account_types_created"] += 1

        updated = cls._assign_missing_fields(
            acc_type,
            {
                "accounttypename": CONTRA_ACCOUNT_TYPE_NAME,
            },
        )
        if actor and not acc_type.createdby_id:
            acc_type.createdby = actor
            updated = True
        if updated:
            acc_type.save()
            if not created and summary is not None:
                summary["account_types_backfilled"] += 1
        return acc_type

    @classmethod
    def _get_or_create_standard_account_head(
        cls,
        *,
        entity,
        actor=None,
        code: int,
        name: str,
        type_code: str,
        type_name: str,
        summary=None,
    ):
        account_type = cls._get_account_type(entity=entity, code=type_code)
        if account_type is None:
            account_type, created = accounttype.objects.get_or_create(
                entity=entity,
                accounttypecode=type_code,
                defaults={
                    "accounttypename": type_name,
                    "balanceType": True,
                    "createdby": actor,
                },
            )
            if created and summary is not None:
                summary["account_types_created"] += 1

        head, created = accountHead.objects.get_or_create(
            entity=entity,
            code=code,
            defaults={
                "name": name,
                "balanceType": Debit,
                "drcreffect": Debit,
                "detailsingroup": 3,
                "accounttype": account_type,
                "canbedeleted": False,
                "createdby": actor,
            },
        )
        if created and summary is not None:
            summary["account_heads_created"] += 1

        updated = cls._assign_missing_fields(
            head,
            {
                "name": name,
                "balanceType": Debit,
                "drcreffect": Debit,
                "detailsingroup": 3,
                "accounttype": account_type,
            },
        )
        if actor and not head.createdby_id:
            head.createdby = actor
            updated = True
        if updated:
            head.save()
            if not created and summary is not None:
                summary["account_heads_backfilled"] += 1
        return head

    @classmethod
    def _get_or_create_account_head(cls, *, entity, actor=None, account_type=None, summary=None):
        head, created = accountHead.objects.get_or_create(
            entity=entity,
            code=CONTRA_HEAD_CODE,
            defaults={
                "name": "Accumulated Depreciation & Reserves",
                "balanceType": Credit,
                "drcreffect": Credit,
                "detailsingroup": 3,
                "accounttype": account_type,
                "canbedeleted": False,
                "createdby": actor,
            },
        )
        if created and summary is not None:
            summary["account_heads_created"] += 1

        updated = cls._assign_missing_fields(
            head,
            {
                "name": "Accumulated Depreciation & Reserves",
                "balanceType": Credit,
                "drcreffect": Credit,
                "detailsingroup": 3,
                "accounttype": account_type,
            },
        )
        if actor and not head.createdby_id:
            head.createdby = actor
            updated = True
        if updated:
            head.save()
            if not created and summary is not None:
                summary["account_heads_backfilled"] += 1
        return head

    @classmethod
    def _get_or_create_ledger(
        cls,
        *,
        entity,
        actor=None,
        ledger_code: int,
        name: str,
        accounthead_code: int | None = None,
        accounthead=None,
        summary=None,
    ):
        if accounthead is None and accounthead_code is not None:
            accounthead = cls._get_account_head(entity=entity, code=accounthead_code)
            if accounthead is None:
                raise ValueError(f"Account head {accounthead_code} is required before seeding asset ledgers.")

        ledger, created = Ledger.objects.get_or_create(
            entity=entity,
            ledger_code=ledger_code,
            defaults={
                "name": name,
                "legal_name": name,
                "accounthead": accounthead,
                "creditaccounthead": accounthead,
                "accounttype": getattr(accounthead, "accounttype", None),
                "is_system": True,
                "is_party": False,
                "canbedeleted": False,
                "createdby": actor,
            },
        )
        if created and summary is not None:
            summary["ledgers_created"] += 1

        updated = cls._assign_missing_fields(
            ledger,
            {
                "name": name,
                "legal_name": name,
                "accounthead": accounthead,
                "creditaccounthead": accounthead,
                "accounttype": getattr(accounthead, "accounttype", None),
            },
        )
        if actor and not ledger.createdby_id:
            ledger.createdby = actor
            updated = True
        if updated:
            ledger.save()
            if not created and summary is not None:
                summary["ledgers_backfilled"] += 1
        return ledger

    @classmethod
    def _get_or_create_category(
        cls,
        *,
        entity,
        actor=None,
        code: str,
        name: str,
        nature: str,
        asset_ledger,
        accumulated_depreciation_ledger,
        depreciation_expense_ledger,
        impairment_expense_ledger,
        impairment_reserve_ledger,
        gain_on_sale_ledger,
        loss_on_sale_ledger,
        cwip_ledger,
        useful_life_months: int,
        residual_value_percent: Decimal,
        summary=None,
    ):
        category, created = AssetCategory.objects.get_or_create(
            entity=entity,
            subentity=None,
            code=code,
            defaults={
                "name": name,
                "nature": nature,
                "depreciation_method": AssetCategory.DepreciationMethod.SLM,
                "useful_life_months": useful_life_months,
                "residual_value_percent": residual_value_percent,
                "capitalization_threshold": Decimal("0.00"),
                "asset_ledger": asset_ledger,
                "accumulated_depreciation_ledger": accumulated_depreciation_ledger,
                "depreciation_expense_ledger": depreciation_expense_ledger,
                "impairment_expense_ledger": impairment_expense_ledger,
                "impairment_reserve_ledger": impairment_reserve_ledger,
                "cwip_ledger": cwip_ledger,
                "gain_on_sale_ledger": gain_on_sale_ledger,
                "loss_on_sale_ledger": loss_on_sale_ledger,
                "created_by": actor,
                "updated_by": actor,
            },
        )
        if created and summary is not None:
            summary["categories_created"] += 1

        updated = cls._assign_missing_fields(
            category,
            {
                "name": name,
                "nature": nature,
                "depreciation_method": AssetCategory.DepreciationMethod.SLM,
                "useful_life_months": useful_life_months,
                "residual_value_percent": residual_value_percent,
                "capitalization_threshold": Decimal("0.00"),
                "asset_ledger": asset_ledger,
                "accumulated_depreciation_ledger": accumulated_depreciation_ledger,
                "depreciation_expense_ledger": depreciation_expense_ledger,
                "impairment_expense_ledger": impairment_expense_ledger,
                "impairment_reserve_ledger": impairment_reserve_ledger,
                "cwip_ledger": cwip_ledger,
                "gain_on_sale_ledger": gain_on_sale_ledger,
                "loss_on_sale_ledger": loss_on_sale_ledger,
                "traceability_controls": default_asset_traceability_controls(),
                "accounting_controls": default_asset_accounting_controls(),
            },
        )
        if actor and not category.created_by_id:
            category.created_by = actor
            updated = True
        if actor:
            category.updated_by = actor
            updated = True
        if updated:
            category.save()
            if not created and summary is not None:
                summary["categories_backfilled"] += 1
        return category

    @staticmethod
    def _assign_missing_fields(instance, updates):
        updated = False
        for field_name, value in updates.items():
            current_value = getattr(instance, field_name)
            if AssetSeedService._is_missing_value(current_value):
                setattr(instance, field_name, value)
                updated = True
        return updated

    @staticmethod
    def _is_missing_value(value):
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        if isinstance(value, (dict, list, tuple, set)):
            return len(value) == 0
        return False

    @staticmethod
    def _get_mapped_ledger(ledger_map, key):
        if key is None:
            return None
        return ledger_map[key]
