from decimal import Decimal

from django.db import transaction
from entity.models import EntityConstitutionV2
from financial.governance import LEDGER_ONLY, PARTY_MANAGED, resolve_management_mode
from financial.models import (
    Credit,
    Debit,
    FinancialCodeSeries,
    FinancialMasterRule,
    FinancialSettings,
    Ledger,
    account,
    accountHead,
    accounttype,
)
from financial.party_accounting_defaults import resolve_party_accounting_from_maps
from financial.seed_catalogs import FINANCIAL_TEMPLATES
from financial.services import (
    allocate_next_ledger_code,
    apply_normalized_profile_payload,
    create_account_with_synced_ledger,
    ensure_account_profile_for_ledger,
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
        governance_rule_count = cls._seed_governance_rules(
            entity=entity,
            actor=actor,
            rows=template.get("governance_rules", []),
            type_map=type_map,
            head_map=head_map,
        )
        code_series_count = cls._seed_code_series(
            entity=entity,
            actor=actor,
            rows=template.get("code_series", []),
            type_map=type_map,
            head_map=head_map,
        )
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
            "governance_rule_count": governance_rule_count,
            "code_series_count": code_series_count,
            "default_account_count": len(account_rows),
            "constitution_account_count": constitution_rows,
        }

    @classmethod
    @transaction.atomic
    def reconcile_entity(cls, *, entity, actor=None, template_code=None, dry_run=False, include_rows=False, row_limit=50):
        template_code = template_code or cls.DEFAULT_TEMPLATE
        summary = cls.seed_entity(entity=entity, actor=actor, template_code=template_code)
        template = FINANCIAL_TEMPLATES[template_code]
        head_map = {row["code"]: accountHead.objects.get(entity=entity, code=row["code"]) for row in template["account_heads"]}
        defaults_by_code = {row["code"]: row for row in template["default_accounts"]}

        corrected_default_ledgers = 0
        corrected_party_ledgers = 0
        corrected_head_types = 0
        repaired_missing_codes = 0
        repaired_missing_account_links = 0
        touched_rows = []
        touched_row_count = 0

        for ledger in Ledger.objects.filter(entity=entity).select_related("accounthead", "accounttype", "account_profile", "account_profile__commercial_profile"):
            target_head = None
            target_credit_head = None
            target_name = None
            target_partytype = None
            target_is_system = ledger.is_system
            target_is_party = ledger.is_party
            change_reasons = []

            if ledger.ledger_code in defaults_by_code:
                row = defaults_by_code[ledger.ledger_code]
                target_partytype = row.get("party_type")
                target_head = head_map[row["head_code"]]
                target_credit_head = head_map.get(row.get("credit_head_code")) or target_head
                target_name = row["name"]
                target_is_system = True
                target_is_party = cls._is_party_managed(
                    entity=entity,
                    partytype=target_partytype,
                    account_type_id=target_head.accounttype_id if target_head else None,
                    debit_head_id=target_head.id if target_head else None,
                    credit_head_id=target_credit_head.id if target_credit_head else None,
                    fallback=ledger.is_party,
                )
            elif getattr(ledger, "account_profile", None):
                target_partytype = getattr(getattr(ledger.account_profile, "commercial_profile", None), "partytype", None)
                party_defaults = resolve_party_accounting_from_maps(type_map={}, head_map=head_map, partytype=target_partytype)
                target_head = party_defaults.get("accounthead") or cls._infer_party_head(
                    head_map=head_map,
                    partytype=target_partytype,
                    current_head_id=ledger.accounthead_id,
                )
                target_credit_head = party_defaults.get("creditaccounthead") or target_head or ledger.creditaccounthead
                target_is_party = cls._is_party_managed(
                    entity=entity,
                    partytype=target_partytype,
                    account_type_id=getattr(target_head, "accounttype_id", None),
                    debit_head_id=getattr(target_head, "id", None),
                    credit_head_id=getattr(target_credit_head, "id", None),
                    fallback=True,
                )
            else:
                target_head = ledger.accounthead
                target_credit_head = ledger.creditaccounthead or ledger.accounthead
                target_is_party = cls._is_party_managed(
                    entity=entity,
                    partytype=None,
                    account_type_id=ledger.accounttype_id or getattr(target_head, "accounttype_id", None),
                    debit_head_id=getattr(target_head, "id", None),
                    credit_head_id=getattr(target_credit_head, "id", None),
                    fallback=ledger.is_party,
                )

            changed = False
            if target_head and ledger.accounthead_id != target_head.id:
                ledger.accounthead = target_head
                changed = True
                change_reasons.append("debit_head")
            if target_credit_head and ledger.creditaccounthead_id != target_credit_head.id:
                ledger.creditaccounthead = target_credit_head
                changed = True
                change_reasons.append("credit_head")
            if target_head and ledger.accounttype_id != target_head.accounttype_id:
                ledger.accounttype = target_head.accounttype
                changed = True
                change_reasons.append("account_type")
            if ledger.ledger_code is None:
                ledger.ledger_code = allocate_next_ledger_code(
                    entity_id=entity.id,
                    partytype=target_partytype,
                    account_type_id=getattr(target_head, "accounttype_id", None) or ledger.accounttype_id,
                    debit_head_id=getattr(target_head, "id", None) or ledger.accounthead_id,
                    credit_head_id=getattr(target_credit_head, "id", None) or ledger.creditaccounthead_id,
                    allocated_by=actor,
                    ledger=ledger,
                    allocation_reason="repair",
                )
                repaired_missing_codes += 1
                changed = True
                change_reasons.append("ledger_code")
            if target_name and ledger.name != target_name:
                ledger.name = target_name
                if not ledger.legal_name:
                    ledger.legal_name = target_name
                changed = True
                change_reasons.append("name")
            if ledger.is_system != target_is_system:
                ledger.is_system = target_is_system
                changed = True
                change_reasons.append("is_system")
            if ledger.is_party != target_is_party:
                ledger.is_party = target_is_party
                changed = True
                change_reasons.append("is_party")

            if changed:
                ledger.save()
                if ledger.ledger_code in defaults_by_code:
                    corrected_default_ledgers += 1
                else:
                    corrected_party_ledgers += 1

            if target_is_party and not getattr(ledger, "account_profile", None):
                ensure_account_profile_for_ledger(ledger=ledger, createdby=actor)
                repaired_missing_account_links += 1
                change_reasons.append("account_profile")

            account_profile = getattr(ledger, "account_profile", None)
            if account_profile and account_profile.accountname != ledger.name:
                account_profile.accountname = ledger.name
                if not account_profile.legalname:
                    account_profile.legalname = ledger.legal_name or ledger.name
                account_profile.save(update_fields=["accountname", "legalname"])
                change_reasons.append("account_profile_name")

            if change_reasons and include_rows and len(touched_rows) < row_limit:
                touched_row_count += 1
                touched_rows.append(
                    {
                        "ledger_id": ledger.id,
                        "ledger_code": ledger.ledger_code,
                        "ledger_name": ledger.name,
                        "management_mode": "party_managed" if target_is_party else "ledger_only",
                        "changes": sorted(set(change_reasons)),
                    }
                )
            elif change_reasons:
                touched_row_count += 1

        summary.update(
            {
                "corrected_default_ledgers": corrected_default_ledgers,
                "corrected_party_ledgers": corrected_party_ledgers,
                "corrected_head_types": corrected_head_types,
                "repaired_missing_codes": repaired_missing_codes,
                "repaired_missing_account_links": repaired_missing_account_links,
            }
        )
        if include_rows:
            summary["touched_rows"] = touched_rows
            summary["touched_row_count"] = touched_row_count
            summary["touched_rows_truncated"] = max(0, touched_row_count - len(touched_rows))
        if dry_run:
            transaction.set_rollback(True)
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
            acc_type.isactive = True
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
                        "is_party": cls._is_party_managed(
                            entity=entity,
                            partytype=row.get("party_type"),
                            account_type_id=head.accounttype_id,
                            debit_head_id=head.id,
                            credit_head_id=credit_head.id if credit_head else None,
                            fallback=False,
                        ),
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
                    "is_party": cls._is_party_managed(
                        entity=entity,
                        partytype=row.get("party_type"),
                        account_type_id=head.accounttype_id,
                        debit_head_id=head.id,
                        credit_head_id=credit_head.id if credit_head else None,
                        fallback=False,
                    ),
                },
            )
            created_or_updated.append(acc.id)
        return created_or_updated

    @classmethod
    def _seed_governance_rules(cls, *, entity, actor, rows, type_map, head_map):
        created_or_updated = 0
        for row in rows:
            defaults = {
                "management_mode": row["management_mode"],
                "account_type": type_map.get(row.get("account_type_code")) if row.get("account_type_code") else None,
                "debit_head": head_map.get(row.get("debit_head_code")) if row.get("debit_head_code") else None,
                "credit_head": head_map.get(row.get("credit_head_code")) if row.get("credit_head_code") else None,
                "suggested_account_type": type_map.get(row.get("suggested_account_type_code"))
                if row.get("suggested_account_type_code")
                else None,
                "suggested_debit_head": head_map.get(row.get("suggested_debit_head_code"))
                if row.get("suggested_debit_head_code")
                else None,
                "suggested_credit_head": head_map.get(row.get("suggested_credit_head_code"))
                if row.get("suggested_credit_head_code")
                else None,
                "auto_create_account": row.get("auto_create_account", False),
                "allow_direct_ledger_edit": row.get("allow_direct_ledger_edit", True),
                "createdby": actor,
            }
            rule, _created = FinancialMasterRule.objects.get_or_create(
                entity=entity,
                party_type=row.get("party_type"),
                priority=row.get("priority", 100),
                defaults=defaults,
            )
            for field, value in defaults.items():
                setattr(rule, field, value)
            rule.isactive = True
            if actor and not rule.createdby_id:
                rule.createdby = actor
            rule.save()
            created_or_updated += 1
        return created_or_updated

    @classmethod
    def _seed_code_series(cls, *, entity, actor, rows, type_map, head_map):
        created_or_updated = 0
        for row in rows:
            defaults = {
                "label": row["label"],
                "account_type": type_map.get(row.get("account_type_code")) if row.get("account_type_code") else None,
                "debit_head": head_map.get(row.get("debit_head_code")) if row.get("debit_head_code") else None,
                "credit_head": head_map.get(row.get("credit_head_code")) if row.get("credit_head_code") else None,
                "party_type": row.get("party_type"),
                "range_start": row["range_start"],
                "range_end": row["range_end"],
                "next_code": row["next_code"],
                "increment_step": row.get("increment_step", 1),
                "is_reserved_anchor": row.get("is_reserved_anchor", False),
                "priority": row.get("priority", 100),
                "createdby": actor,
            }
            series, _created = FinancialCodeSeries.objects.get_or_create(
                entity=entity,
                series_key=row["series_key"],
                defaults=defaults,
            )
            preserved_next_code = max(series.next_code or defaults["next_code"], defaults["next_code"])
            for field, value in defaults.items():
                setattr(series, field, value)
            series.next_code = preserved_next_code
            series.isactive = True
            if actor and not series.createdby_id:
                series.createdby = actor
            series.save()
            created_or_updated += 1
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
    def _is_party_managed(*, entity, partytype, account_type_id=None, debit_head_id=None, credit_head_id=None, fallback=False):
        resolved_mode = resolve_management_mode(
            entity=entity,
            partytype=partytype,
            account_type_id=account_type_id,
            debit_head_id=debit_head_id,
            credit_head_id=credit_head_id,
            fallback=None,
        )
        if resolved_mode == PARTY_MANAGED:
            return True
        if resolved_mode == LEDGER_ONLY:
            return False

        account_type_obj = accounttype.objects.filter(pk=account_type_id).only("accounttypename", "accounttypecode").first() if account_type_id else None
        debit_head_obj = accountHead.objects.select_related("accounttype").filter(pk=debit_head_id).first() if debit_head_id else None
        credit_head_obj = (
            accountHead.objects.select_related("accounttype").filter(pk=credit_head_id).first() if credit_head_id else None
        )

        def _is_party_account_type(obj):
            if not obj:
                return False
            return (
                str(getattr(obj, "accounttypename", "") or "").strip().lower() == "party"
                or str(getattr(obj, "accounttypecode", "") or "").strip() == "1009"
            )

        if _is_party_account_type(account_type_obj):
            return True
        if _is_party_account_type(getattr(debit_head_obj, "accounttype", None)):
            return True
        if _is_party_account_type(getattr(credit_head_obj, "accounttype", None)):
            return True
        return bool(fallback)

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

        return resolve_party_accounting_from_maps(type_map={}, head_map=head_map, partytype=partytype).get("accounthead")
