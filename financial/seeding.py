from decimal import Decimal

from django.db import transaction
from entity.models import EntityConstitutionV2
from financial.models import Credit, Debit, FinancialSettings, Ledger, account, accountHead, accounttype
from financial.seed_catalogs import FINANCIAL_TEMPLATES
from financial.services import (
    allocate_next_ledger_code,
    apply_normalized_profile_payload,
    create_account_with_synced_ledger,
    get_or_create_financial_settings,
    sync_ledger_for_account,
)


class FinancialSeedService:
    """
    Entity bootstrap seeding for the financial domain.

    This is intentionally service-driven and idempotent. It preserves the
    account/account head codes already relied on elsewhere in the project while
    also keeping the additive Ledger foundation synchronized.
    """

    DEFAULT_TEMPLATE = "indian_accounting_final"

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

    @classmethod
    @transaction.atomic
    def reconcile_entity(cls, *, entity, actor=None, template_code=None):
        template_code = template_code or cls.DEFAULT_TEMPLATE
        summary = cls.seed_entity(entity=entity, actor=actor, template_code=template_code)
        template = FINANCIAL_TEMPLATES[template_code]
        head_map = {row["code"]: accountHead.objects.get(entity=entity, code=row["code"]) for row in template["account_heads"]}
        defaults_by_code = {row["code"]: row for row in template["default_accounts"]}

        corrected_default_ledgers = 0
        corrected_party_ledgers = 0
        corrected_head_types = 0

        for ledger in Ledger.objects.filter(entity=entity).select_related("accounthead", "accounttype", "account_profile", "account_profile__commercial_profile"):
            target_head = None
            target_credit_head = None
            target_name = None
            target_is_system = ledger.is_system
            target_is_party = ledger.is_party

            if ledger.ledger_code in defaults_by_code:
                row = defaults_by_code[ledger.ledger_code]
                target_head = head_map[row["head_code"]]
                target_credit_head = head_map.get(row.get("credit_head_code")) or target_head
                target_name = row["name"]
                target_is_system = True
                target_is_party = row.get("party_type") in {"Customer", "Vendor", "Both", "Bank", "Employee", "Government"}
            elif getattr(ledger, "account_profile", None):
                partytype = getattr(getattr(ledger.account_profile, "commercial_profile", None), "partytype", None)
                target_head = cls._infer_party_head(head_map=head_map, partytype=partytype, current_head_id=ledger.accounthead_id)
                target_credit_head = target_head or ledger.creditaccounthead
                target_is_party = True

            changed = False
            if target_head and ledger.accounthead_id != target_head.id:
                ledger.accounthead = target_head
                changed = True
            if target_credit_head and ledger.creditaccounthead_id != target_credit_head.id:
                ledger.creditaccounthead = target_credit_head
                changed = True
            if target_head and ledger.accounttype_id != target_head.accounttype_id:
                ledger.accounttype = target_head.accounttype
                changed = True
            if target_name and ledger.name != target_name:
                ledger.name = target_name
                if not ledger.legal_name:
                    ledger.legal_name = target_name
                changed = True
            if ledger.is_system != target_is_system:
                ledger.is_system = target_is_system
                changed = True
            if ledger.is_party != target_is_party:
                ledger.is_party = target_is_party
                changed = True

            if changed:
                ledger.save()
                if ledger.ledger_code in defaults_by_code:
                    corrected_default_ledgers += 1
                else:
                    corrected_party_ledgers += 1

            account_profile = getattr(ledger, "account_profile", None)
            if account_profile and account_profile.accountname != ledger.name:
                account_profile.accountname = ledger.name
                if not account_profile.legalname:
                    account_profile.legalname = ledger.legal_name or ledger.name
                account_profile.save(update_fields=["accountname", "legalname"])

        summary.update(
            {
                "corrected_default_ledgers": corrected_default_ledgers,
                "corrected_party_ledgers": corrected_party_ledgers,
                "corrected_head_types": corrected_head_types,
            }
        )
        return summary

    @staticmethod
    def _bool_balance(normal_balance):
        return normal_balance == Debit

    @classmethod
    def _seed_account_types(cls, *, entity, actor, rows):
        type_map = {}
        for row in rows:
            acc_type = (
                accounttype.objects.filter(entity=entity, accounttypecode=row["code"]).first()
                or accounttype.objects.filter(entity=entity, accounttypename=row["name"]).first()
            )
            if acc_type is None:
                acc_type = accounttype.objects.create(
                    entity=entity,
                    accounttypecode=row["code"],
                    accounttypename=row["name"],
                    balanceType=cls._bool_balance(row["normal_balance"]),
                    createdby=actor,
                )
            acc_type.accounttypename = row["name"]
            acc_type.accounttypecode = row["code"]
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
            acc = account.objects.filter(entity=entity, ledger__ledger_code=row["code"]).first()
            if acc is None:
                acc = create_account_with_synced_ledger(
                    account_data={
                        "entity": entity,
                        "accountname": row["name"],
                        "legalname": row["name"],
                        "isactive": True,
                        "canbedeleted": False,
                        "createdby": actor,
                    },
                    ledger_overrides={
                        "ledger_code": row["code"],
                        "name": row["name"],
                        "legal_name": row["name"],
                        "accounthead": head,
                        "creditaccounthead": credit_head,
                        "accounttype": head.accounttype,
                        "openingbcr": Decimal("0.00"),
                        "openingbdr": Decimal("0.00"),
                        "is_system": True,
                        "is_party": row.get("party_type") in {"Customer", "Vendor", "Bank", "Government"},
                    },
                )
            acc.accountname = row["name"]
            acc.legalname = row["name"]
            acc.isactive = True
            acc.canbedeleted = False
            if actor and not acc.createdby_id:
                acc.createdby = actor
            acc.save()
            apply_normalized_profile_payload(
                acc,
                commercial_data={
                    "partytype": row.get("party_type") or "Other",
                    "approved": True,
                },
                createdby=actor,
            )
            sync_ledger_for_account(
                acc,
                ledger_overrides={
                    "ledger_code": row["code"],
                    "name": row["name"],
                    "legal_name": row["name"],
                    "accounthead": head,
                    "creditaccounthead": credit_head,
                    "accounttype": head.accounttype,
                    "openingbcr": Decimal("0.00"),
                    "openingbdr": Decimal("0.00"),
                    "is_system": True,
                    "is_party": row.get("party_type") in {"Customer", "Vendor", "Bank", "Government"},
                },
            )
            created_or_updated.append(acc.id)
        return created_or_updated

    @classmethod
    def _seed_constitution_accounts(cls, *, entity, actor, head_map):
        constitution_v2 = entity.constitutions_v2.filter(isactive=True).order_by("id").first()
        const_code = (getattr(constitution_v2, "constitution_code", None) or "").strip()
        if const_code == "01":
            head_code = 6200
        elif const_code == "02":
            head_code = 6300
        else:
            return 0

        head = head_map.get(head_code)
        if not head:
            return 0

        primary_address = (
            entity.addresses.filter(isactive=True, is_primary=True)
            .select_related("country", "state", "district", "city")
            .first()
        )
        primary_contact = entity.contacts.filter(isactive=True, is_primary=True).first()
        count = 0
        for detail in EntityConstitutionV2.objects.filter(entity=entity, isactive=True).order_by("id"):
            existing = account.objects.filter(
                entity=entity,
                ledger__accounthead=head,
                accountname=detail.shareholder,
                compliance_profile__pan=detail.pan,
            ).first()
            if existing:
                acc = existing
            else:
                next_code = cls._next_account_code(entity)
                acc = create_account_with_synced_ledger(
                    account_data={
                        "entity": entity,
                        "accountname": detail.shareholder,
                        "legalname": detail.shareholder,
                        "accountdate": cls._first_fin_start_date(entity),
                        "isactive": True,
                        "canbedeleted": False,
                        "createdby": actor,
                    },
                    ledger_overrides={
                        "ledger_code": next_code,
                        "name": detail.shareholder,
                        "legal_name": detail.shareholder,
                        "accounthead": head,
                        "creditaccounthead": head,
                        "accounttype": head.accounttype,
                        "openingbcr": Decimal("0.00"),
                        "openingbdr": Decimal("0.00"),
                        "is_party": True,
                    },
                )
            acc.accountname = detail.shareholder
            acc.legalname = detail.shareholder
            acc.accountdate = cls._first_fin_start_date(entity)
            acc.isactive = True
            acc.canbedeleted = False
            if actor and not acc.createdby_id:
                acc.createdby = actor
            acc.save()
            apply_normalized_profile_payload(
                acc,
                compliance_data={
                    "pan": detail.pan,
                },
                commercial_data={
                    "partytype": "Other",
                    "approved": True,
                    "agent": None,
                },
                primary_address_data={
                    "country_id": primary_address.country_id if primary_address else None,
                    "state_id": primary_address.state_id if primary_address else None,
                    "district_id": primary_address.district_id if primary_address else None,
                    "city_id": primary_address.city_id if primary_address else None,
                },
                primary_contact_data={
                    "emailid": primary_contact.email if primary_contact else None,
                },
                createdby=actor,
            )
            ledger_code = acc.effective_accounting_code or cls._next_account_code(entity)
            sync_ledger_for_account(
                acc,
                ledger_overrides={
                    "ledger_code": ledger_code,
                    "name": detail.shareholder,
                    "legal_name": detail.shareholder,
                    "accounthead": head,
                    "creditaccounthead": head,
                    "accounttype": head.accounttype,
                    "openingbcr": Decimal("0.00"),
                    "openingbdr": Decimal("0.00"),
                    "is_system": False,
                    "is_party": True,
                },
            )
            count += 1
        return count

    @staticmethod
    def _next_account_code(entity):
        return allocate_next_ledger_code(entity_id=entity.id)

    @staticmethod
    def _first_fin_start_date(entity):
        return (
            entity.fy.order_by("finstartyear")
            .values_list("finstartyear", flat=True)
            .first()
        )

    @staticmethod
    def _infer_party_head(*, head_map, partytype, current_head_id):
        current_head = head_map.get(current_head_id)
        if current_head:
            return current_head

        mapping = {
            "Customer": 8000,
            "Vendor": 7000,
            "Both": 8000,
            "Bank": 2000,
            "Employee": 6100,
            "Government": 5300,
        }
        head_code = mapping.get(partytype or "", None)
        return head_map.get(head_code)
