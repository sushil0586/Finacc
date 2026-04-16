from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from entity.models import Entity, EntityOwnershipV2, EntityTaxProfile
from posting.models import StaticAccount, StaticAccountGroup
from posting.services.static_accounts import StaticAccountService

ZERO = Decimal("0.00")
Q2 = Decimal("0.01")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return ZERO


def _q2(value: Any) -> Decimal:
    try:
        return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class YearOpeningResolution:
    equity_static_account_code: str
    inventory_static_account_code: str
    equity_ledger_id: int | None
    inventory_ledger_id: int


class YearOpeningPostingAdapter:
    """
    Central year-opening adapter for posting.

    Responsibilities:
    - resolve configured destination ledgers through static account mappings
    - inspect entity ownership constitution
    - produce a carry-forward allocation plan for audit/history
    - keep actual posting service integration thin and source-of-truth driven
    """

    def __init__(self, *, entity_id: int, opening_policy: dict[str, Any]):
        self.entity_id = int(entity_id)
        self.opening_policy = opening_policy or {}

    def resolve_destination_ledgers(self, *, require_equity: bool = True) -> YearOpeningResolution:
        equity_code = _safe_text(
            self.opening_policy.get("opening_equity_static_account_code") or "OPENING_EQUITY_TRANSFER"
        ).upper()
        inventory_code = _safe_text(
            self.opening_policy.get("opening_inventory_static_account_code") or "OPENING_INVENTORY_CARRY_FORWARD"
        ).upper()

        equity_ledger_id = StaticAccountService.get_ledger_id(self.entity_id, equity_code, required=require_equity)
        inventory_ledger_id = StaticAccountService.get_ledger_id(self.entity_id, inventory_code, required=False)

        missing = []
        if require_equity and not equity_ledger_id:
            missing.append("opening_equity_static_account_code")
        if not inventory_ledger_id:
            missing.append("opening_inventory_static_account_code")
        if missing:
            raise ValueError(
                "Opening generation cannot resolve the configured destination ledgers. "
                f"Please configure: {', '.join(missing)}."
            )

        return YearOpeningResolution(
            equity_static_account_code=equity_code,
            inventory_static_account_code=inventory_code,
            equity_ledger_id=int(equity_ledger_id) if equity_ledger_id else None,
            inventory_ledger_id=int(inventory_ledger_id),
        )

    def build_constitution_context(self) -> dict[str, Any]:
        entity = Entity.objects.filter(pk=self.entity_id).only("id", "business_type", "entityname", "trade_name", "short_name").first()
        tax_profile = EntityTaxProfile.objects.filter(entity_id=self.entity_id).only("cin_no", "llpin_no").first()
        try:
            rows = list(
                EntityOwnershipV2.objects.filter(entity_id=self.entity_id, isactive=True)
                .order_by("-is_primary", "id")
                .values(
                    "id",
                    "ownership_type",
                    "name",
                    "share_percentage",
                    "capital_contribution",
                    "effective_from",
                    "effective_to",
                    "account_preference",
                    "agreement_reference",
                    "designation",
                    "remarks",
                    "is_primary",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive fallback for test harnesses and partial setups
            return {
                "constitution_mode": "unconfigured",
                "allocation_mode": "unconfigured",
                "total_share_percentage": "0.00",
                "ownership_rows": [],
                "source_error": str(exc),
                "constitution_source": "error",
                "constitution_notes": [str(exc)],
            }

        normalized: list[dict[str, Any]] = []
        total_share = ZERO
        for row in rows:
            share = _q2(row.get("share_percentage") or 0)
            total_share += share
            normalized.append(
                {
                    "id": row.get("id"),
                    "ownership_type": _safe_text(row.get("ownership_type")).lower() or "other",
                    "name": _safe_text(row.get("name")),
                    "share_percentage": f"{share:.2f}",
                    "capital_contribution": row.get("capital_contribution"),
                    "effective_from": row.get("effective_from").isoformat() if row.get("effective_from") else None,
                    "effective_to": row.get("effective_to").isoformat() if row.get("effective_to") else None,
                    "account_preference": _safe_text(row.get("account_preference")).lower() or "auto",
                    "agreement_reference": row.get("agreement_reference"),
                    "designation": row.get("designation"),
                    "remarks": row.get("remarks"),
                    "is_primary": bool(row.get("is_primary")),
                }
            )

        ownership_types = [row["ownership_type"] for row in normalized]
        partner_like = any(kind in {"partner", "proprietor", "shareholder"} for kind in ownership_types)
        company_like = any(kind in {"director", "shareholder"} for kind in ownership_types) and not any(
            kind == "partner" for kind in ownership_types
        )
        sole_owner = len(normalized) == 1
        constitution_source = "ownership_rows"
        constitution_notes: list[str] = []

        if getattr(tax_profile, "llpin_no", None):
            constitution_mode = "llp"
            allocation_mode = "ratio_split" if normalized else "single_owner"
            constitution_source = "tax_profile.llpin_no"
            constitution_notes.append("LLPIN detected in entity tax profile.")
        elif getattr(tax_profile, "cin_no", None):
            constitution_mode = "company"
            allocation_mode = "retained_earnings"
            constitution_source = "tax_profile.cin_no"
            constitution_notes.append("CIN detected in entity tax profile.")
        elif not normalized:
            constitution_mode = "unconfigured"
            allocation_mode = "unconfigured"
            constitution_notes.append("No active ownership rows found.")
        elif sole_owner or any(kind == "proprietor" for kind in ownership_types):
            constitution_mode = "proprietorship"
            allocation_mode = "single_owner"
            constitution_notes.append("Single proprietor ownership row selected.")
        elif any(kind == "partner" for kind in ownership_types):
            constitution_mode = "partnership"
            allocation_mode = "ratio_split"
            constitution_notes.append("Partner ownership rows selected for ratio allocation.")
        elif company_like:
            constitution_mode = "company"
            allocation_mode = "retained_earnings"
            constitution_notes.append("Director/shareholder rows selected as company ownership.")
        else:
            constitution_mode = "llp" if any(kind == "trustee" for kind in ownership_types) else "mixed"
            allocation_mode = "ratio_split" if partner_like else "single_owner"
            constitution_notes.append("Ownership rows did not resolve to a single constitution rule.")

        if entity and getattr(entity, "business_type", None):
            constitution_notes.append(f"Entity business type: {entity.business_type}.")
        if tax_profile and getattr(tax_profile, "cin_no", None) and constitution_mode != "company":
            constitution_notes.append("CIN exists but the ownership rows chose a different rule set.")
        if tax_profile and getattr(tax_profile, "llpin_no", None) and constitution_mode != "llp":
            constitution_notes.append("LLPIN exists but the ownership rows chose a different rule set.")

        validation_issues: list[dict[str, Any]] = []
        duplicate_names = {
            name: count
            for name, count in {
                name: sum(1 for row in normalized if _safe_text(row.get("name")).strip().lower() == name)
                for name in {_safe_text(row.get("name")).strip().lower() for row in normalized if _safe_text(row.get("name"))}
            }.items()
            if count > 1
        }
        if duplicate_names:
            validation_issues.append(
                {
                    "code": "duplicate_ownership_names",
                    "severity": "error",
                    "message": "Ownership rows contain duplicate names. Please keep each owner/partner unique.",
                    "details": sorted(duplicate_names.keys()),
                }
            )

        partner_rows = [row for row in normalized if row["ownership_type"] == "partner"]
        proprietor_rows = [row for row in normalized if row["ownership_type"] == "proprietor"]
        director_rows = [row for row in normalized if row["ownership_type"] == "director"]
        shareholder_rows = [row for row in normalized if row["ownership_type"] == "shareholder"]
        trustee_rows = [row for row in normalized if row["ownership_type"] == "trustee"]
        share_total_ok = total_share.quantize(Q2, rounding=ROUND_HALF_UP)

        if constitution_mode == "proprietorship":
            if len(normalized) != 1:
                validation_issues.append(
                    {
                        "code": "proprietorship_row_count",
                        "severity": "error",
                        "message": "A proprietorship must have exactly one active owner row.",
                        "details": {"active_rows": len(normalized)},
                    }
                )
            if normalized and share_total_ok != Decimal("100.00"):
                validation_issues.append(
                    {
                        "code": "proprietorship_share_total",
                        "severity": "error",
                        "message": "A proprietorship ownership row must total 100%.",
                        "details": {"share_total": f"{share_total_ok:.2f}"},
                    }
                )
        elif constitution_mode in {"partnership", "llp"}:
            if not partner_rows and not trustee_rows:
                validation_issues.append(
                    {
                        "code": "missing_partner_rows",
                        "severity": "error",
                        "message": "Partnership and LLP setups require at least one partner ownership row.",
                        "details": {"active_rows": len(normalized)},
                    }
                )
            if normalized and share_total_ok != Decimal("100.00"):
                validation_issues.append(
                    {
                        "code": "partner_share_total",
                        "severity": "error",
                        "message": "Partner shares must total 100% before opening and allocation can proceed.",
                        "details": {"share_total": f"{share_total_ok:.2f}"},
                    }
                )
        elif constitution_mode == "company":
            if partner_rows or proprietor_rows or trustee_rows:
                validation_issues.append(
                    {
                        "code": "company_ownership_mismatch",
                        "severity": "error",
                        "message": "Company constitution should not carry proprietor, partner, or trustee ownership rows.",
                        "details": {
                            "partner_rows": len(partner_rows),
                            "proprietor_rows": len(proprietor_rows),
                            "trustee_rows": len(trustee_rows),
                        },
                    }
                )
            if normalized and share_total_ok not in {Decimal("0.00"), Decimal("100.00")}:
                validation_issues.append(
                    {
                        "code": "company_share_total",
                        "severity": "warning",
                        "message": "Company ownership rows do not total 100%. Review if these rows are only informational.",
                        "details": {"share_total": f"{share_total_ok:.2f}"},
                    }
                )

        if constitution_mode == "llp" and director_rows + shareholder_rows:
            validation_issues.append(
                {
                    "code": "llp_ownership_mismatch",
                    "severity": "error",
                    "message": "LLP setups should not carry director/shareholder ownership rows.",
                    "details": {"director_rows": len(director_rows), "shareholder_rows": len(shareholder_rows)},
                }
            )

        if constitution_mode == "company" and partner_rows:
            validation_issues.append(
                {
                    "code": "company_has_partner_rows",
                    "severity": "error",
                    "message": "Company constitution cannot use partner ownership rows for profit allocation.",
                    "details": {"partner_rows": len(partner_rows)},
                }
            )

        if constitution_mode == "llp" and proprietor_rows:
            validation_issues.append(
                {
                    "code": "llp_has_proprietor_rows",
                    "severity": "error",
                    "message": "LLP constitution cannot use proprietor ownership rows.",
                    "details": {"proprietor_rows": len(proprietor_rows)},
                }
            )

        return {
            "constitution_mode": constitution_mode,
            "allocation_mode": allocation_mode,
            "total_share_percentage": f"{total_share:.2f}",
            "ownership_rows": normalized,
            "constitution_source": constitution_source,
            "constitution_notes": constitution_notes,
            "validation_issues": validation_issues,
            "is_valid": not any(issue.get("severity") == "error" for issue in validation_issues),
        }

    def build_profit_allocation_plan(self, net_profit: Decimal) -> list[dict[str, Any]]:
        context = self.build_constitution_context()
        rows = context["ownership_rows"]
        if not rows or net_profit == 0:
            return []

        net_profit = _decimal(net_profit)
        absolute_amount = abs(net_profit)
        shares = []
        for row in rows:
            share = _q2(row.get("share_percentage") or 0)
            if share > ZERO:
                shares.append((row, share))
        if not shares:
            shares = [(row, Decimal("100.00") / Decimal(len(rows))) for row in rows]

        total_share = sum((share for _, share in shares), ZERO)
        if total_share <= ZERO:
            return []

        allocations: list[dict[str, Any]] = []
        allocated = ZERO
        for index, (row, share) in enumerate(shares):
            if index == len(shares) - 1:
                amount = absolute_amount - allocated
            else:
                amount = (absolute_amount * share / total_share).quantize(Q2, rounding=ROUND_HALF_UP)
                allocated += amount
            allocations.append(
                {
                    "ownership_id": row.get("id"),
                    "name": row.get("name"),
                    "ownership_type": row.get("ownership_type"),
                    "share_percentage": row.get("share_percentage"),
                    "account_preference": row.get("account_preference"),
                    "amount": f"{amount:.2f}",
                    "drcr": "credit" if net_profit > ZERO else "debit",
                }
            )
        return allocations

    @staticmethod
    def _capital_role_for_row(*, constitution_mode: str, row: dict[str, Any]) -> str:
        preference = _safe_text(row.get("account_preference")).lower() or "auto"
        is_current = preference == "current"
        if constitution_mode == "company":
            return "OPENING_EQUITY_TRANSFER"
        if constitution_mode == "proprietorship":
            return "OPENING_OWNER_CURRENT" if is_current else "OPENING_OWNER_CAPITAL"
        if constitution_mode in {"partnership", "llp"}:
            return "OPENING_PARTNER_CURRENT" if is_current else "OPENING_PARTNER_CAPITAL"
        return "OPENING_EQUITY_TRANSFER"

    @staticmethod
    def _capital_role_name(*, constitution_mode: str, row: dict[str, Any]) -> str:
        label = _safe_text(row.get("name")) or "Unnamed"
        preference = _safe_text(row.get("account_preference")).lower() or "auto"
        if constitution_mode == "company":
            return "Opening Equity Transfer"
        if constitution_mode == "proprietorship":
            return f"Opening Owner {'Current' if preference == 'current' else 'Capital'} - {label}"
        if constitution_mode in {"partnership", "llp"}:
            return f"Opening Partner {'Current' if preference == 'current' else 'Capital'} - {label}"
        return f"Opening Equity Transfer - {label}"

    @staticmethod
    def _opening_role_code(*, constitution_mode: str, row: dict[str, Any]) -> str:
        base_role = YearOpeningPostingAdapter._capital_role_for_row(constitution_mode=constitution_mode, row=row)
        ownership_id = row.get("id")
        if constitution_mode == "company" or ownership_id in (None, ""):
            return base_role
        return f"{base_role}__OWNERSHIP_{ownership_id}"

    @staticmethod
    def _ensure_static_account_master(*, code: str, name: str, required: bool) -> int:
        normalized_code = _safe_text(code).upper()
        group = StaticAccountGroup.EQUITY if normalized_code.startswith("OPENING_") and "INVENTORY" not in normalized_code else StaticAccountGroup.OTHER
        static_acc, _ = StaticAccount.objects.get_or_create(
            code=normalized_code,
            defaults={
                "name": name,
                "group": group,
                "is_required": required,
                "is_active": True,
                "description": name,
            },
        )
        changed = []
        if static_acc.name != name:
            static_acc.name = name
            changed.append("name")
        if static_acc.group != group:
            static_acc.group = group
            changed.append("group")
        if bool(static_acc.is_required) != bool(required):
            static_acc.is_required = bool(required)
            changed.append("is_required")
        if not static_acc.is_active:
            static_acc.is_active = True
            changed.append("is_active")
        if static_acc.description != name:
            static_acc.description = name
            changed.append("description")
        if changed:
            static_acc.save(update_fields=changed)
        return static_acc.id

    def build_equity_targets(self, net_profit: Decimal) -> dict[str, Any]:
        context = self.build_constitution_context()
        constitution_mode = context["constitution_mode"]
        rows = context["ownership_rows"]
        allocations = self.build_profit_allocation_plan(net_profit)
        net_profit = _decimal(net_profit)

        targets: list[dict[str, Any]] = []
        missing_codes: list[str] = []

        if constitution_mode in {"company", "unconfigured", "mixed"} or not rows:
            code = _safe_text(
                self.opening_policy.get("opening_equity_static_account_code") or "OPENING_EQUITY_TRANSFER"
            ).upper() or "OPENING_EQUITY_TRANSFER"
            name = _safe_text(
                self.opening_policy.get("opening_equity_static_account_name") or "Opening Equity Transfer"
            ) or "Opening Equity Transfer"
            self._ensure_static_account_master(code=code, name=name, required=True)
            ledger_id = StaticAccountService.get_ledger_id(self.entity_id, code, required=False)
            if not ledger_id:
                missing_codes.append(code)
            targets.append(
                {
                    "static_account_code": code,
                    "static_account_name": name,
                    "ownership_id": None,
                    "ownership_name": None,
                    "ownership_type": None,
                    "account_preference": None,
                    "ledger_id": ledger_id,
                    "amount": f"{abs(net_profit):.2f}" if net_profit != ZERO else "0.00",
                    "drcr": "credit" if net_profit > ZERO else "debit",
                }
            )
            return {
                "equity_targets": targets,
                "missing_equity_codes": missing_codes,
                "allocation_mode": "single_batch",
            }

        row_index = {row.get("id"): row for row in rows if row.get("id") is not None}
        allocation_index = {item.get("ownership_id"): item for item in allocations}

        for ownership_id, row in row_index.items():
            allocation = allocation_index.get(ownership_id)
            if not allocation:
                continue
            code = self._opening_role_code(constitution_mode=constitution_mode, row=row)
            name = self._capital_role_name(constitution_mode=constitution_mode, row=row)
            self._ensure_static_account_master(code=code, name=name, required=True)
            ledger_id = StaticAccountService.get_ledger_id(self.entity_id, code, required=False)
            if not ledger_id:
                missing_codes.append(code)
            targets.append(
                {
                    "static_account_code": code,
                    "static_account_name": name,
                    "ownership_id": ownership_id,
                    "ownership_name": row.get("name"),
                    "ownership_type": row.get("ownership_type"),
                    "account_preference": row.get("account_preference"),
                    "ledger_id": ledger_id,
                    "amount": allocation.get("amount") or "0.00",
                    "drcr": allocation.get("drcr") or ("credit" if net_profit > ZERO else "debit"),
                }
            )

        return {
            "equity_targets": targets,
            "missing_equity_codes": missing_codes,
            "allocation_mode": context["allocation_mode"],
        }

    def build_context(self, *, net_profit: Decimal) -> dict[str, Any]:
        constitution = self.build_constitution_context()
        allocation_plan = self.build_profit_allocation_plan(net_profit)
        require_equity = not (constitution["constitution_mode"] in {"partnership", "llp"} and constitution["ownership_rows"])
        resolution = self.resolve_destination_ledgers(require_equity=require_equity)
        if constitution["constitution_mode"] in {"partnership", "llp"} and constitution["ownership_rows"]:
            equity_targets = self.build_equity_targets(net_profit)
        else:
            equity_targets = {
                "equity_targets": [],
                "missing_equity_codes": [],
                "allocation_mode": constitution["allocation_mode"],
            }
        return {
            "destination_ledgers": {
                "equity": {
                    "static_account_code": resolution.equity_static_account_code,
                    "ledger_id": resolution.equity_ledger_id,
                },
                "inventory": {
                    "static_account_code": resolution.inventory_static_account_code,
                    "ledger_id": resolution.inventory_ledger_id,
                },
            },
            "constitution": constitution,
            "allocation_plan": allocation_plan,
            "equity_targets": equity_targets.get("equity_targets") or [],
            "missing_equity_codes": equity_targets.get("missing_equity_codes") or [],
            "equity_allocation_mode": equity_targets.get("allocation_mode") or constitution["allocation_mode"],
            "validation_issues": constitution.get("validation_issues") or [],
            "constitution_is_valid": constitution.get("is_valid", True),
        }
