from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Max, Q, Sum
from django.utils import timezone

from assets.models import AssetCategory, AssetSettings, DepreciationRun, FixedAsset
from assets.services.depreciation import attach_preview_lines, preview_run, q2 as dep_q2
from assets.services.settings import AssetSettingsService
from financial.models import Ledger
from posting.models import TxnType
from posting.services.posting_service import JLInput, PostingService

Q2 = Decimal("0.01")
ZERO = Decimal("0.00")


def q2(value) -> Decimal:
    return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)


def _resolve_entityfin_id(instance, fallback=None):
    return getattr(instance, "entityfinid_id", None) or fallback


def _jl_for_ledger(*, ledger_id: int, drcr: bool, amount: Decimal, description: str) -> JLInput:
    ledger = Ledger.objects.filter(id=ledger_id).only("id", "accounthead_id").first()
    if not ledger or not ledger.accounthead_id:
        raise ValueError(f"Ledger {ledger_id} must be linked to an account head for posting.")
    return JLInput(accounthead_id=ledger.accounthead_id, ledger_id=ledger_id, drcr=drcr, amount=amount, description=description)


class AssetService:
    @staticmethod
    def generate_asset_code(*, entity_id: int, settings: AssetSettings) -> str:
        prefix = settings.default_doc_code_asset or "FA"
        last_code = (
            FixedAsset.objects.filter(entity_id=entity_id, asset_code__startswith=f"{prefix}-")
            .aggregate(max_code=Max("asset_code"))
            .get("max_code")
        )
        if last_code and "-" in last_code:
            try:
                seq = int(last_code.rsplit("-", 1)[1]) + 1
            except ValueError:
                seq = FixedAsset.objects.filter(entity_id=entity_id).count() + 1
        else:
            seq = FixedAsset.objects.filter(entity_id=entity_id).count() + 1
        return f"{prefix}-{seq:06d}"

    @staticmethod
    def asset_queryset(*, entity_id: int, subentity_id: int | None = None, search: str | None = None):
        qs = FixedAsset.objects.select_related("category", "ledger", "vendor_account", "subentity").filter(entity_id=entity_id)
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        if search:
            qs = qs.filter(
                Q(asset_code__icontains=search)
                | Q(asset_name__icontains=search)
                | Q(asset_tag__icontains=search)
                | Q(serial_number__icontains=search)
            )
        return qs.order_by("-id")

    @staticmethod
    def create_asset(*, data: dict, user_id: int | None = None) -> FixedAsset:
        entity = data["entity"]
        entity_id = entity.id
        subentity = data.get("subentity")
        subentity_id = subentity.id if subentity else None
        settings = AssetSettingsService.get_settings(entity_id, subentity_id)
        payload = dict(data)
        if not payload.get("asset_code") and settings.auto_number_assets:
            payload["asset_code"] = AssetService.generate_asset_code(entity_id=entity_id, settings=settings)

        category = payload["category"]
        payload.setdefault("useful_life_months", category.useful_life_months or settings.default_useful_life_months)
        payload.setdefault("depreciation_method", category.depreciation_method or settings.default_depreciation_method)
        if payload.get("residual_value") in (None, ""):
            residual_percent = q2(category.residual_value_percent or settings.default_residual_value_percent)
            payload["residual_value"] = q2(q2(payload.get("gross_block")) * residual_percent / Decimal("100.00"))
        payload.setdefault("net_book_value", q2(payload.get("gross_block")))
        asset = FixedAsset.objects.create(created_by_id=user_id, updated_by_id=user_id, **payload)
        return asset

    @staticmethod
    def update_asset(*, instance: FixedAsset, data: dict, user_id: int | None = None) -> FixedAsset:
        immutable_if_posted = {"entity", "entityfinid", "subentity", "category", "gross_block"}
        for key, value in data.items():
            if instance.capitalization_posting_batch_id and key in immutable_if_posted:
                continue
            setattr(instance, key, value)
        instance.updated_by_id = user_id
        instance.net_book_value = q2(instance.gross_block) - q2(instance.accumulated_depreciation) - q2(instance.impairment_amount)
        instance.save()
        return instance

    @staticmethod
    @transaction.atomic
    def capitalize_asset(
        *,
        asset: FixedAsset,
        counter_ledger_id: int,
        capitalization_date: date,
        user_id: int | None = None,
        narration: str | None = None,
    ) -> FixedAsset:
        if asset.status in {FixedAsset.AssetStatus.ACTIVE, FixedAsset.AssetStatus.DISPOSED, FixedAsset.AssetStatus.SCRAPPED}:
            raise ValueError("Only draft or capital-WIP assets can be capitalized.")
        if asset.capitalization_posting_batch_id:
            raise ValueError("This asset is already capitalized.")
        asset_ledger_id = asset.ledger_id or asset.category.asset_ledger_id
        if not asset_ledger_id:
            raise ValueError("Asset ledger is required on asset or asset category before capitalization.")
        if not counter_ledger_id:
            raise ValueError("Counter ledger is required for capitalization.")
        amount = q2(asset.gross_block)
        if amount <= ZERO:
            raise ValueError("Asset gross block must be greater than zero for capitalization.")

        posting = PostingService(
            entity_id=asset.entity_id,
            entityfin_id=_resolve_entityfin_id(asset),
            subentity_id=asset.subentity_id,
            user_id=user_id,
        )
        entry = posting.post(
            txn_type=TxnType.FIXED_ASSET_CAPITALIZATION,
            txn_id=asset.id,
            voucher_no=asset.asset_code,
            voucher_date=capitalization_date,
            posting_date=capitalization_date,
            narration=narration or f"Capitalization of asset {asset.asset_code}",
            jl_inputs=[
                _jl_for_ledger(ledger_id=asset_ledger_id, drcr=True, amount=amount, description=asset.asset_name),
                _jl_for_ledger(ledger_id=counter_ledger_id, drcr=False, amount=amount, description=asset.asset_name),
            ],
        )
        asset.status = FixedAsset.AssetStatus.ACTIVE
        asset.capitalization_date = capitalization_date
        asset.put_to_use_date = asset.put_to_use_date or capitalization_date
        asset.depreciation_start_date = asset.depreciation_start_date or capitalization_date
        asset.capitalization_posting_batch = entry.posting_batch
        asset.net_book_value = q2(asset.gross_block) - q2(asset.accumulated_depreciation) - q2(asset.impairment_amount)
        asset.updated_by_id = user_id
        asset.save()
        return asset

    @staticmethod
    def eligible_assets_for_run(run: DepreciationRun, *, category_id: int | None = None):
        qs = FixedAsset.objects.select_related("category").filter(
            entity_id=run.entity_id,
            status=FixedAsset.AssetStatus.ACTIVE,
        )
        if run.subentity_id is not None:
            qs = qs.filter(subentity_id=run.subentity_id)
        if category_id:
            qs = qs.filter(category_id=category_id)
        qs = qs.filter(
            Q(capitalization_date__isnull=False),
            Q(capitalization_date__lte=run.period_to),
        ).filter(Q(disposal_date__isnull=True) | Q(disposal_date__gt=run.period_from))
        return qs

    @staticmethod
    @transaction.atomic
    def calculate_run(*, run: DepreciationRun, category_id: int | None = None, user_id: int | None = None) -> DepreciationRun:
        if run.status == DepreciationRun.RunStatus.POSTED:
            raise ValueError("Posted depreciation run cannot be recalculated.")
        if run.status == DepreciationRun.RunStatus.CANCELLED:
            raise ValueError("Cancelled depreciation run cannot be recalculated.")
        assets_qs = AssetService.eligible_assets_for_run(run, category_id=category_id)
        preview_lines = preview_run(assets_qs=assets_qs, period_from=run.period_from, period_to=run.period_to)
        attach_preview_lines(run, preview_lines)
        run.total_assets = len(preview_lines)
        run.total_amount = dep_q2(sum((line.depreciation_amount for line in preview_lines), ZERO))
        run.status = DepreciationRun.RunStatus.CALCULATED
        run.calculated_at = timezone.now()
        run.updated_by_id = user_id
        run.save(update_fields=["total_assets", "total_amount", "status", "calculated_at", "updated_by"])
        return run

    @staticmethod
    @transaction.atomic
    def post_run(*, run: DepreciationRun, user_id: int | None = None) -> DepreciationRun:
        if run.status != DepreciationRun.RunStatus.CALCULATED:
            raise ValueError("Depreciation run must be in calculated state before posting.")
        lines = list(run.lines.select_related("asset", "asset__category"))
        if not lines:
            raise ValueError("Depreciation run has no lines to post.")

        aggregated: dict[tuple[int, int], Decimal] = {}
        for line in lines:
            exp_ledger = line.asset.category.depreciation_expense_ledger_id
            acc_ledger = line.asset.category.accumulated_depreciation_ledger_id
            if not exp_ledger or not acc_ledger:
                raise ValueError(f"Category '{line.asset.category.name}' is missing depreciation ledgers.")
            key = (exp_ledger, acc_ledger)
            aggregated[key] = q2(aggregated.get(key, ZERO) + q2(line.depreciation_amount))

        jl_inputs = []
        for (exp_ledger, acc_ledger), amount in aggregated.items():
            if amount <= ZERO:
                continue
            jl_inputs.append(_jl_for_ledger(ledger_id=exp_ledger, drcr=True, amount=amount, description=f"Depreciation run {run.run_code}"))
            jl_inputs.append(_jl_for_ledger(ledger_id=acc_ledger, drcr=False, amount=amount, description=f"Depreciation run {run.run_code}"))

        posting = PostingService(
            entity_id=run.entity_id,
            entityfin_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            user_id=user_id,
        )
        entry = posting.post(
            txn_type=TxnType.FIXED_ASSET_DEPRECIATION,
            txn_id=run.id,
            voucher_no=run.run_code,
            voucher_date=run.posting_date,
            posting_date=run.posting_date,
            narration=run.note or f"Depreciation run {run.run_code}",
            jl_inputs=jl_inputs,
        )

        for line in lines:
            asset = line.asset
            asset.accumulated_depreciation = q2(asset.accumulated_depreciation) + q2(line.depreciation_amount)
            asset.net_book_value = q2(asset.gross_block) - q2(asset.accumulated_depreciation) - q2(asset.impairment_amount)
            asset.updated_by_id = user_id
            asset.save(update_fields=["accumulated_depreciation", "net_book_value", "updated_by", "updated_at"])

        run.status = DepreciationRun.RunStatus.POSTED
        run.posting_batch = entry.posting_batch
        run.posted_at = timezone.now()
        run.posted_by_id = user_id
        run.updated_by_id = user_id
        run.save(update_fields=["status", "posting_batch", "posted_at", "posted_by", "updated_by", "updated_at"])
        return run

    @staticmethod
    @transaction.atomic
    def impair_asset(
        *,
        asset: FixedAsset,
        impairment_amount: Decimal,
        posting_date: date,
        user_id: int | None = None,
        narration: str | None = None,
    ) -> FixedAsset:
        if asset.status != FixedAsset.AssetStatus.ACTIVE:
            raise ValueError("Only active assets can be impaired.")
        amount = q2(impairment_amount)
        if amount <= ZERO:
            raise ValueError("Impairment amount must be greater than zero.")
        category = asset.category
        if not category.impairment_expense_ledger_id or not category.impairment_reserve_ledger_id:
            raise ValueError("Asset category must define impairment expense and impairment reserve ledgers.")
        if amount > q2(asset.net_book_value):
            raise ValueError("Impairment amount cannot exceed current net book value.")

        posting = PostingService(
            entity_id=asset.entity_id,
            entityfin_id=_resolve_entityfin_id(asset),
            subentity_id=asset.subentity_id,
            user_id=user_id,
        )
        entry = posting.post(
            txn_type=TxnType.FIXED_ASSET_IMPAIRMENT,
            txn_id=(asset.id * 1000000) + int(timezone.now().timestamp()) % 1000000,
            voucher_no=f"{asset.asset_code}-IMP",
            voucher_date=posting_date,
            posting_date=posting_date,
            narration=narration or f"Impairment of asset {asset.asset_code}",
            jl_inputs=[
                _jl_for_ledger(ledger_id=category.impairment_expense_ledger_id, drcr=True, amount=amount, description=asset.asset_name),
                _jl_for_ledger(ledger_id=category.impairment_reserve_ledger_id, drcr=False, amount=amount, description=asset.asset_name),
            ],
        )
        asset.impairment_amount = q2(asset.impairment_amount) + amount
        asset.net_book_value = q2(asset.gross_block) - q2(asset.accumulated_depreciation) - q2(asset.impairment_amount)
        asset.impairment_posting_batch = entry.posting_batch
        asset.updated_by_id = user_id
        asset.save(update_fields=["impairment_amount", "net_book_value", "impairment_posting_batch", "updated_by", "updated_at"])
        return asset

    @staticmethod
    def transfer_asset(
        *,
        asset: FixedAsset,
        subentity_id: int | None = None,
        location_name: str | None = None,
        department_name: str | None = None,
        custodian_name: str | None = None,
        notes: str | None = None,
        user_id: int | None = None,
    ) -> FixedAsset:
        if asset.status not in {FixedAsset.AssetStatus.ACTIVE, FixedAsset.AssetStatus.HELD_FOR_SALE, FixedAsset.AssetStatus.CAPITAL_WIP}:
            raise ValueError("Only active, held-for-sale, or capital-WIP assets can be transferred.")
        asset.subentity_id = subentity_id
        asset.location_name = location_name
        asset.department_name = department_name
        asset.custodian_name = custodian_name
        if notes:
            asset.notes = notes
        asset.updated_by_id = user_id
        asset.save(update_fields=["subentity", "location_name", "department_name", "custodian_name", "notes", "updated_by", "updated_at"])
        return asset

    @staticmethod
    @transaction.atomic
    def dispose_asset(
        *,
        asset: FixedAsset,
        proceeds_ledger_id: int,
        disposal_date: date,
        sale_proceeds: Decimal,
        user_id: int | None = None,
        narration: str | None = None,
    ) -> FixedAsset:
        if asset.status != FixedAsset.AssetStatus.ACTIVE:
            raise ValueError("Only active assets can be disposed.")
        category = asset.category
        asset_ledger_id = asset.ledger_id or category.asset_ledger_id
        if not asset_ledger_id or not category.accumulated_depreciation_ledger_id:
            raise ValueError("Asset and accumulated depreciation ledgers are required for disposal.")
        proceeds = q2(sale_proceeds)
        gross = q2(asset.gross_block)
        acc_dep = q2(asset.accumulated_depreciation)
        impairment = q2(asset.impairment_amount)
        nbv = q2(gross - acc_dep - impairment)
        gain_loss = q2(proceeds - nbv)

        jl_inputs = []
        if acc_dep > ZERO:
            jl_inputs.append(_jl_for_ledger(ledger_id=category.accumulated_depreciation_ledger_id, drcr=True, amount=acc_dep, description=asset.asset_name))
        if impairment > ZERO:
            if not category.impairment_reserve_ledger_id:
                raise ValueError("Impairment reserve ledger is required to dispose an impaired asset.")
            jl_inputs.append(_jl_for_ledger(ledger_id=category.impairment_reserve_ledger_id, drcr=True, amount=impairment, description=asset.asset_name))
        if proceeds > ZERO:
            jl_inputs.append(_jl_for_ledger(ledger_id=proceeds_ledger_id, drcr=True, amount=proceeds, description=asset.asset_name))
        if gain_loss < ZERO:
            if not category.loss_on_sale_ledger_id:
                raise ValueError("Loss on sale ledger is required when disposal creates a loss.")
            jl_inputs.append(_jl_for_ledger(ledger_id=category.loss_on_sale_ledger_id, drcr=True, amount=abs(gain_loss), description=asset.asset_name))
        jl_inputs.append(_jl_for_ledger(ledger_id=asset_ledger_id, drcr=False, amount=gross, description=asset.asset_name))
        if gain_loss > ZERO:
            if not category.gain_on_sale_ledger_id:
                raise ValueError("Gain on sale ledger is required when disposal creates a gain.")
            jl_inputs.append(_jl_for_ledger(ledger_id=category.gain_on_sale_ledger_id, drcr=False, amount=gain_loss, description=asset.asset_name))

        posting = PostingService(
            entity_id=asset.entity_id,
            entityfin_id=_resolve_entityfin_id(asset),
            subentity_id=asset.subentity_id,
            user_id=user_id,
        )
        entry = posting.post(
            txn_type=TxnType.FIXED_ASSET_DISPOSAL,
            txn_id=asset.id,
            voucher_no=f"{asset.asset_code}-DISP",
            voucher_date=disposal_date,
            posting_date=disposal_date,
            narration=narration or f"Disposal of asset {asset.asset_code}",
            jl_inputs=jl_inputs,
        )
        asset.status = FixedAsset.AssetStatus.DISPOSED
        asset.disposal_date = disposal_date
        asset.disposal_posting_batch = entry.posting_batch
        asset.disposal_proceeds = proceeds
        asset.disposal_gain_loss = gain_loss
        asset.net_book_value = ZERO
        asset.updated_by_id = user_id
        asset.save(
            update_fields=[
                "status",
                "disposal_date",
                "disposal_posting_batch",
                "disposal_proceeds",
                "disposal_gain_loss",
                "net_book_value",
                "updated_by",
                "updated_at",
            ]
        )
        return asset
