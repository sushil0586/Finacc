from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from assets.models import AssetCategory, AssetSettings, DepreciationRun, DepreciationRunLine, FixedAsset, default_asset_policy_controls
from assets.services.depreciation import attach_preview_lines, preview_run, q2 as dep_q2
from assets.services.settings import AssetSettingsService
from entity.models import SubEntity
from entity.models import Entity
from financial.models import Ledger
from posting.models import Entry, EntryStatus, JournalLine, PostingBatch, TxnType
from posting.services.posting_service import JLInput, PostingService

Q2 = Decimal("0.01")
ZERO = Decimal("0.00")
SYSTEM_MANAGED_WRITE_FIELDS = {
    "accumulated_depreciation",
    "impairment_amount",
    "net_book_value",
    "capitalization_posting_batch",
    "capitalization_posting_batch_id",
    "impairment_posting_batch",
    "impairment_posting_batch_id",
    "disposal_posting_batch",
    "disposal_posting_batch_id",
    "disposal_proceeds",
    "disposal_gain_loss",
}
MANUALLY_SETTABLE_STATUSES = {
    FixedAsset.AssetStatus.DRAFT,
    FixedAsset.AssetStatus.CAPITAL_WIP,
    FixedAsset.AssetStatus.HELD_FOR_SALE,
}


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


def _append_note(existing: str | None, line: str) -> str:
    existing_text = (existing or "").strip()
    combined = f"{existing_text}\n{line}".strip() if existing_text else line.strip()
    max_length = FixedAsset._meta.get_field("notes").max_length or 500
    if len(combined) <= max_length:
        return combined
    return combined[-max_length:]


def _purchase_intake_review_missing(
    *,
    asset: FixedAsset,
    location_name: str | None = None,
    custodian_name: str | None = None,
) -> list[str]:
    if not (getattr(asset, "purchase_document_no", None) or asset.source_purchase_lines.exists()):
        return []

    effective_location = asset.location_name if location_name is None else location_name
    effective_custodian = asset.custodian_name if custodian_name is None else custodian_name
    missing: list[str] = []
    if not asset.category_id:
        missing.append("asset category")
    if not (asset.ledger_id or getattr(asset.category, "asset_ledger_id", None)):
        missing.append("asset ledger")
    if not (asset.asset_name or "").strip():
        missing.append("asset name")
    if not asset.acquisition_date:
        missing.append("acquisition date")
    if not asset.useful_life_months or int(asset.useful_life_months) <= 0:
        missing.append("useful life")
    if not (asset.depreciation_method or "").strip():
        missing.append("depreciation method")
    if not (effective_location or "").strip():
        missing.append("location")
    if not (effective_custodian or "").strip():
        missing.append("custodian")
    return missing


def _entry_for_asset_txn(*, asset: FixedAsset, txn_type: str):
    return Entry.objects.filter(
        entity_id=asset.entity_id,
        entityfin_id=_resolve_entityfin_id(asset),
        subentity_id=asset.subentity_id,
        txn_type=txn_type,
        txn_id=asset.id,
    ).select_related("posting_batch").first()


def _entry_for_posting_batch(posting_batch: PostingBatch | None):
    if posting_batch is None:
        return None
    return Entry.objects.filter(posting_batch=posting_batch).select_related("posting_batch").first()


def _reverse_entry_and_batch(*, entry: Entry | None, posting_batch: PostingBatch | None, reason: str) -> None:
    if posting_batch:
        posting_batch.is_active = False
        posting_batch.note = _append_note(posting_batch.note, f"Reversed: {reason}")
        posting_batch.save(update_fields=["is_active", "note"])
    if entry:
        entry.status = EntryStatus.REVERSED
        entry.posted_at = None
        entry.posted_by = None
        entry.narration = _append_note(entry.narration, f"Reversed: {reason}")
        entry.save(update_fields=["status", "posted_at", "posted_by", "narration"])


def _locked_period_message(*, entityfinid, posting_date: date | None) -> str | None:
    if not entityfinid or not posting_date:
        return None
    if entityfinid.books_locked_until and posting_date <= entityfinid.books_locked_until:
        return "The original posting date falls inside a locked books period and cannot be reversed in this scope."
    return None


def _append_policy_issue(*, rule: str, message: str, blocking_reasons: list[str], warnings: list[str]) -> None:
    if rule in {"hard", "block"}:
        blocking_reasons.append(message)
    elif rule == "warn":
        warnings.append(message)


def _precheck_payload(
    *,
    action: str,
    asset: FixedAsset,
    posting_date: date | None,
    posting_batch_id: int | None,
    allowed: bool,
    blocking_reasons: list[str],
    warnings: list[str],
    impact: list[str],
    policy_profile: dict | None = None,
) -> dict:
    return {
        "action": action,
        "allowed": allowed,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "impact": impact,
        "policy_profile": policy_profile or {},
        "snapshot": {
            "asset_code": asset.asset_code,
            "status": asset.status,
            "posting_batch_id": posting_batch_id,
            "posting_date": posting_date.isoformat() if posting_date else None,
            "gross_block": str(q2(asset.gross_block)),
            "accumulated_depreciation": str(q2(asset.accumulated_depreciation)),
            "impairment_amount": str(q2(asset.impairment_amount)),
            "net_book_value": str(q2(asset.net_book_value)),
        },
    }


def _category_accounting_policy_profile(*, asset: FixedAsset, settings: AssetSettings | None) -> dict:
    category_controls = getattr(asset.category, "accounting_controls", {}) or {}
    resolved_controls = AssetSettingsService.resolve_category_accounting_controls(asset.category, settings)
    labels = {
        "asset_ledger_rule": "Asset Ledger",
        "depreciation_ledgers_rule": "Depreciation Ledgers",
        "impairment_ledgers_rule": "Impairment Ledgers",
        "disposal_ledgers_rule": "Disposal Ledgers",
        "cwip_ledger_rule": "CWIP Ledger",
    }
    items = []
    for key, label in labels.items():
        configured_value = category_controls.get(key, "inherit")
        items.append(
            {
                "code": key,
                "label": label,
                "effective_rule": resolved_controls.get(key, "off"),
                "source": "category" if configured_value not in (None, "", "inherit") else "scope",
                "configured_value": configured_value or "inherit",
            }
        )
    return {
        "category_name": getattr(asset.category, "name", None),
        "items": items,
    }


def _ensure_purchase_intake_ready_for_capitalization(*, asset: FixedAsset) -> None:
    missing = _purchase_intake_review_missing(asset=asset)
    if missing:
        raise ValueError(
            "Purchase intake asset review is incomplete. Complete these fields before capitalization: "
            + ", ".join(missing)
            + "."
        )


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


def _ensure_manual_asset_payload_allowed(*, data: dict, instance: FixedAsset | None = None) -> None:
    prohibited_fields = sorted(field for field in SYSTEM_MANAGED_WRITE_FIELDS if field in data)
    if prohibited_fields:
        raise ValueError(f"These asset fields are system managed and cannot be set directly: {', '.join(prohibited_fields)}.")

    status_value = data.get("status")
    if status_value is not None and status_value not in MANUALLY_SETTABLE_STATUSES:
        raise ValueError("Asset status can only be set manually to Draft, Capital WIP, or Held for Sale.")

    if instance and instance.capitalization_posting_batch_id and "status" in data and data["status"] != instance.status:
        raise ValueError("Asset status cannot be edited directly after capitalization.")


def _asset_snapshot(asset: FixedAsset, *, posting_batch_id: int | None = None, posting_date: date | None = None) -> dict:
    return {
        "asset_code": asset.asset_code,
        "status": asset.status,
        "posting_batch_id": posting_batch_id,
        "posting_date": posting_date.isoformat() if posting_date else None,
        "gross_block": f"{q2(asset.gross_block):.2f}",
        "accumulated_depreciation": f"{q2(asset.accumulated_depreciation):.2f}",
        "impairment_amount": f"{q2(asset.impairment_amount):.2f}",
        "net_book_value": f"{q2(asset.net_book_value):.2f}",
    }


def _build_policy_profile(*, asset: FixedAsset, settings: AssetSettings) -> dict:
    scope_controls = AssetSettingsService.resolve_policy_controls(settings)
    category_controls = asset.category.accounting_controls or {}

    def _item(code: str, label: str, category_key: str) -> dict:
        category_value = category_controls.get(category_key)
        if category_value not in (None, "", "inherit"):
            return {
                "code": code,
                "label": label,
                "effective_rule": category_value,
                "source": "category",
                "configured_value": category_value,
            }
        return {
            "code": code,
            "label": label,
            "effective_rule": scope_controls.get(code, "off"),
            "source": "scope",
            "configured_value": category_value or "inherit",
        }

    return {
        "category_name": asset.category.name,
        "items": [
            _item("require_asset_ledger_rule", "Asset ledger mapping", "asset_ledger_rule"),
            _item("require_depreciation_ledgers_rule", "Depreciation ledger mapping", "depreciation_ledgers_rule"),
            _item("require_impairment_ledgers_rule", "Impairment ledger mapping", "impairment_ledgers_rule"),
            _item("require_disposal_ledgers_rule", "Disposal ledger mapping", "disposal_ledgers_rule"),
            _item("require_cwip_ledger_rule", "CWIP ledger mapping", "cwip_ledger_rule"),
        ],
    }


def _overlapping_active_runs(*, run: DepreciationRun):
    qs = DepreciationRun.objects.filter(
        entity_id=run.entity_id,
        entityfinid_id=run.entityfinid_id,
        status__in=[
            DepreciationRun.RunStatus.DRAFT,
            DepreciationRun.RunStatus.CALCULATED,
            DepreciationRun.RunStatus.POSTED,
        ],
        period_from__lte=run.period_to,
        period_to__gte=run.period_from,
    ).exclude(pk=run.pk)
    if run.subentity_id is None:
        return qs
    return qs.filter(Q(subentity_id__isnull=True) | Q(subentity_id=run.subentity_id))


def _ensure_no_overlapping_depreciation_run(*, run: DepreciationRun) -> None:
    if _overlapping_active_runs(run=run).exists():
        raise ValueError("An overlapping depreciation run already exists in this scope. Cancel or move the existing run before continuing.")


def _immutable_posted_asset_field_changes(*, instance: FixedAsset, data: dict) -> list[str]:
    if not instance.capitalization_posting_batch_id:
        return []

    changed_fields: list[str] = []
    field_accessors = {
        "entity": lambda obj: getattr(obj, "entity_id", None),
        "entityfinid": lambda obj: getattr(obj, "entityfinid_id", None),
        "subentity": lambda obj: getattr(obj, "subentity_id", None),
        "category": lambda obj: getattr(obj, "category_id", None),
        "gross_block": lambda obj: q2(getattr(obj, "gross_block", ZERO)),
    }
    immutable_fields = tuple(field_accessors.keys())

    for field_name in immutable_fields:
        if field_name not in data:
            continue
        incoming = data[field_name]
        current = field_accessors[field_name](instance)
        if field_name == "gross_block":
            incoming_value = q2(incoming)
        else:
            incoming_value = getattr(incoming, "id", incoming)
        if incoming_value != current:
            changed_fields.append(field_name)

    return changed_fields


class AssetService:
    @staticmethod
    def _is_asset_code_collision(error: Exception) -> bool:
        return "uq_fixed_asset_entity_code" in str(error)

    @staticmethod
    def generate_asset_code(*, entity_id: int, settings: AssetSettings) -> str:
        prefix = settings.default_doc_code_asset or "FA"
        prefix_token = f"{prefix}-"
        max_seq = 0
        existing_codes = FixedAsset.objects.filter(
            entity_id=entity_id,
            asset_code__startswith=prefix_token,
        ).values_list("asset_code", flat=True)

        for code in existing_codes.iterator():
            suffix = str(code or "")[len(prefix_token):].strip()
            if not suffix.isdigit():
                continue
            max_seq = max(max_seq, int(suffix))

        seq = max_seq + 1
        candidate = f"{prefix}-{seq:06d}"
        while FixedAsset.objects.filter(entity_id=entity_id, asset_code=candidate).exists():
            seq += 1
            candidate = f"{prefix}-{seq:06d}"
        return candidate

    @staticmethod
    def asset_queryset(*, entity_id: int, subentity_id: int | None = None, search: str | None = None):
        qs = (
            FixedAsset.objects
            .select_related("category", "ledger", "vendor_account", "subentity")
            .prefetch_related("source_purchase_lines__header")
            .filter(entity_id=entity_id, is_active=True)
        )
        if subentity_id is not None:
            qs = qs.filter(subentity_id=subentity_id)
        if search:
            qs = qs.filter(
                Q(asset_code__icontains=search)
                | Q(asset_name__icontains=search)
                | Q(asset_tag__icontains=search)
                | Q(serial_number__icontains=search)
                | Q(purchase_document_no__icontains=search)
                | Q(vendor_account__accountname__icontains=search)
                | Q(location_name__icontains=search)
                | Q(custodian_name__icontains=search)
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
    @transaction.atomic
    def create_asset(*, data: dict, user_id: int | None = None) -> FixedAsset:
        _ensure_manual_asset_payload_allowed(data=data)
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
        Entity.objects.select_for_update().filter(pk=entity_id).exists()
        payload = dict(data)
        auto_generated_code = not payload.get("asset_code") and settings.auto_number_assets
        if auto_generated_code:
            payload["asset_code"] = AssetService.generate_asset_code(entity_id=entity_id, settings=settings)

        payload.setdefault("useful_life_months", category.useful_life_months or settings.default_useful_life_months)
        payload.setdefault("depreciation_method", category.depreciation_method or settings.default_depreciation_method)
        if payload.get("residual_value") in (None, ""):
            residual_percent = q2(category.residual_value_percent or settings.default_residual_value_percent)
            payload["residual_value"] = q2(q2(payload.get("gross_block")) * residual_percent / Decimal("100.00"))
        payload.setdefault("net_book_value", q2(payload.get("gross_block")))
        asset = None
        for _ in range(5):
            try:
                with transaction.atomic():
                    asset = FixedAsset.objects.create(created_by_id=user_id, updated_by_id=user_id, **payload)
                break
            except IntegrityError as exc:
                if not auto_generated_code or not AssetService._is_asset_code_collision(exc):
                    raise
                payload["asset_code"] = AssetService.generate_asset_code(entity_id=entity_id, settings=settings)
        if asset is None:
            raise ValueError("Unable to generate a unique asset code for this entity. Please retry.")
        _ensure_non_negative_nbv(asset=asset, rule=(AssetSettingsService.resolve_policy_controls(settings).get("negative_nbv_rule") or "block"))
        return asset

    @staticmethod
    def update_asset(*, instance: FixedAsset, data: dict, user_id: int | None = None) -> FixedAsset:
        _ensure_manual_asset_payload_allowed(data=data, instance=instance)
        immutable_changes = _immutable_posted_asset_field_changes(instance=instance, data=data)
        if immutable_changes:
            raise ValueError(
                "Posted asset fields cannot be edited directly after capitalization: "
                + ", ".join(sorted(immutable_changes))
                + ". Reverse capitalization first if accounting data must change."
            )
        for key, value in data.items():
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
    def capitalize_asset_precheck(
        *,
        asset: FixedAsset,
        counter_ledger_id: int,
        capitalization_date: date,
        location_name: str | None = None,
        department_name: str | None = None,
        custodian_name: str | None = None,
        notes: str | None = None,
        narration: str | None = None,
    ) -> dict:
        del notes, narration
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        impact = [
            "Capitalization will create a posting batch and move the asset to Active status.",
            "Capitalization date, put-to-use date, and depreciation start date will be set on the asset record.",
            "Net book value will be recalculated and the asset will become eligible for depreciation runs.",
        ]

        if asset.status in {FixedAsset.AssetStatus.ACTIVE, FixedAsset.AssetStatus.DISPOSED, FixedAsset.AssetStatus.SCRAPPED}:
            blocking_reasons.append("Only draft or capital-WIP assets can be capitalized.")
        if asset.capitalization_posting_batch_id:
            blocking_reasons.append("This asset is already capitalized.")

        settings, controls = _asset_settings_and_controls(entity_id=asset.entity_id, subentity_id=asset.subentity_id)
        asset_ledger_id = asset.ledger_id or asset.category.asset_ledger_id
        if not asset_ledger_id:
            blocking_reasons.append("Asset ledger is required on asset or asset category before capitalization.")
        elif not blocking_reasons:
            try:
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=asset_ledger_id, drcr=True, amount=q2(asset.gross_block), description=asset.asset_name)
            except ValueError as exc:
                blocking_reasons.append(str(exc))

        if not counter_ledger_id:
            blocking_reasons.append("Counter ledger is required for capitalization.")
        else:
            try:
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=counter_ledger_id, drcr=False, amount=q2(asset.gross_block), description=asset.asset_name)
            except ValueError as exc:
                blocking_reasons.append(str(exc))

        amount = q2(asset.gross_block)
        if amount <= ZERO:
            blocking_reasons.append("Asset gross block must be greater than zero for capitalization.")

        missing = _purchase_intake_review_missing(
            asset=asset,
            location_name=location_name,
            custodian_name=custodian_name,
        )
        if missing:
            _append_policy_issue(
                rule=controls.get("purchase_review_completeness_rule", "hard"),
                message=(
                    "Purchase intake asset review is incomplete. Complete these fields before capitalization: "
                    + ", ".join(missing)
                    + "."
                ),
                blocking_reasons=blocking_reasons,
                warnings=warnings,
            )

        threshold = q2(asset.category.capitalization_threshold or settings.capitalization_threshold)
        if threshold > ZERO and amount < threshold:
            _append_policy_issue(
                rule=controls.get("capitalization_threshold_rule", "warn"),
                message=f"Asset gross block {amount} is below the capitalization threshold {threshold}.",
                blocking_reasons=blocking_reasons,
                warnings=warnings,
            )
        if not asset.asset_tag and (settings.require_asset_tag or controls.get("allow_posting_without_tag") == "off"):
            blocking_reasons.append("Asset tag is required before posting this asset.")
        if asset.acquisition_date and capitalization_date < asset.acquisition_date:
            _append_policy_issue(
                rule=controls.get("backdated_capitalization_rule", "warn"),
                message="Capitalization date cannot be earlier than the acquisition date.",
                blocking_reasons=blocking_reasons,
                warnings=warnings,
            )
        locked_message = _locked_period_message(entityfinid=asset.entityfinid, posting_date=capitalization_date)
        if locked_message:
            blocking_reasons.append(locked_message)
        if counter_ledger_id and asset_ledger_id and counter_ledger_id == asset_ledger_id:
            _append_policy_issue(
                rule=controls.get("counter_ledger_match_rule", "warn"),
                message="Counter ledger matches the asset ledger. Review this carefully before posting.",
                blocking_reasons=blocking_reasons,
                warnings=warnings,
            )
        if department_name and not str(department_name).strip():
            warnings.append("Department value is blank and will not improve downstream reporting.")

        return _precheck_payload(
            action="capitalize",
            asset=asset,
            posting_date=capitalization_date,
            posting_batch_id=None,
            allowed=not blocking_reasons,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            impact=impact,
            policy_profile=_category_accounting_policy_profile(asset=asset, settings=settings),
        )

    @staticmethod
    @transaction.atomic
    def capitalize_asset(
        *,
        asset: FixedAsset,
        counter_ledger_id: int,
        capitalization_date: date,
        user_id: int | None = None,
        narration: str | None = None,
        location_name: str | None = None,
        department_name: str | None = None,
        custodian_name: str | None = None,
        notes: str | None = None,
    ) -> FixedAsset:
        if asset.status in {FixedAsset.AssetStatus.ACTIVE, FixedAsset.AssetStatus.DISPOSED, FixedAsset.AssetStatus.SCRAPPED}:
            raise ValueError("Only draft or capital-WIP assets can be capitalized.")
        if asset.capitalization_posting_batch_id:
            raise ValueError("This asset is already capitalized.")
        if location_name is not None:
            asset.location_name = location_name
        if department_name is not None:
            asset.department_name = department_name
        if custodian_name is not None:
            asset.custodian_name = custodian_name
        if notes is not None:
            asset.notes = notes
        settings, controls = _asset_settings_and_controls(entity_id=asset.entity_id, subentity_id=asset.subentity_id)
        asset_ledger_id = asset.ledger_id or asset.category.asset_ledger_id
        if not asset_ledger_id:
            raise ValueError("Asset ledger is required on asset or asset category before capitalization.")
        if not counter_ledger_id:
            raise ValueError("Counter ledger is required for capitalization.")
        amount = q2(asset.gross_block)
        if amount <= ZERO:
            raise ValueError("Asset gross block must be greater than zero for capitalization.")
        missing_purchase_review_fields = _purchase_intake_review_missing(asset=asset)
        if missing_purchase_review_fields:
            _policy_block(
                controls.get("purchase_review_completeness_rule", "hard"),
                "Purchase intake asset review is incomplete. Complete these fields before capitalization: "
                + ", ".join(missing_purchase_review_fields)
                + ".",
            )
        _ensure_capitalization_threshold(asset=asset, settings=settings, controls=controls)
        _ensure_tag_for_posting(asset=asset, settings=settings, controls=controls)
        _ensure_backdated_capitalization(asset=asset, capitalization_date=capitalization_date, rule=controls.get("backdated_capitalization_rule", "warn"))
        _ensure_locked_period(entityfinid=asset.entityfinid, posting_date=capitalization_date, rule=controls.get("depreciation_lock_rule", "hard"))
        if counter_ledger_id == asset_ledger_id:
            _policy_block(
                controls.get("counter_ledger_match_rule", "warn"),
                "Counter ledger matches the asset ledger. Review this carefully before posting.",
            )

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
        _ensure_no_overlapping_depreciation_run(run=run)
        assets_qs = AssetService.eligible_assets_for_run(run, category_id=category_id)
        conflict = None
        asset_ids = list(assets_qs.values_list("id", flat=True))
        if asset_ids:
            conflict = (
                DepreciationRunLine.objects
                .select_related("run", "asset")
                .filter(
                    asset_id__in=asset_ids,
                    run__status__in=[DepreciationRun.RunStatus.CALCULATED, DepreciationRun.RunStatus.POSTED],
                    period_from__lte=run.period_to,
                    period_to__gte=run.period_from,
                )
                .exclude(run_id=run.id)
                .order_by("asset__asset_code", "run__period_from", "run__id")
                .first()
            )
        if conflict:
            raise ValueError(
                f"Depreciation period overlaps with existing run '{conflict.run.run_code}' "
                f"for asset '{conflict.asset.asset_code}' ({conflict.period_from} to {conflict.period_to})."
            )
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
        _ensure_no_overlapping_depreciation_run(run=run)
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

            entry = Entry.objects.filter(
                entity_id=run.entity_id,
                entityfin_id=run.entityfinid_id,
                subentity_id=run.subentity_id,
                txn_type=TxnType.FIXED_ASSET_DEPRECIATION,
                txn_id=run.id,
            ).first()
            if entry:
                entry.status = EntryStatus.REVERSED
                entry.posted_at = None
                entry.posted_by = None
                entry.save(update_fields=["status", "posted_at", "posted_by"])
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
                "updated_by",
                "updated_at",
            ]
        )
        return run

    @staticmethod
    def impair_asset_precheck(
        *,
        asset: FixedAsset,
        impairment_amount: Decimal,
        posting_date: date,
        narration: str | None = None,
    ) -> dict:
        del narration
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        impact = [
            "Impairment will create a posting batch using the category impairment ledgers.",
            "Impairment amount will increase on the asset and net book value will reduce immediately.",
            "The impairment posting will remain available for governed reversal later if correction is required.",
        ]

        if asset.status != FixedAsset.AssetStatus.ACTIVE:
            blocking_reasons.append("Only active assets can be impaired.")
        amount = q2(impairment_amount)
        if amount <= ZERO:
            blocking_reasons.append("Impairment amount must be greater than zero.")
        category = asset.category
        if not category.impairment_expense_ledger_id or not category.impairment_reserve_ledger_id:
            blocking_reasons.append("Asset category must define impairment expense and impairment reserve ledgers.")
        else:
            try:
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.impairment_expense_ledger_id, drcr=True, amount=amount, description=asset.asset_name)
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.impairment_reserve_ledger_id, drcr=False, amount=amount, description=asset.asset_name)
            except ValueError as exc:
                blocking_reasons.append(str(exc))
        if amount > q2(asset.net_book_value):
            blocking_reasons.append("Impairment amount cannot exceed current net book value.")
        settings, controls = _asset_settings_and_controls(entity_id=asset.entity_id, subentity_id=asset.subentity_id)
        locked_message = _locked_period_message(entityfinid=asset.entityfinid, posting_date=posting_date)
        if locked_message:
            blocking_reasons.append(locked_message)
        if amount == q2(asset.net_book_value) and amount > ZERO:
            _append_policy_issue(
                rule=controls.get("full_impairment_rule", "warn"),
                message="This posting will fully impair the asset and reduce net book value to zero.",
                blocking_reasons=blocking_reasons,
                warnings=warnings,
            )

        return _precheck_payload(
            action="impair",
            asset=asset,
            posting_date=posting_date,
            posting_batch_id=None,
            allowed=not blocking_reasons,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            impact=impact,
            policy_profile=_category_accounting_policy_profile(asset=asset, settings=settings),
        )

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
        _ensure_locked_period(entityfinid=asset.entityfinid, posting_date=posting_date, rule=controls.get("depreciation_lock_rule", "hard"))
        if amount == q2(asset.net_book_value) and amount > ZERO:
            _policy_block(
                controls.get("full_impairment_rule", "warn"),
                "This posting will fully impair the asset and reduce net book value to zero.",
            )

        posting = PostingService(
            entity_id=asset.entity_id,
            entityfin_id=_resolve_entityfin_id(asset),
            subentity_id=asset.subentity_id,
            user_id=user_id,
        )
        entry = posting.post(
            txn_type=TxnType.FIXED_ASSET_IMPAIRMENT,
            txn_id=asset.id,
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
        if notes is not None:
            asset.notes = notes
        asset.updated_by_id = user_id
        asset.save(update_fields=["subentity", "location_name", "department_name", "custodian_name", "notes", "updated_by", "updated_at"])
        return asset

    @staticmethod
    def transfer_asset_precheck(
        *,
        asset: FixedAsset,
        subentity_id: int | None = None,
        location_name: str | None = None,
        department_name: str | None = None,
        custodian_name: str | None = None,
        notes: str | None = None,
    ) -> dict:
        del notes
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        impact = [
            "Transfer will update the operational ownership fields on the asset record without creating a posting batch.",
            "Capitalization, impairment, disposal, and depreciation history will remain unchanged.",
            "The updated scope values will flow into downstream reporting, searches, and asset work queues.",
        ]

        if asset.status not in {FixedAsset.AssetStatus.ACTIVE, FixedAsset.AssetStatus.HELD_FOR_SALE, FixedAsset.AssetStatus.CAPITAL_WIP}:
            blocking_reasons.append("Only active, held-for-sale, or capital-WIP assets can be transferred.")

        if subentity_id is not None:
            subentity = SubEntity.objects.filter(id=subentity_id, entity_id=asset.entity_id, isactive=True).only("id", "entity_id").first()
            if subentity is None:
                blocking_reasons.append("Selected subentity belongs to a different entity or is inactive.")

        if (
            subentity_id == asset.subentity_id
            and location_name == asset.location_name
            and department_name == asset.department_name
            and custodian_name == asset.custodian_name
        ):
            warnings.append("Transfer request matches the current asset scope, so no operational fields will change.")

        if location_name is not None and not str(location_name).strip():
            warnings.append("Location is blank; asset-by-location reporting may become less useful.")
        if department_name is not None and not str(department_name).strip():
            warnings.append("Department is blank; department-wise asset analysis may become less useful.")
        if custodian_name is not None and not str(custodian_name).strip():
            warnings.append("Custodian is blank; handoff accountability may be harder to track.")

        settings = AssetSettingsService.get_settings(asset.entity_id, asset.subentity_id)
        return _precheck_payload(
            action="transfer",
            asset=asset,
            posting_date=None,
            posting_batch_id=None,
            allowed=not blocking_reasons,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            impact=impact,
            policy_profile=_category_accounting_policy_profile(asset=asset, settings=settings),
        )

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
        if notes is not None:
            asset.notes = notes
        asset.updated_by_id = user_id
        asset.save(update_fields=["subentity", "location_name", "department_name", "custodian_name", "notes", "updated_by", "updated_at"])
        return asset

    @staticmethod
    def dispose_asset_precheck(
        *,
        asset: FixedAsset,
        proceeds_ledger_id: int,
        disposal_date: date,
        sale_proceeds: Decimal,
        narration: str | None = None,
    ) -> dict:
        del narration
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        impact = [
            "Disposal will create a posting batch, move the asset to Disposed status, and set net book value to zero.",
            "Disposal proceeds and gain or loss will be stored on the asset for reporting and audit.",
            "Any later correction will need governed disposal reversal rather than direct asset edits.",
        ]

        if asset.status != FixedAsset.AssetStatus.ACTIVE:
            blocking_reasons.append("Only active assets can be disposed.")
        category = asset.category
        settings, controls = _asset_settings_and_controls(entity_id=asset.entity_id, subentity_id=asset.subentity_id)
        asset_ledger_id = asset.ledger_id or category.asset_ledger_id
        if not asset_ledger_id or not category.accumulated_depreciation_ledger_id:
            blocking_reasons.append("Asset and accumulated depreciation ledgers are required for disposal.")
        proceeds = q2(sale_proceeds)
        gross = q2(asset.gross_block)
        acc_dep = q2(asset.accumulated_depreciation)
        impairment = q2(asset.impairment_amount)
        nbv = q2(gross - acc_dep - impairment)
        gain_loss = q2(proceeds - nbv)
        if nbv < ZERO:
            _append_policy_issue(
                rule=controls.get("negative_nbv_rule", "block"),
                message="Asset net book value cannot be negative before disposal.",
                blocking_reasons=blocking_reasons,
                warnings=warnings,
            )
        if not proceeds_ledger_id:
            blocking_reasons.append("Proceeds ledger is required for disposal.")
        else:
            try:
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=proceeds_ledger_id, drcr=True, amount=proceeds, description=asset.asset_name)
            except ValueError as exc:
                blocking_reasons.append(str(exc))
        if asset_ledger_id:
            try:
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=asset_ledger_id, drcr=False, amount=gross, description=asset.asset_name)
            except ValueError as exc:
                blocking_reasons.append(str(exc))
        if category.accumulated_depreciation_ledger_id and acc_dep > ZERO:
            try:
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.accumulated_depreciation_ledger_id, drcr=True, amount=acc_dep, description=asset.asset_name)
            except ValueError as exc:
                blocking_reasons.append(str(exc))
        if impairment > ZERO:
            if not category.impairment_reserve_ledger_id:
                blocking_reasons.append("Impairment reserve ledger is required to dispose an impaired asset.")
            else:
                try:
                    _jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.impairment_reserve_ledger_id, drcr=True, amount=impairment, description=asset.asset_name)
                except ValueError as exc:
                    blocking_reasons.append(str(exc))
        if gain_loss < ZERO and not category.loss_on_sale_ledger_id:
            blocking_reasons.append("Loss on sale ledger is required when disposal creates a loss.")
        if gain_loss > ZERO and not category.gain_on_sale_ledger_id:
            blocking_reasons.append("Gain on sale ledger is required when disposal creates a gain.")
        if category.loss_on_sale_ledger_id and gain_loss < ZERO:
            try:
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.loss_on_sale_ledger_id, drcr=True, amount=abs(gain_loss), description=asset.asset_name)
            except ValueError as exc:
                blocking_reasons.append(str(exc))
        if category.gain_on_sale_ledger_id and gain_loss > ZERO:
            try:
                _jl_for_ledger(entity_id=asset.entity_id, ledger_id=category.gain_on_sale_ledger_id, drcr=False, amount=gain_loss, description=asset.asset_name)
            except ValueError as exc:
                blocking_reasons.append(str(exc))
        if asset.capitalization_date and disposal_date < asset.capitalization_date:
            _append_policy_issue(
                rule=controls.get("backdated_disposal_rule", "hard"),
                message="Disposal date cannot be earlier than the asset capitalization date.",
                blocking_reasons=blocking_reasons,
                warnings=warnings,
            )
        locked_message = _locked_period_message(entityfinid=asset.entityfinid, posting_date=disposal_date)
        if locked_message:
            blocking_reasons.append(locked_message)
        if gain_loss > ZERO:
            warnings.append(f"This disposal will book a gain of {gain_loss}.")
        elif gain_loss < ZERO:
            warnings.append(f"This disposal will book a loss of {abs(gain_loss)}.")
        if impairment > ZERO:
            warnings.append("This asset already carries impairment, so disposal will also clear the impairment reserve from books.")

        return _precheck_payload(
            action="dispose",
            asset=asset,
            posting_date=disposal_date,
            posting_batch_id=None,
            allowed=not blocking_reasons,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            impact=impact,
            policy_profile=_category_accounting_policy_profile(asset=asset, settings=settings),
        )

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
            subentity=asset.subentity,
            category=category,
            ledger=asset.ledger or category.asset_ledger,
        )
        _ensure_locked_period(entityfinid=asset.entityfinid, posting_date=disposal_date, rule=controls.get("depreciation_lock_rule", "hard"))
        _ensure_backdated_disposal(asset=asset, disposal_date=disposal_date, rule=controls.get("backdated_disposal_rule", "hard"))
        _ensure_locked_period(entityfinid=asset.entityfinid, posting_date=disposal_date, rule=controls.get("depreciation_lock_rule", "hard"))
        proceeds = q2(sale_proceeds)
        if proceeds < ZERO:
            raise ValueError("Sale proceeds cannot be negative.")
        gross = q2(asset.gross_block)
        acc_dep = q2(asset.accumulated_depreciation)
        impairment = q2(asset.impairment_amount)
        nbv = q2(gross - acc_dep - impairment)
        gain_loss = q2(proceeds - nbv)
        if nbv < ZERO:
            _policy_block(controls.get("negative_nbv_rule", "block"), "Asset net book value cannot be negative before disposal.")
        if proceeds > ZERO and not proceeds_ledger_id:
            raise ValueError("Proceeds ledger is required when sale proceeds are recorded.")

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

    @staticmethod
    @transaction.atomic
    def reverse_capitalization(*, asset: FixedAsset, reason: str, user_id: int | None = None) -> FixedAsset:
        if not asset.capitalization_posting_batch_id:
            raise ValueError("This asset does not have a posted capitalization to reverse.")
        if asset.disposal_posting_batch_id or asset.status == FixedAsset.AssetStatus.DISPOSED:
            raise ValueError("Capitalization cannot be reversed after disposal. Reverse disposal first.")
        if asset.impairment_posting_batch_id or q2(asset.impairment_amount) > ZERO:
            raise ValueError("Capitalization cannot be reversed after impairment. Reverse impairment first.")
        if asset.depreciation_lines.filter(run__status__in=[DepreciationRun.RunStatus.CALCULATED, DepreciationRun.RunStatus.POSTED]).exists():
            raise ValueError("Capitalization cannot be reversed while depreciation runs exist. Cancel those runs first.")

        _, controls = _asset_settings_and_controls(entity_id=asset.entity_id, subentity_id=asset.subentity_id)
        posting_date = asset.capitalization_date or asset.acquisition_date
        _ensure_locked_period(entityfinid=asset.entityfinid, posting_date=posting_date, rule=controls.get("depreciation_lock_rule", "hard"))

        entry = _entry_for_asset_txn(asset=asset, txn_type=TxnType.FIXED_ASSET_CAPITALIZATION)
        _reverse_entry_and_batch(entry=entry, posting_batch=asset.capitalization_posting_batch, reason=reason)

        prior_capitalization_date = asset.capitalization_date
        asset.status = FixedAsset.AssetStatus.CAPITAL_WIP if (asset.purchase_document_no or asset.source_purchase_lines.exists()) else FixedAsset.AssetStatus.DRAFT
        asset.capitalization_date = None
        asset.depreciation_start_date = None
        if asset.put_to_use_date and asset.put_to_use_date == prior_capitalization_date:
            asset.put_to_use_date = None
        asset.capitalization_posting_batch = None
        asset.updated_by_id = user_id
        asset.notes = _append_note(asset.notes, f"Capitalization reversed: {reason}")
        asset.net_book_value = q2(asset.gross_block) - q2(asset.accumulated_depreciation) - q2(asset.impairment_amount)
        asset.save(
            update_fields=[
                "status",
                "capitalization_date",
                "depreciation_start_date",
                "put_to_use_date",
                "capitalization_posting_batch",
                "notes",
                "net_book_value",
                "updated_by",
                "updated_at",
            ]
        )
        return asset

    @staticmethod
    def reverse_capitalization_precheck(*, asset: FixedAsset) -> dict:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        impact = [
            "Capitalization posting will be marked reversed and its posting batch will be deactivated.",
            "Asset status will move back to Draft or Capital WIP depending on its source.",
            "Capitalization date and depreciation start date will be cleared from the asset record.",
        ]

        if not asset.capitalization_posting_batch_id:
            blocking_reasons.append("This asset does not have a posted capitalization to reverse.")
        if asset.disposal_posting_batch_id or asset.status == FixedAsset.AssetStatus.DISPOSED:
            blocking_reasons.append("Capitalization cannot be reversed after disposal. Reverse disposal first.")
        if asset.impairment_posting_batch_id or q2(asset.impairment_amount) > ZERO:
            blocking_reasons.append("Capitalization cannot be reversed after impairment. Reverse impairment first.")
        if asset.depreciation_lines.filter(run__status__in=[DepreciationRun.RunStatus.CALCULATED, DepreciationRun.RunStatus.POSTED]).exists():
            blocking_reasons.append("Capitalization cannot be reversed while depreciation runs exist. Cancel those runs first.")

        posting_date = asset.capitalization_date or asset.acquisition_date
        locked_message = _locked_period_message(entityfinid=asset.entityfinid, posting_date=posting_date)
        if locked_message:
            blocking_reasons.append(locked_message)

        if q2(asset.accumulated_depreciation) > ZERO:
            warnings.append("This asset already carries accumulated depreciation in its current snapshot.")
        if asset.purchase_document_no or asset.source_purchase_lines.exists():
            warnings.append("This asset originated from purchase intake, so reversal will restore it to Capital WIP rather than Draft.")

        return _precheck_payload(
            action="capitalization",
            asset=asset,
            posting_date=posting_date,
            posting_batch_id=asset.capitalization_posting_batch_id,
            allowed=not blocking_reasons,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            impact=impact,
        )

    @staticmethod
    @transaction.atomic
    def reverse_impairment(*, asset: FixedAsset, reason: str, user_id: int | None = None) -> FixedAsset:
        if not asset.impairment_posting_batch_id or q2(asset.impairment_amount) <= ZERO:
            raise ValueError("This asset does not have a posted impairment to reverse.")
        if asset.disposal_posting_batch_id or asset.status == FixedAsset.AssetStatus.DISPOSED:
            raise ValueError("Impairment cannot be reversed after disposal. Reverse disposal first.")

        _, controls = _asset_settings_and_controls(entity_id=asset.entity_id, subentity_id=asset.subentity_id)
        entry = _entry_for_posting_batch(asset.impairment_posting_batch)
        posting_date = entry.posting_date if entry else asset.capitalization_date or asset.acquisition_date
        _ensure_locked_period(entityfinid=asset.entityfinid, posting_date=posting_date, rule=controls.get("depreciation_lock_rule", "hard"))

        _reverse_entry_and_batch(entry=entry, posting_batch=asset.impairment_posting_batch, reason=reason)

        asset.impairment_amount = ZERO
        asset.impairment_posting_batch = None
        asset.updated_by_id = user_id
        asset.notes = _append_note(asset.notes, f"Impairment reversed: {reason}")
        asset.net_book_value = q2(asset.gross_block) - q2(asset.accumulated_depreciation)
        asset.save(
            update_fields=[
                "impairment_amount",
                "impairment_posting_batch",
                "notes",
                "net_book_value",
                "updated_by",
                "updated_at",
            ]
        )
        return asset

    @staticmethod
    def reverse_impairment_precheck(*, asset: FixedAsset) -> dict:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        impact = [
            "Impairment posting will be marked reversed and its posting batch will be deactivated.",
            "Impairment amount will be reset to zero on the asset record.",
            "Net book value will be recalculated from gross block and accumulated depreciation.",
        ]

        if not asset.impairment_posting_batch_id or q2(asset.impairment_amount) <= ZERO:
            blocking_reasons.append("This asset does not have a posted impairment to reverse.")
        if asset.disposal_posting_batch_id or asset.status == FixedAsset.AssetStatus.DISPOSED:
            blocking_reasons.append("Impairment cannot be reversed after disposal. Reverse disposal first.")

        entry = _entry_for_posting_batch(asset.impairment_posting_batch)
        posting_date = entry.posting_date if entry else asset.capitalization_date or asset.acquisition_date
        locked_message = _locked_period_message(entityfinid=asset.entityfinid, posting_date=posting_date)
        if locked_message:
            blocking_reasons.append(locked_message)

        if q2(asset.accumulated_depreciation) > ZERO:
            warnings.append("Depreciation balances will remain in place after impairment reversal.")

        return _precheck_payload(
            action="impairment",
            asset=asset,
            posting_date=posting_date,
            posting_batch_id=asset.impairment_posting_batch_id,
            allowed=not blocking_reasons,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            impact=impact,
        )

    @staticmethod
    @transaction.atomic
    def reverse_disposal(*, asset: FixedAsset, reason: str, user_id: int | None = None) -> FixedAsset:
        if not asset.disposal_posting_batch_id or asset.status != FixedAsset.AssetStatus.DISPOSED:
            raise ValueError("This asset does not have a posted disposal to reverse.")

        _, controls = _asset_settings_and_controls(entity_id=asset.entity_id, subentity_id=asset.subentity_id)
        entry = _entry_for_asset_txn(asset=asset, txn_type=TxnType.FIXED_ASSET_DISPOSAL)
        posting_date = entry.posting_date if entry else asset.disposal_date or asset.capitalization_date or asset.acquisition_date
        _ensure_locked_period(entityfinid=asset.entityfinid, posting_date=posting_date, rule=controls.get("depreciation_lock_rule", "hard"))

        _reverse_entry_and_batch(entry=entry, posting_batch=asset.disposal_posting_batch, reason=reason)

        asset.status = FixedAsset.AssetStatus.ACTIVE
        asset.disposal_date = None
        asset.disposal_posting_batch = None
        asset.disposal_proceeds = ZERO
        asset.disposal_gain_loss = ZERO
        asset.updated_by_id = user_id
        asset.notes = _append_note(asset.notes, f"Disposal reversed: {reason}")
        asset.net_book_value = q2(asset.gross_block) - q2(asset.accumulated_depreciation) - q2(asset.impairment_amount)
        asset.save(
            update_fields=[
                "status",
                "disposal_date",
                "disposal_posting_batch",
                "disposal_proceeds",
                "disposal_gain_loss",
                "notes",
                "net_book_value",
                "updated_by",
                "updated_at",
            ]
        )
        return asset

    @staticmethod
    def reverse_disposal_precheck(*, asset: FixedAsset) -> dict:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        impact = [
            "Disposal posting will be marked reversed and its posting batch will be deactivated.",
            "Asset status will return to Active and disposal fields will be cleared.",
            "Net book value will be restored from the current gross block, depreciation, and impairment balances.",
        ]

        if not asset.disposal_posting_batch_id or asset.status != FixedAsset.AssetStatus.DISPOSED:
            blocking_reasons.append("This asset does not have a posted disposal to reverse.")

        entry = _entry_for_asset_txn(asset=asset, txn_type=TxnType.FIXED_ASSET_DISPOSAL)
        posting_date = entry.posting_date if entry else asset.disposal_date or asset.capitalization_date or asset.acquisition_date
        locked_message = _locked_period_message(entityfinid=asset.entityfinid, posting_date=posting_date)
        if locked_message:
            blocking_reasons.append(locked_message)

        if q2(asset.impairment_amount) > ZERO:
            warnings.append("Any existing impairment balance will remain after disposal reversal.")
        if q2(asset.accumulated_depreciation) > ZERO:
            warnings.append("Accumulated depreciation stays on the asset when disposal is reversed.")

        return _precheck_payload(
            action="disposal",
            asset=asset,
            posting_date=posting_date,
            posting_batch_id=asset.disposal_posting_batch_id,
            allowed=not blocking_reasons,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            impact=impact,
        )
