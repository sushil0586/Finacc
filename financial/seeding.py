from decimal import Decimal

from django.db import transaction

from entity.models import EntityConstitution
from financial.models import Credit, Debit, FinancialSettings, account, accountHead, accounttype
from financial.seed_catalogs import FINANCIAL_TEMPLATES
from financial.services import get_or_create_financial_settings, sync_ledger_for_account


class FinancialSeedService:
    """
    Entity bootstrap seeding for the financial domain.

    This is intentionally service-driven and idempotent. It preserves the
    account/account head codes already relied on elsewhere in the project while
    also keeping the additive Ledger foundation synchronized.
    """

    DEFAULT_TEMPLATE = "standard_trading"

    @classmethod
    @transaction.atomic
    def seed_entity(cls, *, entity, actor, template_code=None):
        template = FINANCIAL_TEMPLATES[template_code or cls.DEFAULT_TEMPLATE]
        settings_obj, _ = get_or_create_financial_settings(entity, createdby=actor)

        type_map = cls._seed_account_types(entity=entity, actor=actor, rows=template["account_types"])
        head_map = cls._seed_account_heads(entity=entity, actor=actor, rows=template["account_heads"], type_map=type_map)
        account_rows = cls._seed_default_accounts(
            entity=entity,
            actor=actor,
            rows=template["default_accounts"],
            head_map=head_map,
        )
        constitution_rows = cls._seed_constitution_accounts(entity=entity, actor=actor, head_map=head_map)

        return {
            "template_code": template_code or cls.DEFAULT_TEMPLATE,
            "financial_settings_id": settings_obj.id,
            "account_type_count": len(type_map),
            "account_head_count": len(head_map),
            "default_account_count": len(account_rows),
            "constitution_account_count": constitution_rows,
        }

    @staticmethod
    def _bool_balance(normal_balance):
        return normal_balance == Debit

    @classmethod
    def _seed_account_types(cls, *, entity, actor, rows):
        type_map = {}
        for row in rows:
            acc_type, _ = accounttype.objects.get_or_create(
                entity=entity,
                accounttypecode=row["code"],
                defaults={
                    "accounttypename": row["name"],
                    "balanceType": cls._bool_balance(row["normal_balance"]),
                    "createdby": actor,
                },
            )
            acc_type.accounttypename = row["name"]
            acc_type.balanceType = cls._bool_balance(row["normal_balance"])
            if actor and not acc_type.createdby_id:
                acc_type.createdby = actor
            acc_type.save()
            type_map[row["code"]] = acc_type
        return type_map

    @classmethod
    def _seed_account_heads(cls, *, entity, actor, rows, type_map):
        head_map = {}
        for row in rows:
            acc_type = type_map[row["type_code"]]
            head, _ = accountHead.objects.get_or_create(
                entity=entity,
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "detailsingroup": row["detailsingroup"],
                    "balanceType": row["balance_type"],
                    "drcreffect": row["drcreffect"],
                    "description": row["name"],
                    "accounttype": acc_type,
                    "canbedeleted": False,
                    "createdby": actor,
                },
            )
            head.name = row["name"]
            head.detailsingroup = row["detailsingroup"]
            head.balanceType = row["balance_type"]
            head.drcreffect = row["drcreffect"]
            head.description = row["name"]
            head.accounttype = acc_type
            head.canbedeleted = False
            if actor and not head.createdby_id:
                head.createdby = actor
            head.save()
            head_map[row["code"]] = head
        return head_map

    @classmethod
    def _seed_default_accounts(cls, *, entity, actor, rows, head_map):
        created_or_updated = []
        for row in rows:
            head = head_map[row["head_code"]]
            credit_head = head_map.get(row.get("credit_head_code")) or head
            acc, _ = account.objects.get_or_create(
                entity=entity,
                accountcode=row["code"],
                defaults={
                    "accountname": row["name"],
                    "legalname": row["name"],
                    "accounthead": head,
                    "creditaccounthead": credit_head,
                    "accounttype": head.accounttype,
                    "partytype": row.get("party_type") or "Other",
                    "approved": True,
                    "isactive": True,
                    "canbedeleted": False,
                    "createdby": actor,
                    "openingbcr": Decimal("0.00"),
                    "openingbdr": Decimal("0.00"),
                },
            )
            acc.accountname = row["name"]
            acc.legalname = row["name"]
            acc.accounthead = head
            acc.creditaccounthead = credit_head
            acc.accounttype = head.accounttype
            acc.partytype = row.get("party_type") or acc.partytype or "Other"
            acc.approved = True
            acc.isactive = True
            acc.canbedeleted = False
            if actor and not acc.createdby_id:
                acc.createdby = actor
            if acc.openingbcr is None:
                acc.openingbcr = Decimal("0.00")
            if acc.openingbdr is None:
                acc.openingbdr = Decimal("0.00")
            acc.save()
            sync_ledger_for_account(acc, ledger_overrides={"is_system": True, "is_party": row.get("party_type") in {"Customer", "Vendor", "Bank", "Government"}})
            created_or_updated.append(acc.id)
        return created_or_updated

    @classmethod
    def _seed_constitution_accounts(cls, *, entity, actor, head_map):
        const_code = getattr(entity.const, "constcode", None)
        if const_code == "01":
            head_code = 6200
        elif const_code == "02":
            head_code = 6300
        else:
            return 0

        head = head_map.get(head_code)
        if not head:
            return 0

        count = 0
        for detail in EntityConstitution.objects.filter(entity=entity).order_by("id"):
            existing = account.objects.filter(
                entity=entity,
                accounthead=head,
                accountname=detail.shareholder,
                pan=detail.pan,
            ).first()
            if existing:
                acc = existing
            else:
                next_code = cls._next_account_code(entity)
                acc = account(
                    entity=entity,
                    accountcode=next_code,
                    accounthead=head,
                    creditaccounthead=head,
                    accounttype=head.accounttype,
                    accountname=detail.shareholder,
                    legalname=detail.shareholder,
                    pan=detail.pan,
                    sharepercentage=detail.sharepercentage,
                    country=entity.country,
                    state=entity.state,
                    district=entity.district,
                    city=entity.city,
                    emailid=entity.email,
                    accountdate=cls._first_fin_start_date(entity),
                    partytype="Other",
                    approved=True,
                    isactive=True,
                    canbedeleted=False,
                    createdby=actor,
                    openingbcr=Decimal("0.00"),
                    openingbdr=Decimal("0.00"),
                )
            acc.accounthead = head
            acc.creditaccounthead = head
            acc.accounttype = head.accounttype
            acc.accountname = detail.shareholder
            acc.legalname = detail.shareholder
            acc.pan = detail.pan
            acc.sharepercentage = detail.sharepercentage
            acc.country = entity.country
            acc.state = entity.state
            acc.district = entity.district
            acc.city = entity.city
            acc.emailid = entity.email
            acc.accountdate = cls._first_fin_start_date(entity)
            acc.partytype = "Other"
            acc.approved = True
            acc.isactive = True
            acc.canbedeleted = False
            if actor and not acc.createdby_id:
                acc.createdby = actor
            acc.save()
            sync_ledger_for_account(acc, ledger_overrides={"is_system": False, "is_party": True})
            count += 1
        return count

    @staticmethod
    def _next_account_code(entity):
        last_code = (
            account.objects.filter(entity=entity)
            .order_by("-accountcode")
            .values_list("accountcode", flat=True)
            .first()
        )
        return (last_code or 0) + 1

    @staticmethod
    def _first_fin_start_date(entity):
        return (
            entity.fy.order_by("finstartyear")
            .values_list("finstartyear", flat=True)
            .first()
        )
