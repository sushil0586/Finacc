from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from entity.models import Entity
from financial.models import account
from financial.services import create_account_with_synced_ledger, sync_ledger_for_account
from posting.common.static_accounts import StaticAccountCodes
from posting.models import EntityStaticAccountMap, StaticAccount, StaticAccountGroup
from posting.services.static_accounts import StaticAccountService


@dataclass(frozen=True)
class StaticSeedDef:
    code: str
    name: str
    group: str
    description: str
    is_required: bool
    default_account_name: str


STATIC_SEED_DEFS: tuple[StaticSeedDef, ...] = (
    StaticSeedDef(
        code=StaticAccountCodes.PURCHASE_DEFAULT,
        name="Purchase Default",
        group=StaticAccountGroup.PURCHASE,
        description="Fallback purchase base account when a product/account line has no dedicated purchase account.",
        is_required=False,
        default_account_name="Purchase Default",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.PURCHASE_MISC_EXPENSE,
        name="Purchase Misc Expense",
        group=StaticAccountGroup.PURCHASE,
        description="Fallback expense ledger for purchase charges and misc adjustments.",
        is_required=True,
        default_account_name="Purchase Misc Expense",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.SALES_DEFAULT,
        name="Sales Default",
        group=StaticAccountGroup.SALES,
        description="Fallback sales revenue account when an item has no dedicated revenue account.",
        is_required=False,
        default_account_name="Sales Default",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.SALES_REVENUE,
        name="Sales Revenue",
        group=StaticAccountGroup.SALES,
        description="Default revenue ledger for sales posting.",
        is_required=False,
        default_account_name="Sales Revenue",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.SALES_OTHER_CHARGES_INCOME,
        name="Sales Other Charges Income",
        group=StaticAccountGroup.SALES,
        description="Income ledger for sales invoice other charges.",
        is_required=False,
        default_account_name="Sales Other Charges Income",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.SALES_MISC_EXPENSE,
        name="Sales Misc Expense",
        group=StaticAccountGroup.SALES,
        description="Fallback sales-side expense ledger.",
        is_required=False,
        default_account_name="Sales Misc Expense",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.ITC_BLOCKED_EXPENSE,
        name="ITC Blocked Expense",
        group=StaticAccountGroup.GST_INPUT,
        description="Expense ledger for GST that is not claimable as ITC.",
        is_required=False,
        default_account_name="Blocked ITC Expense",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.ROUND_OFF_INCOME,
        name="Round Off Income",
        group=StaticAccountGroup.ROUND_OFF,
        description="Round-off gain ledger.",
        is_required=True,
        default_account_name="Round Off Income",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.ROUND_OFF_EXPENSE,
        name="Round Off Expense",
        group=StaticAccountGroup.ROUND_OFF,
        description="Round-off loss ledger.",
        is_required=True,
        default_account_name="Round Off Expense",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.INPUT_CGST,
        name="Input CGST",
        group=StaticAccountGroup.GST_INPUT,
        description="Input tax ledger for claimable CGST.",
        is_required=False,
        default_account_name="Input CGST",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.INPUT_SGST,
        name="Input SGST",
        group=StaticAccountGroup.GST_INPUT,
        description="Input tax ledger for claimable SGST.",
        is_required=False,
        default_account_name="Input SGST",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.INPUT_IGST,
        name="Input IGST",
        group=StaticAccountGroup.GST_INPUT,
        description="Input tax ledger for claimable IGST.",
        is_required=False,
        default_account_name="Input IGST",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.INPUT_CESS,
        name="Input CESS",
        group=StaticAccountGroup.GST_INPUT,
        description="Input tax ledger for claimable cess.",
        is_required=False,
        default_account_name="Input CESS",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.OUTPUT_CGST,
        name="Output CGST",
        group=StaticAccountGroup.GST_OUTPUT,
        description="Output tax liability ledger for CGST.",
        is_required=False,
        default_account_name="Output CGST",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.OUTPUT_SGST,
        name="Output SGST",
        group=StaticAccountGroup.GST_OUTPUT,
        description="Output tax liability ledger for SGST.",
        is_required=False,
        default_account_name="Output SGST",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.OUTPUT_IGST,
        name="Output IGST",
        group=StaticAccountGroup.GST_OUTPUT,
        description="Output tax liability ledger for IGST.",
        is_required=False,
        default_account_name="Output IGST",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.OUTPUT_CESS,
        name="Output CESS",
        group=StaticAccountGroup.GST_OUTPUT,
        description="Output tax liability ledger for cess.",
        is_required=False,
        default_account_name="Output CESS",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.RCM_CGST_PAYABLE,
        name="RCM CGST Payable",
        group=StaticAccountGroup.RCM_PAYABLE,
        description="Reverse-charge liability ledger for CGST.",
        is_required=False,
        default_account_name="RCM CGST Payable",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.RCM_SGST_PAYABLE,
        name="RCM SGST Payable",
        group=StaticAccountGroup.RCM_PAYABLE,
        description="Reverse-charge liability ledger for SGST.",
        is_required=False,
        default_account_name="RCM SGST Payable",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.RCM_IGST_PAYABLE,
        name="RCM IGST Payable",
        group=StaticAccountGroup.RCM_PAYABLE,
        description="Reverse-charge liability ledger for IGST.",
        is_required=False,
        default_account_name="RCM IGST Payable",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.RCM_CESS_PAYABLE,
        name="RCM CESS Payable",
        group=StaticAccountGroup.RCM_PAYABLE,
        description="Reverse-charge liability ledger for cess.",
        is_required=False,
        default_account_name="RCM CESS Payable",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.TDS_PAYABLE,
        name="TDS Payable",
        group=StaticAccountGroup.TDS,
        description="Liability ledger for income-tax TDS payable.",
        is_required=False,
        default_account_name="TDS Payable",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.GST_TDS_PAYABLE,
        name="GST TDS Payable",
        group=StaticAccountGroup.TDS,
        description="Liability ledger for GST-TDS payable.",
        is_required=False,
        default_account_name="GST TDS Payable",
    ),
    StaticSeedDef(
        code=StaticAccountCodes.TCS_PAYABLE,
        name="TCS Payable",
        group=StaticAccountGroup.TCS,
        description="Liability ledger for TCS payable.",
        is_required=False,
        default_account_name="TCS Payable",
    ),
)


class Command(BaseCommand):
    help = (
        "Bootstrap posting static accounts for an entity: seed StaticAccount master, "
        "create default system ledgers/accounts when missing, and map important codes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, required=True, help="Entity id to bootstrap.")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write changes. Without this flag the command runs in dry-run mode.",
        )
        parser.add_argument(
            "--include-sales",
            action="store_true",
            help="Also create/map sales-side static accounts in the same run.",
        )
        parser.add_argument(
            "--subentity-id",
            type=int,
            help="Optional subentity scope for mappings. Defaults to entity-level mappings.",
        )

    def handle(self, *args, **options):
        entity_id = options["entity_id"]
        apply_changes = bool(options["apply"])
        include_sales = bool(options["include_sales"])
        subentity_id = options.get("subentity_id")

        entity = Entity.objects.filter(id=entity_id).first()
        if not entity:
            raise CommandError(f"Entity not found: {entity_id}")

        defs = self._selected_defs(include_sales=include_sales)

        self.stdout.write(self.style.MIGRATE_HEADING("Bootstrapping static account master..."))
        master_summary = self._seed_static_master(defs=defs, apply_changes=apply_changes)
        self.stdout.write(
            f"StaticAccount master: created={master_summary['created']}, updated={master_summary['updated']}"
        )

        self.stdout.write(self.style.MIGRATE_HEADING("Preparing entity mappings..."))
        mapping_summary = self._bootstrap_entity(
            entity=entity,
            defs=defs,
            subentity_id=subentity_id,
            apply_changes=apply_changes,
        )

        mode_label = "APPLIED" if apply_changes else "DRY-RUN"
        self.stdout.write(self.style.SUCCESS(f"{mode_label} complete for entity {entity_id}."))
        self.stdout.write(
            f"Accounts created={mapping_summary['accounts_created']}, "
            f"ledgers linked/created={mapping_summary['ledgers_ready']}, "
            f"mappings created={mapping_summary['mappings_created']}, "
            f"mappings repaired={mapping_summary['mappings_repaired']}"
        )

        if mapping_summary["created_or_repaired"]:
            self.stdout.write("Touched codes:")
            for code in mapping_summary["created_or_repaired"]:
                self.stdout.write(f"  - {code}")
        else:
            self.stdout.write("No new mappings were needed; entity already had the selected codes.")

    def _selected_defs(self, *, include_sales: bool) -> tuple[StaticSeedDef, ...]:
        if include_sales:
            return STATIC_SEED_DEFS
        sales_codes = {
            StaticAccountCodes.SALES_DEFAULT,
            StaticAccountCodes.SALES_REVENUE,
            StaticAccountCodes.SALES_OTHER_CHARGES_INCOME,
            StaticAccountCodes.SALES_MISC_EXPENSE,
            StaticAccountCodes.OUTPUT_CGST,
            StaticAccountCodes.OUTPUT_SGST,
            StaticAccountCodes.OUTPUT_IGST,
            StaticAccountCodes.OUTPUT_CESS,
            StaticAccountCodes.TCS_PAYABLE,
        }
        return tuple(item for item in STATIC_SEED_DEFS if item.code not in sales_codes)

    @transaction.atomic
    def _seed_static_master(self, *, defs: Iterable[StaticSeedDef], apply_changes: bool) -> Dict[str, int]:
        created = 0
        updated = 0
        for item in defs:
            existing = StaticAccount.objects.filter(code=item.code).first()
            if existing is None:
                created += 1
                self.stdout.write(f"  + master {item.code}")
                if apply_changes:
                    StaticAccount.objects.create(
                        code=item.code,
                        name=item.name,
                        group=item.group,
                        is_required=item.is_required,
                        is_active=True,
                        description=item.description,
                    )
                continue

            changed = (
                existing.name != item.name
                or existing.group != item.group
                or bool(existing.is_required) != bool(item.is_required)
                or (existing.description or "") != item.description
            )
            if changed:
                updated += 1
                self.stdout.write(f"  ~ master {item.code}")
                if apply_changes:
                    existing.name = item.name
                    existing.group = item.group
                    existing.is_required = item.is_required
                    existing.description = item.description
                    existing.is_active = True
                    existing.save(update_fields=["name", "group", "is_required", "description", "is_active"])
        return {"created": created, "updated": updated}

    @transaction.atomic
    def _bootstrap_entity(
        self,
        *,
        entity: Entity,
        defs: Iterable[StaticSeedDef],
        subentity_id: Optional[int],
        apply_changes: bool,
    ) -> Dict[str, object]:
        account_by_name = {
            (acc.accountname or "").strip().lower(): acc
            for acc in account.objects.filter(entity=entity).select_related("ledger")
        }
        static_by_code = {
            row.code: row
            for row in StaticAccount.objects.filter(code__in=[item.code for item in defs])
        }
        existing_maps = {
            row.static_account.code: row
            for row in EntityStaticAccountMap.objects.filter(
                entity=entity,
                sub_entity_id=subentity_id,
                is_active=True,
                static_account__code__in=list(static_by_code.keys()),
            ).select_related("static_account", "account", "ledger")
        }

        accounts_created = 0
        ledgers_ready = 0
        mappings_created = 0
        mappings_repaired = 0
        touched_codes: list[str] = []

        for item in defs:
            existing_map = existing_maps.get(item.code)
            acc = existing_map.account if existing_map and existing_map.account_id else None
            if acc is None:
                acc = account_by_name.get(item.default_account_name.strip().lower())
            if acc is None:
                self.stdout.write(f"  + account/ledger {item.default_account_name} for {item.code}")
                accounts_created += 1
                ledgers_ready += 1
                touched_codes.append(item.code)
                if apply_changes:
                    acc = create_account_with_synced_ledger(
                        account_data={
                            "entity": entity,
                            "accountname": item.default_account_name,
                            "legalname": item.default_account_name,
                            "canbedeleted": False,
                            "isactive": True,
                            "createdby": None,
                        },
                        ledger_overrides={
                            "name": item.default_account_name,
                            "legal_name": item.default_account_name,
                            "is_party": False,
                            "is_system": True,
                            "canbedeleted": False,
                            "createdby": None,
                        },
                    )
                    account_by_name[item.default_account_name.strip().lower()] = acc
            elif not acc.ledger_id:
                self.stdout.write(f"  ~ attach ledger to existing account {acc.accountname} for {item.code}")
                ledgers_ready += 1
                touched_codes.append(item.code)
                if apply_changes:
                    sync_ledger_for_account(
                        acc,
                        ledger_overrides={
                            "name": acc.accountname or item.default_account_name,
                            "legal_name": acc.legalname or acc.accountname or item.default_account_name,
                            "is_party": False,
                            "is_system": True,
                            "canbedeleted": False,
                            "createdby": acc.createdby,
                        },
                    )

            ledger_id = getattr(acc, "ledger_id", None) if acc else None
            account_id = getattr(acc, "id", None) if acc else None
            needs_new_mapping = existing_map is None
            needs_repair = (
                existing_map is not None
                and (
                    existing_map.account_id != account_id
                    or existing_map.ledger_id != ledger_id
                )
            )

            if needs_new_mapping:
                mappings_created += 1
                touched_codes.append(item.code)
                self.stdout.write(
                    f"  + map {item.code} -> {item.default_account_name}"
                )
                if apply_changes and acc:
                    EntityStaticAccountMap.objects.create(
                        entity=entity,
                        sub_entity_id=subentity_id,
                        static_account=static_by_code[item.code],
                        account_id=account_id,
                        ledger_id=ledger_id,
                        is_active=True,
                    )
            elif needs_repair:
                mappings_repaired += 1
                touched_codes.append(item.code)
                self.stdout.write(
                    f"  ~ repair map {item.code} -> {item.default_account_name}"
                )
                if apply_changes and acc:
                    existing_map.account_id = account_id
                    existing_map.ledger_id = ledger_id
                    existing_map.is_active = True
                    existing_map.save(update_fields=["account", "ledger", "is_active", "updated_at"])

        if apply_changes:
            StaticAccountService.invalidate(entity.id)

        return {
            "accounts_created": accounts_created,
            "ledgers_ready": ledgers_ready,
            "mappings_created": mappings_created,
            "mappings_repaired": mappings_repaired,
            "created_or_repaired": sorted(set(touched_codes)),
        }
