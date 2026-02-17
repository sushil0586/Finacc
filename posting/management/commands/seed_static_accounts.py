# posting/management/commands/seed_static_accounts.py
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from posting.models import StaticAccount, EntityStaticAccountMap

# ✅ Adjust these imports if your project differs:
from entity.models import Entity
from financial.models import account as Account  # ledger table is "account"


@dataclass(frozen=True)
class StaticDef:
    code: str
    name: str
    group: str
    description: str = ""


# ------------------------------
# 1) Global master list (stable)
# ------------------------------
STATIC_MASTER: List[StaticDef] = [
    # Cash/Bank
    StaticDef("CASH", "Cash-in-hand", "CASH_BANK", "Default cash account"),
    StaticDef("BANK_MAIN", "Main Bank Account", "CASH_BANK", "Default bank account (optional)"),

    # Rounding
    StaticDef("ROUND_OFF_INCOME", "Round-off Income", "ROUNDING", "Used when roundoff decreases payable/receivable"),
    StaticDef("ROUND_OFF_EXPENSE", "Round-off Expense", "ROUNDING", "Used when roundoff increases payable/receivable"),

    # Purchase
    StaticDef("PURCHASE_MISC_EXPENSE", "Purchase Misc Expense", "PURCHASE", "Fallback for purchase expenses/other charges"),
    StaticDef("PURCHASE_DISCOUNT", "Purchase Discount", "PURCHASE", "Discount received/allowed on purchase (optional)"),

    # Input GST
    StaticDef("INPUT_IGST", "Input IGST", "GST_INPUT", "ITC ledger - IGST"),
    StaticDef("INPUT_CGST", "Input CGST", "GST_INPUT", "ITC ledger - CGST"),
    StaticDef("INPUT_SGST", "Input SGST", "GST_INPUT", "ITC ledger - SGST"),
    StaticDef("INPUT_CESS", "Input CESS", "GST_INPUT", "ITC ledger - CESS"),

    # Output GST (future, but seed now)
    StaticDef("OUTPUT_IGST", "Output IGST", "GST_OUTPUT", "GST liability - IGST"),
    StaticDef("OUTPUT_CGST", "Output CGST", "GST_OUTPUT", "GST liability - CGST"),
    StaticDef("OUTPUT_SGST", "Output SGST", "GST_OUTPUT", "GST liability - SGST"),
    StaticDef("OUTPUT_CESS", "Output CESS", "GST_OUTPUT", "GST liability - CESS"),

    # TDS/TCS (future)
    StaticDef("TDS_RECEIVABLE", "TDS Receivable", "TDS_TCS", "TDS receivable"),
    StaticDef("TDS_PAYABLE", "TDS Payable", "TDS_TCS", "TDS payable"),
    StaticDef("TCS_PAYABLE", "TCS Payable", "TDS_TCS", "TCS payable"),

    # Bank charges
    StaticDef("BANK_CHARGES", "Bank Charges", "CASH_BANK", "Bank charges expense"),
]


# ------------------------------
# 2) Keyword rules for auto-map
# ------------------------------
# Tune these to your chart-of-accounts naming.
AUTO_KEYWORDS: Dict[str, List[str]] = {
    "CASH": ["cash in hand", "cash-in-hand", "cash a/c", "cash account", "cash"],
    "BANK_MAIN": ["bank", "current account", "saving account", "bank a/c"],

    "ROUND_OFF_INCOME": ["round off income", "rounding income", "round off gain", "round off"],
    "ROUND_OFF_EXPENSE": ["round off expense", "rounding expense", "round off loss", "round off"],

    "PURCHASE_MISC_EXPENSE": ["purchase expense", "purchase misc", "misc expense", "freight inward", "loading", "unloading", "packing", "cartage"],
    "PURCHASE_DISCOUNT": ["purchase discount", "discount received"],

    "INPUT_IGST": ["input igst", "igst input", "itc igst"],
    "INPUT_CGST": ["input cgst", "cgst input", "itc cgst"],
    "INPUT_SGST": ["input sgst", "sgst input", "itc sgst"],
    "INPUT_CESS": ["input cess", "cess input", "itc cess"],

    "OUTPUT_IGST": ["output igst", "igst output", "igst payable"],
    "OUTPUT_CGST": ["output cgst", "cgst output", "cgst payable"],
    "OUTPUT_SGST": ["output sgst", "sgst output", "sgst payable"],
    "OUTPUT_CESS": ["output cess", "cess payable"],

    "TDS_RECEIVABLE": ["tds receivable", "tds recoverable", "tds rcv"],
    "TDS_PAYABLE": ["tds payable", "tds pay", "tds liability"],
    "TCS_PAYABLE": ["tcs payable", "tcs liability"],

    "BANK_CHARGES": ["bank charges", "bank charge", "charges bank", "neft charges", "rtgs charges"],
}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _account_label(a: Account) -> str:
    # Try common field names
    for f in ("accountname", "name", "ledgername", "title"):
        v = getattr(a, f, None)
        if v:
            return str(v)
    return str(a)


def _find_best_account_for_code(entity: Entity, code: str) -> Optional[Account]:
    """
    Auto-map strategy:
    - Search in Account table under the entity (if entity-scoped)
    - Match by keywords against account name
    """
    # If your Account table is entity-scoped, keep this filter.
    # If not, remove entity filter.
    qs = Account.objects.all()
    if hasattr(Account, "entity_id"):
        qs = qs.filter(entity_id=entity.id)

    keywords = AUTO_KEYWORDS.get(code, [])
    if not keywords:
        return None

    # Build OR Q
    q = Q()
    for kw in keywords:
        # adjust fields depending on your account model
        if hasattr(Account, "accountname"):
            q |= Q(accountname__icontains=kw)
        elif hasattr(Account, "name"):
            q |= Q(name__icontains=kw)
        else:
            # fallback - no name field known
            return None

    candidates = list(qs.filter(q)[:20])
    if not candidates:
        return None

    # Prefer the candidate whose name contains the most keywords
    def score(a: Account) -> int:
        name = _norm(_account_label(a))
        return sum(1 for kw in keywords if _norm(kw) in name)

    candidates.sort(key=score, reverse=True)
    return candidates[0]


class Command(BaseCommand):
    help = "Seed StaticAccount master + optionally map entity accounts."

    def add_arguments(self, parser):
        parser.add_argument("--entity-id", type=int, help="Entity ID for mapping (optional if only seeding master).")
        parser.add_argument("--only-master", action="store_true", help="Seed only StaticAccount master, no mapping.")

        parser.add_argument("--auto-map", action="store_true", help="Try to auto-map entity accounts by keywords.")
        parser.add_argument("--map-file", type=str, help="JSON file with mapping: {\"CODE\": account_id, ...}")
        parser.add_argument("--copy-from-entity", type=int, help="Copy mappings from another entity.")

        parser.add_argument("--force", action="store_true", help="Overwrite existing entity mappings.")
        parser.add_argument("--dry-run", action="store_true", help="Print what would happen without writing.")

    @transaction.atomic
    def handle(self, *args, **opts):
        entity_id = opts.get("entity_id")
        only_master = bool(opts.get("only_master"))
        auto_map = bool(opts.get("auto_map"))
        map_file = opts.get("map_file")
        copy_from_entity = opts.get("copy_from_entity")
        force = bool(opts.get("force"))
        dry_run = bool(opts.get("dry_run"))

        # --------------------------
        # Step A) Seed Static master
        # --------------------------
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding StaticAccount master..."))

        created = 0
        updated = 0

        for s in STATIC_MASTER:
            obj = StaticAccount.objects.filter(code=s.code).first()
            if obj is None:
                created += 1
                if not dry_run:
                    StaticAccount.objects.create(
                        code=s.code,
                        name=s.name,
                        group=s.group,
                        description=s.description,
                        is_active=True,
                    )
            else:
                # Keep code stable; update name/group/desc if changed
                changed = (
                    obj.name != s.name
                    or (obj.group or "") != (s.group or "")
                    or (obj.description or "") != (s.description or "")
                )
                if changed:
                    updated += 1
                    if not dry_run:
                        obj.name = s.name
                        obj.group = s.group
                        obj.description = s.description
                        obj.save(update_fields=["name", "group", "description"])

        self.stdout.write(f"StaticAccount master: created={created}, updated={updated}")

        if only_master:
            self.stdout.write(self.style.SUCCESS("Done (master only)."))
            return

        # --------------------------
        # Step B) Mapping requires entity
        # --------------------------
        if not entity_id:
            raise CommandError("--entity-id is required unless --only-master is used.")

        entity = Entity.objects.filter(id=entity_id).first()
        if not entity:
            raise CommandError(f"Entity not found: {entity_id}")

        # Decide mapping source
        if sum(bool(x) for x in [auto_map, bool(map_file), bool(copy_from_entity)]) == 0:
            raise CommandError("Choose one mapping mode: --auto-map OR --map-file OR --copy-from-entity")

        if sum(bool(x) for x in [auto_map, bool(map_file), bool(copy_from_entity)]) > 1:
            raise CommandError("Use only ONE mapping mode at a time (auto-map / map-file / copy-from-entity).")

        # Existing maps
        existing_qs = EntityStaticAccountMap.objects.filter(entity_id=entity.id)
        existing_count = existing_qs.count()

        if existing_count and not force:
            self.stdout.write(
                self.style.WARNING(
                    f"Entity {entity_id} already has {existing_count} mappings. "
                    f"Use --force to overwrite."
                )
            )
            return

        # If force, clear existing mappings first (safer)
        if existing_count and force:
            self.stdout.write(self.style.WARNING(f"Overwriting: deleting {existing_count} existing mappings..."))
            if not dry_run:
                existing_qs.delete()

        # Load mapping dict
        mapping: Dict[str, int] = {}

        if map_file:
            self.stdout.write(self.style.MIGRATE_HEADING(f"Loading mapping file: {map_file}"))
            try:
                with open(map_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("mapping file must contain a JSON object {CODE: account_id}")
                mapping = {str(k): int(v) for k, v in data.items()}
            except Exception as e:
                raise CommandError(f"Failed reading map-file: {e}")

        elif copy_from_entity:
            src = Entity.objects.filter(id=copy_from_entity).first()
            if not src:
                raise CommandError(f"Source entity not found: {copy_from_entity}")

            src_rows = (
                EntityStaticAccountMap.objects
                .filter(entity_id=src.id)
                .select_related("static_account", "account")
            )

            if not src_rows.exists():
                raise CommandError(f"Source entity {copy_from_entity} has no mappings.")

            # Copy by static code; keep same account_id (works only if accounts are shared or identical IDs)
            for r in src_rows:
                mapping[r.static_account.code] = r.account_id

        elif auto_map:
            self.stdout.write(self.style.MIGRATE_HEADING("Auto-mapping by keywords..."))
            for s in STATIC_MASTER:
                acc = _find_best_account_for_code(entity, s.code)
                if acc:
                    mapping[s.code] = acc.id

        # --------------------------
        # Step C) Create mappings
        # --------------------------
        if not mapping:
            self.stdout.write(self.style.WARNING("No mappings resolved. Nothing to insert."))
            return

        # Validate codes exist
        static_by_code = {x.code: x for x in StaticAccount.objects.filter(code__in=list(mapping.keys()))}
        missing_codes = [c for c in mapping.keys() if c not in static_by_code]
        if missing_codes:
            raise CommandError(f"Unknown StaticAccount codes in mapping: {missing_codes}")

        # Validate accounts exist
        acc_ids = set(mapping.values())
        acc_qs = Account.objects.filter(id__in=list(acc_ids))
        acc_by_id = {a.id: a for a in acc_qs}
        missing_acc = [aid for aid in acc_ids if aid not in acc_by_id]
        if missing_acc:
            raise CommandError(f"Account IDs not found: {missing_acc}")

        rows_to_create: List[EntityStaticAccountMap] = []

        for code, acc_id in mapping.items():
            rows_to_create.append(
                EntityStaticAccountMap(
                    entity_id=entity.id,
                    static_account_id=static_by_code[code].id,
                    account_id=acc_id,
                )
            )

        # Report
        self.stdout.write(self.style.MIGRATE_HEADING(f"Creating {len(rows_to_create)} mappings for entity={entity.id}"))

        # Print preview
        for r in rows_to_create:
            sa = StaticAccount.objects.get(id=r.static_account_id)
            a = acc_by_id.get(r.account_id)
            self.stdout.write(f"  {sa.code:<22} -> {a.id} ({_account_label(a)})")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry-run complete. No changes saved."))
            return

        EntityStaticAccountMap.objects.bulk_create(rows_to_create)
        self.stdout.write(self.style.SUCCESS(f"Inserted {len(rows_to_create)} mappings for entity={entity.id}"))
