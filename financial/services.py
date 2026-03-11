from financial.models import FinancialSettings, Ledger
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
        for field, value in ledger_defaults.items():
            setattr(ledger, field, value)
        ledger.save()
    else:
        ledger = Ledger.objects.create(**ledger_defaults)
        acc.ledger = ledger
        acc.save(update_fields=["ledger"])

    if acc.contraaccount_id and acc.contraaccount and acc.contraaccount.ledger_id:
        if ledger.contra_ledger_id != acc.contraaccount.ledger_id:
            ledger.contra_ledger = acc.contraaccount.ledger
            ledger.save(update_fields=["contra_ledger"])
    elif ledger.contra_ledger_id is not None:
        ledger.contra_ledger = None
        ledger.save(update_fields=["contra_ledger"])

    return ledger


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
        synced += 1
    return synced


def build_ledger_balance_rows(entity_id, fin_start, fin_end, ledger_ids=None, accounthead_ids=None):
    qs = (
        Ledger.objects.filter(entity_id=entity_id, isactive=True)
        .select_related(
            "accounthead",
            "creditaccounthead",
            "account_profile",
            "account_profile__city",
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
        ledger_balance = balance_map.get(ledger.id, {"balance": 0, "debit": 0, "credit": 0})
        balance = ledger_balance["balance"]
        rows.append(
            {
                "ledger_id": ledger.id,
                "account_id": getattr(account_profile, "id", None),
                "ledger_code": ledger.ledger_code,
                "ledger_name": ledger.name,
                "accountname": getattr(account_profile, "accountname", None) or ledger.name,
                "accgst": getattr(account_profile, "gstno", None),
                "accpan": getattr(account_profile, "pan", None),
                "cityname": getattr(getattr(account_profile, "city", None), "cityname", None),
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
