from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from entity.models import Entity, EntityBankAccountV2
from financial.models import AccountBankDetails, Ledger, account


@dataclass(frozen=True)
class EligibleBankLedgerRow:
    id: int
    ledger_code: Optional[int]
    name: str
    account_id: Optional[int]
    accountname: Optional[str]


@dataclass(frozen=True)
class BankAccountMappingRow:
    id: int
    entity_id: int
    bank_name: str
    account_number_masked: str
    ifsc_code: str
    branch: Optional[str]
    is_primary: bool
    is_active: bool
    ledger_id: Optional[int]
    ledger_name: Optional[str]
    account_id: Optional[int]
    account_name: Optional[str]
    mapping_source: str


class EntityBankAccountMappingService:
    @staticmethod
    def _mask_account_number(account_number: str) -> str:
        value = str(account_number or "").strip()
        if len(value) <= 4:
            return value or ""
        return f"***{value[-4:]}"

    @staticmethod
    def _validate_entity(entity_id: int) -> None:
        if not Entity.objects.filter(id=entity_id).exists():
            raise NotFound("Entity not found.")

    @staticmethod
    def _fallback_detail(entity_id: int, bank_account: EntityBankAccountV2) -> Optional[AccountBankDetails]:
        details_qs = AccountBankDetails.objects.filter(entity_id=entity_id, isactive=True).select_related("account__ledger")
        direct = details_qs.filter(banKAcno=bank_account.account_number)
        if bank_account.ifsc_code:
            direct = direct.filter(ifsc__iexact=bank_account.ifsc_code)
        detail = direct.first()
        if detail:
            return detail
        suffix = bank_account.account_number[-4:]
        if not suffix:
            return None
        fallback = details_qs.filter(banKAcno__endswith=suffix)
        if bank_account.ifsc_code:
            fallback = fallback.filter(ifsc__iexact=bank_account.ifsc_code)
        return fallback.first()

    @classmethod
    def list_rows(cls, *, entity_id: int) -> list[BankAccountMappingRow]:
        cls._validate_entity(entity_id)
        bank_accounts = list(
            EntityBankAccountV2.objects.filter(entity_id=entity_id, isactive=True)
            .select_related("book_ledger", "book_ledger__account_profile")
            .order_by("-is_primary", "bank_name", "id")
        )

        rows: list[BankAccountMappingRow] = []
        for bank_account in bank_accounts:
            explicit_ledger = bank_account.book_ledger
            explicit_account = getattr(explicit_ledger, "account_profile", None) if explicit_ledger else None
            ledger = explicit_ledger
            acc = explicit_account
            mapping_source = "explicit" if explicit_ledger else "none"

            if ledger is None:
                detail = cls._fallback_detail(entity_id, bank_account)
                if detail and detail.account_id:
                    acc = detail.account
                    ledger = getattr(detail.account, "ledger", None)
                    mapping_source = "derived"

            rows.append(
                BankAccountMappingRow(
                    id=bank_account.id,
                    entity_id=bank_account.entity_id,
                    bank_name=bank_account.bank_name,
                    account_number_masked=cls._mask_account_number(bank_account.account_number),
                    ifsc_code=bank_account.ifsc_code,
                    branch=bank_account.branch,
                    is_primary=bool(bank_account.is_primary),
                    is_active=bool(bank_account.isactive),
                    ledger_id=getattr(ledger, "id", None),
                    ledger_name=getattr(ledger, "name", None),
                    account_id=getattr(acc, "id", None),
                    account_name=getattr(acc, "accountname", None),
                    mapping_source=mapping_source,
                )
            )
        return rows

    @staticmethod
    def eligible_ledgers(*, entity_id: int) -> list[EligibleBankLedgerRow]:
        EntityBankAccountMappingService._validate_entity(entity_id)
        queryset = (
            Ledger.objects.filter(entity_id=entity_id, isactive=True, account_profile__isnull=False)
            .select_related("account_profile")
            .order_by("name", "id")
        )
        return [
            EligibleBankLedgerRow(
                id=ledger.id,
                ledger_code=ledger.ledger_code,
                name=ledger.name,
                account_id=getattr(ledger.account_profile, "id", None),
                accountname=getattr(ledger.account_profile, "accountname", None),
            )
            for ledger in queryset
        ]

    @staticmethod
    def _validate_ledger(entity_id: int, ledger_id: Optional[int]) -> Optional[Ledger]:
        if not ledger_id:
            return None
        ledger = (
            Ledger.objects.filter(entity_id=entity_id, id=ledger_id, isactive=True)
            .select_related("account_profile")
            .first()
        )
        if ledger is None:
            raise ValidationError({"ledger_id": "ledger_id not found for entity."})
        if getattr(ledger, "account_profile", None) is None:
            raise ValidationError({"ledger_id": "Selected ledger must have an account profile for bank reconciliation."})
        return ledger

    @classmethod
    @transaction.atomic
    def update_mapping(cls, *, entity_id: int, bank_account_id: int, ledger_id: Optional[int]) -> BankAccountMappingRow:
        cls._validate_entity(entity_id)
        bank_account = EntityBankAccountV2.objects.filter(entity_id=entity_id, id=bank_account_id, isactive=True).first()
        if bank_account is None:
            raise NotFound("Bank account not found for entity.")
        bank_account.book_ledger = cls._validate_ledger(entity_id, ledger_id)
        bank_account.save(update_fields=["book_ledger"])
        return cls._row_by_id(entity_id=entity_id, bank_account_id=bank_account_id)

    @classmethod
    def _row_by_id(cls, *, entity_id: int, bank_account_id: int) -> BankAccountMappingRow:
        for row in cls.list_rows(entity_id=entity_id):
            if row.id == bank_account_id:
                return row
        raise NotFound("Bank account mapping row not found.")
