from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from assets.models import AssetCategory, AssetSettings, DepreciationRun, FixedAsset, default_asset_policy_controls
from assets.services.depreciation import attach_preview_lines, preview_run, q2 as dep_q2
from assets.services.settings import AssetSettingsService
from entity.models import SubEntity
from financial.models import Ledger
from posting.models import Entry, EntryStatus, JournalLine, PostingBatch, TxnType
from posting.services.posting_service import JLInput, PostingService

Q2 = Decimal("0.01")
ZERO = Decimal("0.00")


def q2(value) -> Decimal:
    return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)


def _resolve_entityfin_id(instance, fallback=None):
    return getattr(instance, "entityfinid_id", None) or fallback


def _validate_entity_scope(*, obj, entity_id: int, field_name: str) -> None:
    if obj is None:
        return
    obj_entity_id = getattr(obj, "entity_id", None)
    if obj_entity_id is not None and obj_entity_id != entity_id:
        raise ValueError(f"Selected {field_name} belongs to a different entity.")


def _validate_asset_scope(*, entity_id: int, subentity=None, entityfinid=None, category=None, ledger=None, vendor_account=None) -> None:
    _validate_entity_scope(obj=subentity, entity_id=entity_id, field_name="subentity")
    _validate_entity_scope(obj=entityfinid, entity_id=entity_id, field_name="entityfinid")
    _validate_entity_scope(obj=category, entity_id=entity_id, field_name="category")
    _validate_entity_scope(obj=ledger, entity_id=entity_id, field_name="ledger")
    _validate_entity_scope(obj=vendor_account, entity_id=entity_id, field_name="vendor_account")
    if category is not None and getattr(category, "subentity_id", None) is not None:
        category_subentity_id = getattr(category, "subentity_id", None)
        subentity_id = getattr(subentity, "id", None)
        if subentity_id is None:
            raise ValueError("Selected category belongs to a subentity and requires the same subentity on the asset.")
        if category_subentity_id != subentity_id:
            raise ValueError("Selected category belongs to a different subentity.")


def _asset_settings_and_controls(*, entity_id: int, subentity_id: int | None = None) -> tuple[AssetSettings, dict]:
    settings = AssetSettingsService.get_settings(entity_id, subentity_id)
    controls = default_asset_policy_controls()
    controls.update(settings.policy_controls or {})
    return settings, controls


def _policy_block(rule: str, message: str) -> None:
    if rule in {"hard", "block"}:
        raise ValueError(message)


def _ensure_non_negative_nbv(*, asset: FixedAsset, rule: str) -> None:
    if q2(asset.gross_block) - q2(asset.accumulated_depreciation) - q2(asset.impairment_amount) < ZERO:
        _policy_block(rule, "Asset net book value cannot be negative.")


def _ensure_tag_for_posting(*, asset: FixedAsset, settings: AssetSettings, controls: dict) -> None:
    if asset.asset_tag:
        return
    if settings.require_asset_tag or controls.get("allow_posting_without_tag") == "off":
        raise ValueError("Asset tag is required before posting this asset.")


def _ensure_locked_period(*, entityfinid, posting_date: date, rule: str) -> None:
    if entityfinid and entityfinid.books_locked_until and posting_date <= entityfinid.books_locked_until:
        _policy_block(rule, "The selected posting date falls inside a locked books period.")


def _ensure_backdated_capitalization(*, asset: FixedAsset, capitalization_date: date, rule: str) -> None:
    if capitalization_date < asset.acquisition_date:
        _policy_block(rule, "Capitalization date cannot be earlier than the acquisition date.")


def _ensure_backdated_disposal(*, asset: FixedAsset, disposal_date: date, rule: str) -> None:
    baseline_date = asset.capitalization_date or asset.acquisition_date
    if disposal_date < baseline_date:
        _policy_block(rule, "Disposal date cannot be earlier than the asset capitalization date.")


def _ensure_capitalization_threshold(*, asset: FixedAsset, settings: AssetSettings, controls: dict) -> None:
    threshold = q2(asset.category.capitalization_threshold or settings.capitalization_threshold)
    if threshold <= ZERO:
        return
    amount = q2(asset.gross_block)
    if amount < threshold:
        _policy_block(
            controls.get("capitalization_threshold_rule", "warn"),
            f"Asset gross block {amount} is below the capitalization threshold {threshold}.",
        )


def _jl_for_ledger(*, entity_id: int, ledger_id: int, drcr: bool, amount: Decimal, description: str) -> JLInput:
    ledger = Ledger.objects.filter(id=ledger_id, entity_id=entity_id).only("id", "accounthead_id", "entity_id").first()
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
        qs = FixedAsset.objects.select_related("category", "ledger", "vendor_account", "subentity").filter(entity_id=entity_id, is_active=True)
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
    @transaction.atomic
    def archive_category(*, category: AssetCategory, user_id: int | None = None) -> AssetCategory | None:
        if FixedAsset.objects.filter(category=category).exists():
            if category.is_active:
                category.is_active = False
                category.updated_by_id = user_id
                category.save(update_fields=["is_active", "updated_by", "updated_at"])
            return category

        category.delete()
        return None

    @staticmethod
    @transaction.atomic
    def archive_asset(*, asset: FixedAsset, user_id: int | None = None) -> FixedAsset | None:
        has_posting = bool(asset.capitalization_posting_batch_id or asset.impairment_posting_batch_id or asset.disposal_posting_batch_id)
        has_dep_lines = asset.depreciation_lines.exists()

        if has_posting or has_dep_lines:
            if asset.is_active:
                asset.is_active = False
                asset.updated_by_id = user_id
                asset.save(update_fields=["is_active", "updated_by", "updated_at"])
            return asset

        asset.delete()
        return None

    @staticmethod
    def create_asset(*, data: dict, user_id: int | None = None) -> FixedAsset:
        entity = data["entity"]
        entity_id = entity.id
        subentity = data.get("subentity")
        entityfinid = data.get("entityfinid")
        category = data["category"]
        ledger = data.get("ledger")
        vendor_account = data.get("vendor_account")
        _validate_asset_scope(
            entity_id=entity_id,
            subentity=subentity,
            entityfinid=entityfinid,
            category=category,
            ledger=ledger,
            vendor_account=vendor_account,
        )
        subentity_id = subentity.id if subentity else None
        settings = AssetSettingsService.get_settings(entity_id, subentity_id)
        payload = dict(data)
        if not payload.get("asset_code") and settings.auto_number_assets:
            payload["asset_code"] = AssetService.generate_asset_code(entity_id=entity_id, settings=settings)

        payload.setdefault("useful_life_months", category.useful_life_months or settings.default_useful_life_months)
        payload.setdefault("depreciation_method", category.depreciation_method or settings.default_depreciation_method)
        if payload.get("residual_value") in (None, ""):
            residual_percent = q2(category.residual_value_percent or settings.default_residual_value_percent)
            payload["residual_value"] = q2(q2(payload.get("gross_block")) * residual_percent / Decimal("100.00"))
        payload.setdefault("net_book_value", q2(payload.get("gross_block")))
        asset = FixedAsset.objects.create(created_by_id=user_id, updated_by_id=user_id, **payload)
        _ensure_non_negative_nbv(asset=asset, rule=(AssetSettingsService.resolve_policy_controls(settings).get("negative_nbv_rule") or "block"))
        return asset

    @staticmethod
    def update_asset(*, instance: FixedAsset, data: dict, user_id: int | None = None) -> FixedAsset:
        immutable_if_posted = {"entity", "entityfinid", "subentity", "category", "gross_block"}
        for key, value in data.items():
            if instance.capitalization_posting_batch_id and key in immutable_if_posted:
                continue
            setattr(instance, key, value)
        _validate_asset_scope(
            entity_id=instance.entity_id,
            subentity=instance.subentity,
            entityfinid=instance.entityfinid,
            category=instance.category,
            ledger=instance.ledger,
            vendor_account=instance.vendor_account,
        )
        _, controls = _asset_settings_and_controls(entity_id=instance.entity_id, subentity_id=instance.subentity_id)
        instance.updated_by_id = user_id
        instance.net_book_value = q2(instance.gross_block) - q2(instance.accumulated_depreciation) - q2(instance.impairment_amount)
        _ensure_non_negative_nbv(asset=instance, rule=controls.get("negative_nbv_rule", "block"))
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
        settings, controls = _asset_settings_and_controls(entity_id=asset.entity_id, subentity_id=asset.subentity_id)
        asset_ledger_id = asset.ledger_id or asset.category.asset_ledger_id
        if not asset_ledger_id:
            raise ValueError("Asset ledger is required on asset or asset category before capitalization.")
        if not counter_ledger_id:
            raise ValueError("Counter ledger is required for capitalization.")
        amount = q2(asset.gross_block)
        if amount <= ZERO:
            raise ValueError("Asset gross block must be greater than zero for capitalization.")
        _ensure_capitalization_threshold(asset=asset, settings=settings, controls=controls)
        _ensure_tag_for_posting(asset=asset, settings=settings, controls=controls)
        _ensure_backdated_capitalization(asset=asset, capitalization_date=capitalization_date, rule=controls.get("backdated_capitalization_rule", "warn"))
        _ensure_locked_period(entityfinid=asset.entityfinid, posting_date=capitalization_date, rule=controls.get("depreciation_lock_rule", "hard"))

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
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=asset_ledger_id, drcr=True, amount=amount, description=asset.asset_name),
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=counter_ledger_id, drcr=False, amount=amount, description=asset.asset_name),
            ],
        )
        asset.status = FixedAsset.AssetStatus.ACTIVE
        asset.capitalization_date = capitalization_date
        asset.put_to_use_date = asset.put_to_use_date or capitalization_date
        asset.depreciation_start_date = asset.depreciation_start_date or capitalization_date
        asset.capitalization_posting_batch = entry.posting_batch
        asset.net_book_value = q2(asset.gross_block) - q2(asset.accumulated_depreciation) - q2(asset.impairment_amount)
        asset.updated_by_id = user_id
        _ensure_non_negative_nbv(asset=asset, rule=controls.get("negative_nbv_rule", "block"))
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
        _, controls = _asset_settings_and_controls(entity_id=run.entity_id, subentity_id=run.subentity_id)
        _ensure_locked_period(entityfinid=run.entityfinid, posting_date=run.period_to, rule=controls.get("depreciation_lock_rule", "hard"))
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
        _, controls = _asset_settings_and_controls(entity_id=run.entity_id, subentity_id=run.subentity_id)
        _ensure_locked_period(entityfinid=run.entityfinid, posting_date=run.posting_date, rule=controls.get("depreciation_lock_rule", "hard"))
        if run.status != DepreciationRun.RunStatus.CALCULATED:
            raise ValueError("Depreciation run must be in calculated state before posting.")
        lines = list(run.lines.select_related("asset", "asset__category"))
        if not lines:
            raise ValueError("Depreciation run has no lines to post.")
        for line in lines:
            _ensure_tag_for_posting(asset=line.asset, settings=AssetSettingsService.get_settings(line.asset.entity_id, line.asset.subentity_id), controls=AssetSettingsService.resolve_policy_controls(AssetSettingsService.get_settings(line.asset.entity_id, line.asset.subentity_id)))

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
            jl_inputs.append(_jl_for_ledger(entity_id=run.entity_id, ledger_id=exp_ledger, drcr=True, amount=amount, description=f"Depreciation run {run.run_code}"))
            jl_inputs.append(_jl_for_ledger(entity_id=run.entity_id, ledger_id=acc_ledger, drcr=False, amount=amount, description=f"Depreciation run {run.run_code}"))

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
            _ensure_non_negative_nbv(asset=asset, rule=controls.get("negative_nbv_rule", "block"))
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
    def cancel_run(*, run: DepreciationRun, user_id: int | None = None) -> DepreciationRun:
        _, controls = _asset_settings_and_controls(entity_id=run.entity_id, subentity_id=run.subentity_id)
        _ensure_locked_period(entityfinid=run.entityfinid, posting_date=run.posting_date, rule=controls.get("depreciation_lock_rule", "hard"))

        if run.status not in {DepreciationRun.RunStatus.CALCULATED, DepreciationRun.RunStatus.POSTED}:
            raise ValueError("Depreciation run must be calculated or posted before it can be cancelled.")

        if run.status == DepreciationRun.RunStatus.POSTED:
            lines = list(run.lines.select_related("asset", "asset__category"))
            if not lines:
                raise ValueError("Posted depreciation run has no lines to reverse.")

            for line in lines:
                asset = line.asset
                asset.accumulated_depreciation = q2(asset.accumulated_depreciation) - q2(line.depreciation_amount)
                if asset.accumulated_depreciation < ZERO:
                    raise ValueError(f"Cannot reverse depreciation for asset {asset.asset_code}; accumulated depreciation would become negative.")
                asset.net_book_value = q2(asset.gross_block) - q2(asset.accumulated_depreciation) - q2(asset.impairment_amount)
                _ensure_non_negative_nbv(asset=asset, rule=controls.get("negative_nbv_rule", "block"))
                asset.updated_by_id = user_id
                asset.save(update_fields=["accumulated_depreciation", "net_book_value", "updated_by", "updated_at"])

            if run.posting_batch_id:
                run.posting_batch.is_active = False
                run.posting_batch.save(update_fields=["is_active"])
                JournalLine.objects.filter(posting_batch=run.posting_batch).delete()

            entry = Entry.objects.filter(
                entity_id=run.entity_id,
                entityfin_id=run.entityfinid_id,
                subentity_id=run.subentity_id,
                txn_type=TxnType.FIXED_ASSET_DEPRECIATION,
                txn_id=run.id,
            ).first()
            if entry:
                entry.status = EntryStatus.REVERSED
                entry.posting_batch = None
                entry.posted_at = None
                entry.posted_by = None
                entry.save(update_fields=["status", "posting_batch", "posted_at", "posted_by"])
            run.posting_batch_id = None
        elif run.posting_batch_id:
            run.posting_batch.is_active = False
            run.posting_batch.save(update_fields=["is_active"])

        run.status = DepreciationRun.RunStatus.CANCELLED
        run.total_assets = 0
        run.total_amount = ZERO
        run.calculated_at = None
        run.posted_at = None
        run.posted_by_id = None
        run.updated_by_id = user_id
        run.save(
            update_fields=[
                "status",
                "total_assets",
                "total_amount",
                "calculated_at",
                "posted_at",
                "posted_by",
                "posting_batch",
                "updated_by",
                "updated_at",
            ]
        )
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
        _, controls = _asset_settings_and_controls(entity_id=asset.entity_id, subentity_id=asset.subentity_id)

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
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.impairment_expense_ledger_id, drcr=True, amount=amount, description=asset.asset_name),
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.impairment_reserve_ledger_id, drcr=False, amount=amount, description=asset.asset_name),
            ],
        )
        asset.impairment_amount = q2(asset.impairment_amount) + amount
        asset.net_book_value = q2(asset.gross_block) - q2(asset.accumulated_depreciation) - q2(asset.impairment_amount)
        asset.impairment_posting_batch = entry.posting_batch
        asset.updated_by_id = user_id
        _ensure_non_negative_nbv(asset=asset, rule=controls.get("negative_nbv_rule", "block"))
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
        if subentity_id is not None:
            subentity = SubEntity.objects.filter(id=subentity_id, entity_id=asset.entity_id, isactive=True).only("id", "entity_id").first()
            if subentity is None:
                raise ValueError("Selected subentity belongs to a different entity or is inactive.")
            asset.subentity_id = subentity.id
        else:
            asset.subentity_id = None
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
        settings, controls = _asset_settings_and_controls(entity_id=asset.entity_id, subentity_id=asset.subentity_id)
        asset_ledger_id = asset.ledger_id or category.asset_ledger_id
        if not asset_ledger_id or not category.accumulated_depreciation_ledger_id:
            raise ValueError("Asset and accumulated depreciation ledgers are required for disposal.")
        _validate_asset_scope(
            entity_id=asset.entity_id,
            category=category,
            ledger=asset.ledger or category.asset_ledger,
        )
        _ensure_backdated_disposal(asset=asset, disposal_date=disposal_date, rule=controls.get("backdated_disposal_rule", "hard"))
        proceeds = q2(sale_proceeds)
        gross = q2(asset.gross_block)
        acc_dep = q2(asset.accumulated_depreciation)
        impairment = q2(asset.impairment_amount)
        nbv = q2(gross - acc_dep - impairment)
        gain_loss = q2(proceeds - nbv)
        if nbv < ZERO:
            _policy_block(controls.get("negative_nbv_rule", "block"), "Asset net book value cannot be negative before disposal.")

        jl_inputs = []
        if acc_dep > ZERO:
            jl_inputs.append(_jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.accumulated_depreciation_ledger_id, drcr=True, amount=acc_dep, description=asset.asset_name))
        if impairment > ZERO:
            if not category.impairment_reserve_ledger_id:
                raise ValueError("Impairment reserve ledger is required to dispose an impaired asset.")
            jl_inputs.append(_jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.impairment_reserve_ledger_id, drcr=True, amount=impairment, description=asset.asset_name))
        if proceeds > ZERO:
            jl_inputs.append(_jl_for_ledger(entity_id=asset.entity_id, ledger_id=proceeds_ledger_id, drcr=True, amount=proceeds, description=asset.asset_name))
        if gain_loss < ZERO:
            if not category.loss_on_sale_ledger_id:
                raise ValueError("Loss on sale ledger is required when disposal creates a loss.")
            jl_inputs.append(_jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.loss_on_sale_ledger_id, drcr=True, amount=abs(gain_loss), description=asset.asset_name))
        jl_inputs.append(_jl_for_ledger(entity_id=asset.entity_id, ledger_id=asset_ledger_id, drcr=False, amount=gross, description=asset.asset_name))
        if gain_loss > ZERO:
            if not category.gain_on_sale_ledger_id:
                raise ValueError("Gain on sale ledger is required when disposal creates a gain.")
            jl_inputs.append(_jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.gain_on_sale_ledger_id, drcr=False, amount=gain_loss, description=asset.asset_name))

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
