from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from assets.models import AssetCategory, AssetSettings, default_asset_policy_controls
from financial.models import Credit, Debit, Ledger, accountHead, accounttype
from financial.seeding import FinancialSeedService


CONTRA_ACCOUNT_TYPE_CODE = "1310"
CONTRA_ACCOUNT_TYPE_NAME = "Fixed Asset Contra"
CONTRA_HEAD_CODE = 2310

COMPUTER_ASSET_LEDGER_CODE = 2210
PERIPHERAL_ASSET_LEDGER_CODE = 2211
ACCUMULATED_DEPRECIATION_LEDGER_CODE = 2311
IMPAIRMENT_RESERVE_LEDGER_CODE = 2312
DEPRECIATION_EXPENSE_LEDGER_CODE = 8396
GAIN_ON_SALE_LEDGER_CODE = 8405
LOSS_ON_SALE_LEDGER_CODE = 8406
IMPAIRMENT_EXPENSE_LEDGER_CODE = 8407


class AssetSeedService:
    @classmethod
    @transaction.atomic
    def seed_entity(cls, *, entity, actor=None):
        financial_summary = FinancialSeedService.seed_entity(
            entity=entity,
            actor=actor,
            template_code="indian_accounting_final",
        )

        contra_type = cls._get_or_create_account_type(entity=entity, actor=actor)
        contra_head = cls._get_or_create_account_head(entity=entity, actor=actor, account_type=contra_type)

        computer_asset_ledger = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=COMPUTER_ASSET_LEDGER_CODE,
            name="Computer Equipment",
            accounthead_code=2250,
        )
        peripheral_asset_ledger = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=PERIPHERAL_ASSET_LEDGER_CODE,
            name="Peripheral Equipment",
            accounthead_code=2250,
        )
        accumulated_depreciation_ledger = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=ACCUMULATED_DEPRECIATION_LEDGER_CODE,
            name="Accumulated Depreciation - Assets",
            accounthead_code=contra_head.code,
            accounthead=contra_head,
        )
        impairment_reserve_ledger = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=IMPAIRMENT_RESERVE_LEDGER_CODE,
            name="Impairment Reserve",
            accounthead_code=contra_head.code,
            accounthead=contra_head,
        )
        depreciation_expense_ledger = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=DEPRECIATION_EXPENSE_LEDGER_CODE,
            name="Depreciation Expense",
            accounthead_code=8395,
        )
        gain_on_sale_ledger = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=GAIN_ON_SALE_LEDGER_CODE,
            name="Gain on Sale of Asset",
            accounthead_code=7088,
        )
        loss_on_sale_ledger = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=LOSS_ON_SALE_LEDGER_CODE,
            name="Loss on Sale of Asset",
            accounthead_code=8350,
        )
        impairment_expense_ledger = cls._get_or_create_ledger(
            entity=entity,
            actor=actor,
            ledger_code=IMPAIRMENT_EXPENSE_LEDGER_CODE,
            name="Impairment Expense",
            accounthead_code=8350,
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
        elif not settings_obj.policy_controls:
            settings_obj.policy_controls = default_asset_policy_controls()
            settings_updated = True

        if actor and not settings_obj.created_by_id:
            settings_obj.created_by = actor
            settings_updated = True
        if actor:
            settings_obj.updated_by = actor
            settings_updated = True

        if settings_updated:
            settings_obj.save()

        categories = [
            cls._get_or_create_category(
                entity=entity,
                actor=actor,
                code="COMPUTER",
                name="Computer",
                asset_ledger=computer_asset_ledger,
                accumulated_depreciation_ledger=accumulated_depreciation_ledger,
                depreciation_expense_ledger=depreciation_expense_ledger,
                impairment_expense_ledger=impairment_expense_ledger,
                impairment_reserve_ledger=impairment_reserve_ledger,
                gain_on_sale_ledger=gain_on_sale_ledger,
                loss_on_sale_ledger=loss_on_sale_ledger,
                useful_life_months=36,
            ),
            cls._get_or_create_category(
                entity=entity,
                actor=actor,
                code="PERIPHERAL",
                name="Peripheral",
                asset_ledger=peripheral_asset_ledger,
                accumulated_depreciation_ledger=accumulated_depreciation_ledger,
                depreciation_expense_ledger=depreciation_expense_ledger,
                impairment_expense_ledger=impairment_expense_ledger,
                impairment_reserve_ledger=impairment_reserve_ledger,
                gain_on_sale_ledger=gain_on_sale_ledger,
                loss_on_sale_ledger=loss_on_sale_ledger,
                useful_life_months=24,
            ),
        ]

        return {
            "financial_template": financial_summary.get("template_code"),
            "financial_settings_id": financial_summary.get("financial_settings_id"),
            "contra_account_type_id": contra_type.id,
            "contra_account_head_id": contra_head.id,
            "asset_ledger_count": 2,
            "contra_ledger_count": 2,
            "disposal_ledger_count": 2,
            "category_count": len(categories),
            "asset_settings_id": settings_obj.id,
        }

    @staticmethod
    def _get_account_head(*, entity, code: int):
        return accountHead.objects.filter(entity=entity, code=code).first()

    @classmethod
    def _get_or_create_account_type(cls, *, entity, actor=None):
        acc_type, _ = accounttype.objects.get_or_create(
            entity=entity,
            accounttypecode=CONTRA_ACCOUNT_TYPE_CODE,
            defaults={
                "accounttypename": CONTRA_ACCOUNT_TYPE_NAME,
                "balanceType": False,
                "createdby": actor,
            },
        )
        acc_type.accounttypename = CONTRA_ACCOUNT_TYPE_NAME
        acc_type.balanceType = False
        if actor and not acc_type.createdby_id:
            acc_type.createdby = actor
        acc_type.save()
        return acc_type

    @classmethod
    def _get_or_create_account_head(cls, *, entity, actor=None, account_type=None):
        head, _ = accountHead.objects.get_or_create(
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
        head.name = "Accumulated Depreciation & Reserves"
        head.balanceType = Credit
        head.drcreffect = Credit
        head.detailsingroup = 3
        head.accounttype = account_type
        head.canbedeleted = False
        if actor and not head.createdby_id:
            head.createdby = actor
        head.save()
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
    ):
        if accounthead is None and accounthead_code is not None:
            accounthead = cls._get_account_head(entity=entity, code=accounthead_code)
            if accounthead is None:
                raise ValueError(f"Account head {accounthead_code} is required before seeding asset ledgers.")

        ledger, _ = Ledger.objects.get_or_create(
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
        ledger.name = name
        ledger.legal_name = name
        ledger.accounthead = accounthead
        ledger.creditaccounthead = accounthead
        ledger.accounttype = getattr(accounthead, "accounttype", None)
        ledger.is_system = True
        ledger.is_party = False
        ledger.canbedeleted = False
        if actor and not ledger.createdby_id:
            ledger.createdby = actor
        ledger.save()
        return ledger

    @classmethod
    def _get_or_create_category(
        cls,
        *,
        entity,
        actor=None,
        code: str,
        name: str,
        asset_ledger,
        accumulated_depreciation_ledger,
        depreciation_expense_ledger,
        impairment_expense_ledger,
        impairment_reserve_ledger,
        gain_on_sale_ledger,
        loss_on_sale_ledger,
        useful_life_months: int,
    ):
        category, _ = AssetCategory.objects.get_or_create(
            entity=entity,
            subentity=None,
            code=code,
            defaults={
                "name": name,
                "nature": AssetCategory.AssetNature.TANGIBLE,
                "depreciation_method": AssetCategory.DepreciationMethod.SLM,
                "useful_life_months": useful_life_months,
                "residual_value_percent": Decimal("5.0000"),
                "capitalization_threshold": Decimal("0.00"),
                "asset_ledger": asset_ledger,
                "accumulated_depreciation_ledger": accumulated_depreciation_ledger,
                "depreciation_expense_ledger": depreciation_expense_ledger,
                "impairment_expense_ledger": impairment_expense_ledger,
                "impairment_reserve_ledger": impairment_reserve_ledger,
                "gain_on_sale_ledger": gain_on_sale_ledger,
                "loss_on_sale_ledger": loss_on_sale_ledger,
                "created_by": actor,
                "updated_by": actor,
            },
        )
        category.name = name
        category.nature = AssetCategory.AssetNature.TANGIBLE
        category.depreciation_method = AssetCategory.DepreciationMethod.SLM
        category.useful_life_months = useful_life_months
        category.residual_value_percent = Decimal("5.0000")
        category.capitalization_threshold = Decimal("0.00")
        category.asset_ledger = asset_ledger
        category.accumulated_depreciation_ledger = accumulated_depreciation_ledger
        category.depreciation_expense_ledger = depreciation_expense_ledger
        category.impairment_expense_ledger = impairment_expense_ledger
        category.impairment_reserve_ledger = impairment_reserve_ledger
        category.gain_on_sale_ledger = gain_on_sale_ledger
        category.loss_on_sale_ledger = loss_on_sale_ledger
        if actor and not category.created_by_id:
            category.created_by = actor
        if actor:
            category.updated_by = actor
        category.save()
        return category
