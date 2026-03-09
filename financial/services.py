from django.db.models import Sum

from financial.models import FinancialSettings, Ledger
from invoice.models import StockTransactions


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
        ledger_defaults.update({k: v for k, v in ledger_overrides.items() if v is not None})

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

    account_profile_ids = list(
        qs.exclude(account_profile__isnull=True).values_list("account_profile_id", flat=True)
    )

    balance_map = {}
    if account_profile_ids:
        balance_rows = (
            StockTransactions.objects.filter(
                entity_id=entity_id,
                isactive=1,
                account_id__in=account_profile_ids,
                entrydatetime__range=(fin_start, fin_end),
            )
            .exclude(accounttype="MD")
            .exclude(transactiontype__in=["PC"])
            .values("account_id")
            .annotate(balance=Sum("debitamount", default=0) - Sum("creditamount", default=0))
        )
        balance_map = {row["account_id"]: (row["balance"] or 0) for row in balance_rows}

    rows = []
    for ledger in qs:
        account_profile = getattr(ledger, "account_profile", None)
        balance = balance_map.get(getattr(account_profile, "id", None), 0)
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
                "debit": max(balance, 0),
                "credit": abs(min(balance, 0)),
                "drcr": "CR" if balance < 0 else "DR",
                "is_party": ledger.is_party,
            }
        )

    return rows
