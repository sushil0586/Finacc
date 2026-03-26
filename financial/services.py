from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch

from financial.models import (
    AccountAddress,
    AccountCommercialProfile,
    AccountComplianceProfile,
    FinancialSettings,
    Ledger,
    account,
)
from financial.gstin import validate_financial_gstin
from posting.services.balances import ledger_balance_map


def get_or_create_financial_settings(entity, createdby=None):
    settings_obj, created = FinancialSettings.objects.get_or_create(
        entity=entity,
        defaults={
            "createdby": createdby,
        },
    )
    return settings_obj, created


def sync_ledger_for_account(acc, ledger_overrides=None):
    """
    Keep the additive Ledger row in sync with the current account row.

    This is intentionally narrow and compatibility-focused:
    - no endpoint contract changes
    - no posting cutover yet
    - account remains the operational source for now

    Later this service should become the primary create/update path once
    accounting flows are Ledger-first.
    """
    ledger_defaults = {
        "entity": acc.entity,
        "ledger_code": acc.accountcode,
        "name": acc.accountname or f"Account {acc.pk}",
        "legal_name": acc.legalname,
        "accounthead": acc.accounthead,
        "creditaccounthead": acc.creditaccounthead,
        "accounttype": acc.accounttype,
        "is_party": True,
        "is_system": False,
        "canbedeleted": acc.canbedeleted,
        "openingbcr": acc.openingbcr,
        "openingbdr": acc.openingbdr,
        "createdby": acc.createdby,
        "isactive": acc.isactive,
    }
    if ledger_overrides:
        ledger_defaults.update(ledger_overrides)

    if acc.ledger_id:
        ledger = acc.ledger
        if acc.entity_id and ledger.entity_id and ledger.entity_id != acc.entity_id:
            raise ValidationError({"ledger": "Selected ledger belongs to a different entity."})
        for field, value in ledger_defaults.items():
            setattr(ledger, field, value)
        ledger.save()
    else:
        ledger = Ledger.objects.create(**ledger_defaults)
        acc.ledger = ledger
        acc.save(update_fields=["ledger"])

    if acc.contraaccount_id and acc.contraaccount and acc.contraaccount.ledger_id:
        if acc.contraaccount.entity_id and acc.entity_id and acc.contraaccount.entity_id != acc.entity_id:
            raise ValidationError({"contraaccount": "Contra account belongs to a different entity."})
        if ledger.contra_ledger_id != acc.contraaccount.ledger_id:
            ledger.contra_ledger = acc.contraaccount.ledger
            ledger.save(update_fields=["contra_ledger"])
    elif ledger.contra_ledger_id is not None:
        ledger.contra_ledger = None
        ledger.save(update_fields=["contra_ledger"])

    return ledger


def sync_account_profiles_for_account(acc):
    """Backward-compatible wrapper; normalized profiles are now source of truth."""
    ensure_normalized_profiles_for_account(acc)


def ensure_normalized_profiles_for_account(acc):
    """Ensure normalized profile rows exist for an account with structural defaults."""
    compliance_defaults = {
        "entity": acc.entity,
        "createdby": acc.createdby,
        "isactive": bool(acc.isactive),
    }
    commercial_defaults = {
        "entity": acc.entity,
        "createdby": acc.createdby,
        "isactive": bool(acc.isactive),
    }

    AccountComplianceProfile.objects.update_or_create(account=acc, defaults=compliance_defaults)
    AccountCommercialProfile.objects.update_or_create(account=acc, defaults=commercial_defaults)


@transaction.atomic
def create_account_with_synced_ledger(*, account_data, ledger_overrides=None):
    """
    Canonical account create path for new APIs:
    - allocates account code when missing
    - creates account row
    - creates/syncs linked ledger row
    """
    data = dict(account_data or {})
    entity = data.get("entity")
    if data.get("accountcode") is None and entity is not None:
        data["accountcode"] = allocate_next_ledger_code(entity_id=entity.id)

    acc = account.objects.create(**data)
    sync_ledger_for_account(acc, ledger_overrides=ledger_overrides)
    ensure_normalized_profiles_for_account(acc)
    return acc


def allocate_next_ledger_code(*, entity_id):
    """
    Generate the next ledger code for an entity.

    The new financial APIs should not rely on the legacy account-code endpoint.
    For account-managed ledgers, we allocate a code lazily if one is not
    supplied. This keeps the account page simple while still producing a real
    posting ledger.
    """
    max_code = (
        Ledger.objects.filter(entity_id=entity_id, ledger_code__isnull=False)
        .order_by("-ledger_code")
        .values_list("ledger_code", flat=True)
        .first()
    )
    return (max_code or 999) + 1


def bootstrap_financial_settings_for_all_entities(entity_model, createdby=None):
    created_count = 0
    for entity in entity_model.objects.all().iterator():
        _, created = get_or_create_financial_settings(entity, createdby=createdby)
        created_count += 1 if created else 0
    return created_count


def resync_ledgers(entity_id=None):
    from financial.models import account

    qs = account.objects.select_related("ledger", "contraaccount", "contraaccount__ledger")
    if entity_id is not None:
        qs = qs.filter(entity_id=entity_id)

    synced = 0
    for acc in qs.iterator():
        sync_ledger_for_account(acc)
        ensure_normalized_profiles_for_account(acc)
        synced += 1
    return synced


@transaction.atomic
def backfill_missing_account_profiles(entity_id=None, dry_run=False):
    """
    One-time repair utility for legacy accounts that missed normalized profile rows.

    Creates missing AccountComplianceProfile / AccountCommercialProfile rows.
    """
    qs = account.objects.all()
    if entity_id is not None:
        qs = qs.filter(entity_id=entity_id)

    account_ids = list(qs.values_list("id", flat=True))
    if not account_ids:
        return {
            "accounts_scanned": 0,
            "missing_compliance": 0,
            "missing_commercial": 0,
            "missing_primary_address": 0,
            "accounts_updated": 0,
        }

    compliance_ids = set(
        AccountComplianceProfile.objects.filter(account_id__in=account_ids).values_list("account_id", flat=True)
    )
    commercial_ids = set(
        AccountCommercialProfile.objects.filter(account_id__in=account_ids).values_list("account_id", flat=True)
    )
    missing_compliance = 0
    missing_commercial = 0
    missing_primary_address = 0
    accounts_updated = 0

    for acc in qs.iterator():
        needs_compliance = acc.id not in compliance_ids
        needs_commercial = acc.id not in commercial_ids
        needs_primary_address = False

        if needs_compliance:
            missing_compliance += 1
        if needs_commercial:
            missing_commercial += 1
        if needs_primary_address:
            missing_primary_address += 1

        if not dry_run and (needs_compliance or needs_commercial or needs_primary_address):
            ensure_normalized_profiles_for_account(acc)
            accounts_updated += 1

    return {
        "accounts_scanned": len(account_ids),
        "missing_compliance": missing_compliance,
        "missing_commercial": missing_commercial,
        "missing_primary_address": missing_primary_address,
        "accounts_updated": accounts_updated,
    }


@transaction.atomic
def apply_normalized_profile_payload(
    acc,
    *,
    compliance_data=None,
    commercial_data=None,
    primary_address_data=None,
    createdby=None,
):
    """
    Persist normalized profile payloads without relying on legacy account columns.
    """
    actor = createdby or acc.createdby

    if compliance_data is not None:
        defaults = {"entity": acc.entity, "createdby": actor}
        if "gstno" in compliance_data:
            compliance_data = dict(compliance_data)
            compliance_data["gstno"] = validate_financial_gstin(compliance_data.get("gstno"))
        defaults.update(compliance_data)
        compliance_profile, _ = AccountComplianceProfile.objects.update_or_create(account=acc, defaults=defaults)
        acc.compliance_profile = compliance_profile

    if commercial_data is not None:
        defaults = {"entity": acc.entity, "createdby": actor}
        defaults.update(commercial_data)
        commercial_profile, _ = AccountCommercialProfile.objects.update_or_create(account=acc, defaults=defaults)
        acc.commercial_profile = commercial_profile

    if primary_address_data is not None:
        address = (
            AccountAddress.objects.filter(account=acc, isprimary=True, isactive=True)
            .order_by("-id")
            .first()
        )
        if address is None:
            address = AccountAddress(
                account=acc,
                address_type=AccountAddress.AddressType.BILLING,
                isprimary=True,
                isactive=True,
            )
        address.entity = acc.entity
        address.createdby = actor
        fk_fields = {"country", "state", "district", "city"}
        for field_name, value in primary_address_data.items():
            # Frontend sends FK ids (e.g. state: 1). Django FK attributes
            # expect model instances unless we assign via <field>_id.
            if field_name in fk_fields:
                normalized = None if value in (None, "", 0, "0") else value
                setattr(address, f"{field_name}_id", normalized)
                continue
            setattr(address, field_name, value)
        address.save()


def build_ledger_balance_rows(entity_id, fin_start, fin_end, ledger_ids=None, accounthead_ids=None):
    primary_address_qs = AccountAddress.objects.filter(isprimary=True, isactive=True).select_related("city")
    qs = (
        Ledger.objects.filter(entity_id=entity_id, isactive=True)
        .select_related(
            "accounthead",
            "creditaccounthead",
            "account_profile",
            "account_profile__compliance_profile",
        )
        .prefetch_related(
            Prefetch(
                "account_profile__addresses",
                queryset=primary_address_qs,
                to_attr="prefetched_primary_addresses",
            )
        )
        .order_by("name")
    )

    if ledger_ids:
        qs = qs.filter(id__in=ledger_ids)
    if accounthead_ids:
        qs = qs.filter(accounthead_id__in=accounthead_ids)

    balance_map = ledger_balance_map(
        entity_id=entity_id,
        fin_start=fin_start,
        fin_end=fin_end,
        ledger_ids=ledger_ids,
        accounthead_ids=accounthead_ids,
    )

    rows = []
    for ledger in qs:
        account_profile = getattr(ledger, "account_profile", None)
        compliance = getattr(account_profile, "compliance_profile", None)
        primary_address = None
        if account_profile is not None:
            prefetched_primary = getattr(account_profile, "prefetched_primary_addresses", None)
            if prefetched_primary:
                primary_address = prefetched_primary[0]
        ledger_balance = balance_map.get(ledger.id, {"balance": 0, "debit": 0, "credit": 0})
        balance = ledger_balance["balance"]
        rows.append(
            {
                "ledger_id": ledger.id,
                "account_id": getattr(account_profile, "id", None),
                "ledger_code": ledger.ledger_code,
                "ledger_name": ledger.name,
                "accountname": getattr(account_profile, "accountname", None) or ledger.name,
                "accgst": getattr(compliance, "gstno", None),
                "accpan": getattr(compliance, "pan", None),
                "cityname": getattr(getattr(primary_address, "city", None), "cityname", None),
                "accounthead_id": ledger.accounthead_id,
                "accounthead_name": getattr(ledger.accounthead, "name", None),
                "creditaccounthead_id": ledger.creditaccounthead_id,
                "creditaccounthead_name": getattr(ledger.creditaccounthead, "name", None),
                "accanbedeleted": ledger.canbedeleted,
                "balance": balance,
                "debit": ledger_balance["debit"],
                "credit": ledger_balance["credit"],
                "drcr": "CR" if balance < 0 else "DR",
                "is_party": ledger.is_party,
            }
        )

    return rows
