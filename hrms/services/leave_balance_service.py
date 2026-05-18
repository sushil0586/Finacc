from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db import transaction

from hrms.models import ContractLeaveBalanceSnapshot, ContractLeaveLedgerEntry, HrEmploymentContract, LeaveApplication, LeavePolicy, LeaveType
from hrms.services.leave_rule_engine import LeaveRuleEngine, LeaveRuleEvaluation
from hrms.services.leave_year_service import LeaveYearService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def _decimal(value: Any, default: Decimal = ZERO2) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default)).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return default


@dataclass(frozen=True)
class LeaveBalanceSummary:
    leave_type_id: str
    leave_type_code: str
    leave_type_name: str
    balance_days: Decimal
    encashable_days: Decimal
    last_snapshot_id: str | None
    trace: dict[str, Any]


class LeaveBalanceService:
    @classmethod
    def _policy_leave_types(cls, *, contract: HrEmploymentContract, as_of_date: date) -> list[LeaveType]:
        leave_policy = cls._active_leave_policy(contract=contract, as_of_date=as_of_date)
        if leave_policy is None:
            queryset = LeaveType.objects.filter(
                entity_id=contract.entity_id,
                is_active=True,
                deleted_at__isnull=True,
            )
        else:
            queryset = LeaveType.objects.filter(
                policy_rules__leave_policy=leave_policy,
                is_active=True,
                deleted_at__isnull=True,
            ).distinct()
        return list(queryset.order_by("code"))

    @staticmethod
    def _active_leave_policy(*, contract: HrEmploymentContract, as_of_date: date) -> LeavePolicy | None:
        return LeaveRuleEngine.resolve_leave_policy(contract=contract, as_of_date=as_of_date)

    @staticmethod
    def _latest_snapshot(
        *,
        contract: HrEmploymentContract,
        leave_type: LeaveType,
        as_of_date: date | None = None,
        period_start: date | None = None,
    ) -> ContractLeaveBalanceSnapshot | None:
        queryset = ContractLeaveBalanceSnapshot.objects.filter(
            entity_id=contract.entity_id,
            contract=contract,
            leave_type=leave_type,
            deleted_at__isnull=True,
        )
        if as_of_date is not None:
            queryset = queryset.filter(snapshot_date__lte=as_of_date)
        if period_start is not None:
            queryset = queryset.filter(snapshot_date__gte=period_start)
        return queryset.order_by("-snapshot_date", "-created_at", "-id").first()

    @classmethod
    def get_balance_days(cls, *, contract: HrEmploymentContract, leave_type: LeaveType, as_of_date: date | None = None) -> Decimal:
        as_of_date = as_of_date or date.today()
        leave_policy = cls._active_leave_policy(contract=contract, as_of_date=as_of_date)
        leave_year = LeaveYearService.current_leave_year(leave_policy=leave_policy, anchor_date=as_of_date)
        snapshot = cls._latest_snapshot(
            contract=contract,
            leave_type=leave_type,
            as_of_date=as_of_date,
            period_start=leave_year.start_date,
        )
        return _decimal(getattr(snapshot, "closing_balance", ZERO2))

    @classmethod
    def get_latest_balance_summary(cls, *, contract: HrEmploymentContract, leave_type: LeaveType, as_of_date: date | None = None) -> LeaveBalanceSummary:
        as_of_date = as_of_date or date.today()
        leave_policy = cls._active_leave_policy(contract=contract, as_of_date=as_of_date)
        leave_year = LeaveYearService.current_leave_year(leave_policy=leave_policy, anchor_date=as_of_date)
        snapshot = cls._latest_snapshot(
            contract=contract,
            leave_type=leave_type,
            as_of_date=as_of_date,
            period_start=leave_year.start_date,
        )
        evaluation = LeaveRuleEngine.evaluate_leave_type(
            contract=contract,
            leave_type=leave_type,
            as_of_date=as_of_date,
            leave_policy=leave_policy,
        )
        balance_days = _decimal(getattr(snapshot, "closing_balance", ZERO2))
        encashable_days = ZERO2
        if evaluation.encashment_enabled:
            encashable_days = min(balance_days, evaluation.encashment_cap or balance_days)
        return LeaveBalanceSummary(
            leave_type_id=str(leave_type.id),
            leave_type_code=leave_type.code,
            leave_type_name=leave_type.name,
            balance_days=balance_days,
            encashable_days=encashable_days,
            last_snapshot_id=str(snapshot.id) if snapshot else None,
            trace={
                "evaluation": evaluation.trace,
                "snapshot_source": getattr(snapshot, "snapshot_source", None),
                "leave_year_start": leave_year.start_date.isoformat(),
                "leave_year_end": leave_year.end_date.isoformat(),
            },
        )

    @classmethod
    def list_balance_summaries(cls, *, contract: HrEmploymentContract, as_of_date: date | None = None) -> list[LeaveBalanceSummary]:
        as_of_date = as_of_date or date.today()
        leave_types = cls._policy_leave_types(contract=contract, as_of_date=as_of_date)
        return [cls.get_latest_balance_summary(contract=contract, leave_type=leave_type, as_of_date=as_of_date) for leave_type in leave_types]

    @classmethod
    def _create_ledger_and_snapshot(
        cls,
        *,
        contract: HrEmploymentContract,
        leave_type: LeaveType,
        leave_policy: LeavePolicy | None,
        effective_date: date,
        entry_type: str,
        quantity_days: Decimal,
        balance_after_days: Decimal,
        snapshot_source: str,
        payroll_period_code: str = "",
        trace_json: dict[str, Any] | None = None,
        remarks: str = "",
        reference_type: str = "",
        reference_id: str = "",
        opening_balance: Decimal = ZERO2,
        accrued_days: Decimal = ZERO2,
        consumed_days: Decimal = ZERO2,
        carried_forward_days: Decimal = ZERO2,
        lapsed_days: Decimal = ZERO2,
        encashed_days: Decimal = ZERO2,
        attendance_percentage: Decimal = ZERO2,
    ) -> tuple[ContractLeaveLedgerEntry, ContractLeaveBalanceSnapshot]:
        ledger = ContractLeaveLedgerEntry.objects.create(
            entity_id=contract.entity_id,
            subentity_id=contract.subentity_id,
            contract=contract,
            leave_policy=leave_policy,
            leave_type=leave_type,
            effective_date=effective_date,
            entry_type=entry_type,
            quantity_days=quantity_days,
            balance_after_days=balance_after_days,
            reference_type=reference_type,
            reference_id=reference_id,
            payroll_period_code=payroll_period_code,
            trace_json=trace_json or {},
            remarks=remarks,
        )
        snapshot = ContractLeaveBalanceSnapshot.objects.create(
            entity_id=contract.entity_id,
            subentity_id=contract.subentity_id,
            contract=contract,
            leave_policy=leave_policy,
            leave_type=leave_type,
            payroll_period_code=payroll_period_code,
            snapshot_date=effective_date,
            snapshot_source=snapshot_source,
            opening_balance=opening_balance,
            accrued_days=accrued_days,
            consumed_days=consumed_days,
            carried_forward_days=carried_forward_days,
            lapsed_days=lapsed_days,
            encashed_days=encashed_days,
            closing_balance=balance_after_days,
            attendance_percentage=attendance_percentage,
            trace_json=trace_json or {},
        )
        return ledger, snapshot

    @classmethod
    @transaction.atomic
    def set_opening_balance(
        cls,
        *,
        contract: HrEmploymentContract,
        leave_type: LeaveType,
        as_of_date: date,
        quantity_days: Decimal,
        remarks: str = "Opening balance initialized",
        reference_type: str = "OPENING_BALANCE",
        reference_id: str = "",
        trace_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        leave_policy = cls._active_leave_policy(contract=contract, as_of_date=as_of_date)
        opening_balance = max(_decimal(quantity_days), ZERO2)
        ledger, snapshot = cls._create_ledger_and_snapshot(
            contract=contract,
            leave_type=leave_type,
            leave_policy=leave_policy,
            effective_date=as_of_date,
            entry_type=ContractLeaveLedgerEntry.EntryType.OPENING,
            quantity_days=opening_balance,
            balance_after_days=opening_balance,
            snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.OPENING,
            trace_json=trace_json or {},
            remarks=remarks,
            reference_type=reference_type,
            reference_id=reference_id or as_of_date.isoformat(),
            opening_balance=opening_balance,
        )
        return {
            "created": True,
            "quantity_days": str(opening_balance),
            "balance_after_days": str(opening_balance),
            "ledger_id": str(ledger.id),
            "snapshot_id": str(snapshot.id),
        }

    @classmethod
    def bootstrap_from_policy_defaults(cls, *, contract: HrEmploymentContract, as_of_date: date) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        created_count = 0
        for leave_type in cls._policy_leave_types(contract=contract, as_of_date=as_of_date):
            existing_snapshot = cls._latest_snapshot(
                contract=contract,
                leave_type=leave_type,
                as_of_date=as_of_date,
                period_start=LeaveYearService.current_leave_year(
                    leave_policy=cls._active_leave_policy(contract=contract, as_of_date=as_of_date),
                    anchor_date=as_of_date,
                ).start_date,
            )
            evaluation = LeaveRuleEngine.evaluate_leave_type(
                contract=contract,
                leave_type=leave_type,
                as_of_date=as_of_date,
            )
            merged_rule_json = (evaluation.trace or {}).get("merged_rule_json", {}) or {}
            default_quantity = ZERO2
            if evaluation.accrual_frequency == "yearly":
                default_quantity = evaluation.accrual_days
            elif evaluation.accrual_frequency == "monthly":
                default_quantity = _decimal(merged_rule_json.get("monthly_quota", "0"))
            elif merged_rule_json.get("opening_balance") not in (None, ""):
                default_quantity = _decimal(merged_rule_json.get("opening_balance", "0"))

            if evaluation.max_balance_cap is not None:
                default_quantity = min(default_quantity, evaluation.max_balance_cap)

            if existing_snapshot is not None:
                items.append(
                    {
                        "leave_type_id": str(leave_type.id),
                        "leave_type_code": leave_type.code,
                        "leave_type_name": leave_type.name,
                        "action": "skipped_existing",
                        "quantity_days": "0.00",
                        "balance_after_days": str(getattr(existing_snapshot, "closing_balance", ZERO2)),
                        "message": "Existing balance snapshot already present.",
                        "trace": evaluation.trace,
                    }
                )
                continue

            if default_quantity <= ZERO2:
                items.append(
                    {
                        "leave_type_id": str(leave_type.id),
                        "leave_type_code": leave_type.code,
                        "leave_type_name": leave_type.name,
                        "action": "skipped_zero",
                        "quantity_days": "0.00",
                        "balance_after_days": "0.00",
                        "message": "Policy did not resolve a positive default balance.",
                        "trace": evaluation.trace,
                    }
                )
                continue

            result = cls.set_opening_balance(
                contract=contract,
                leave_type=leave_type,
                as_of_date=as_of_date,
                quantity_days=default_quantity,
                remarks="Opening balance initialized from leave policy defaults",
                reference_type="POLICY_DEFAULT",
                reference_id=as_of_date.isoformat(),
                trace_json=evaluation.trace,
            )
            created_count += 1
            items.append(
                {
                    "leave_type_id": str(leave_type.id),
                    "leave_type_code": leave_type.code,
                    "leave_type_name": leave_type.name,
                    "action": "created",
                    "quantity_days": result["quantity_days"],
                    "balance_after_days": result["balance_after_days"],
                    "message": "Opening balance created from current leave rule defaults.",
                    "trace": evaluation.trace,
                }
            )
        return {
            "contract_id": str(contract.id),
            "as_of_date": as_of_date.isoformat(),
            "created_count": created_count,
            "items": items,
        }

    @classmethod
    def accrue_contract_balances(cls, *, contract: HrEmploymentContract, as_of_date: date) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        created_count = 0
        for leave_type in cls._policy_leave_types(contract=contract, as_of_date=as_of_date):
            result = cls.accrue_for_period(contract=contract, leave_type=leave_type, as_of_date=as_of_date)
            action = "created" if result.get("created") else "skipped"
            if result.get("created"):
                created_count += 1
            items.append(
                {
                    "leave_type_id": str(leave_type.id),
                    "leave_type_code": leave_type.code,
                    "leave_type_name": leave_type.name,
                    "action": action,
                    "quantity_days": str(result.get("accrued_days", "0.00")),
                    "balance_after_days": str(cls.get_balance_days(contract=contract, leave_type=leave_type)),
                    "message": "Periodic accrual created." if result.get("created") else "No new accrual created.",
                    "trace": result.get("trace", {}),
                }
            )
        return {
            "contract_id": str(contract.id),
            "as_of_date": as_of_date.isoformat(),
            "created_count": created_count,
            "items": items,
        }

    @classmethod
    @transaction.atomic
    def accrue_for_period(cls, *, contract: HrEmploymentContract, leave_type: LeaveType, as_of_date: date, payroll_period=None) -> dict[str, Any]:
        leave_policy = cls._active_leave_policy(contract=contract, as_of_date=as_of_date)
        evaluation = LeaveRuleEngine.evaluate_leave_type(
            contract=contract,
            leave_type=leave_type,
            as_of_date=as_of_date,
            payroll_period=payroll_period,
            leave_policy=leave_policy,
        )
        if evaluation.accrual_days <= ZERO2:
            return {"accrued_days": "0.00", "created": False, "trace": evaluation.trace}

        leave_year = LeaveYearService.current_leave_year(leave_policy=leave_policy, anchor_date=as_of_date)
        if payroll_period is not None:
            reference_id = getattr(payroll_period, "code", "") or as_of_date.isoformat()
            reference_type = "PAYROLL_PERIOD"
        elif evaluation.accrual_frequency == "yearly":
            reference_id = f"LEAVE_YEAR:{leave_year.start_date.isoformat()}"
            reference_type = "LEAVE_YEAR"
        elif evaluation.accrual_frequency == "monthly":
            reference_id = as_of_date.strftime("%Y-%m")
            reference_type = "LEAVE_MONTH"
        else:
            reference_id = as_of_date.isoformat()
            reference_type = "ADHOC"
        existing = ContractLeaveLedgerEntry.objects.filter(
            entity_id=contract.entity_id,
            contract=contract,
            leave_type=leave_type,
            entry_type=ContractLeaveLedgerEntry.EntryType.ACCRUAL,
            reference_type=reference_type,
            reference_id=reference_id,
            deleted_at__isnull=True,
        ).first()
        if existing is not None:
            return {"accrued_days": str(existing.quantity_days), "created": False, "trace": existing.trace_json or {}}

        opening_balance = cls.get_balance_days(contract=contract, leave_type=leave_type, as_of_date=as_of_date)
        accrual_days = evaluation.accrual_days
        if evaluation.max_balance_cap is not None:
            accrual_days = max(min(accrual_days, evaluation.max_balance_cap - opening_balance), ZERO2)
        if accrual_days <= ZERO2:
            return {"accrued_days": "0.00", "created": False, "trace": evaluation.trace}

        closing_balance = opening_balance + accrual_days
        ledger, snapshot = cls._create_ledger_and_snapshot(
            contract=contract,
            leave_type=leave_type,
            leave_policy=leave_policy,
            effective_date=getattr(payroll_period, "period_end", as_of_date),
            entry_type=ContractLeaveLedgerEntry.EntryType.ACCRUAL,
            quantity_days=accrual_days,
            balance_after_days=closing_balance,
            snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.ACCRUAL,
            payroll_period_code=getattr(payroll_period, "code", ""),
            trace_json=evaluation.trace,
            remarks="Periodic leave accrual",
            reference_type=reference_type,
            reference_id=reference_id,
            opening_balance=opening_balance,
            accrued_days=accrual_days,
            attendance_percentage=evaluation.attendance_percentage,
        )
        return {"accrued_days": str(accrual_days), "created": True, "ledger_id": str(ledger.id), "snapshot_id": str(snapshot.id), "trace": evaluation.trace}

    @classmethod
    @transaction.atomic
    def apply_carry_forward(cls, *, contract: HrEmploymentContract, leave_type: LeaveType, as_of_date: date) -> dict[str, Any]:
        leave_policy = cls._active_leave_policy(contract=contract, as_of_date=as_of_date)
        current_year = LeaveYearService.current_leave_year(leave_policy=leave_policy, anchor_date=as_of_date)
        previous_year = LeaveYearService.previous_leave_year(leave_policy=leave_policy, anchor_date=as_of_date)
        evaluation = LeaveRuleEngine.evaluate_leave_type(
            contract=contract,
            leave_type=leave_type,
            as_of_date=as_of_date,
            leave_policy=leave_policy,
        )
        existing = ContractLeaveLedgerEntry.objects.filter(
            entity_id=contract.entity_id,
            contract=contract,
            leave_type=leave_type,
            entry_type=ContractLeaveLedgerEntry.EntryType.LAPSE,
            reference_type="LEAVE_YEAR",
            reference_id=current_year.start_date.isoformat(),
            deleted_at__isnull=True,
        ).first()
        if existing is not None:
            return {"created": False, "carried_forward_days": str(existing.balance_after_days), "lapsed_days": "0.00", "trace": existing.trace_json or {}}
        opening_snapshot = cls._latest_snapshot(
            contract=contract,
            leave_type=leave_type,
            as_of_date=previous_year.end_date,
            period_start=previous_year.start_date,
        )
        opening_balance = _decimal(getattr(opening_snapshot, "closing_balance", ZERO2))
        if evaluation.carry_forward_cap is not None:
            allowed_balance = opening_balance
            allowed_balance = min(opening_balance, evaluation.carry_forward_cap)
        elif evaluation.lapse_enabled:
            allowed_balance = ZERO2
        else:
            allowed_balance = opening_balance
        lapsed_days = max(opening_balance - allowed_balance, ZERO2)
        if opening_balance <= ZERO2 and allowed_balance <= ZERO2:
            return {"created": False, "carried_forward_days": "0.00", "lapsed_days": "0.00", "trace": evaluation.trace}

        ledger, snapshot = cls._create_ledger_and_snapshot(
            contract=contract,
            leave_type=leave_type,
            leave_policy=leave_policy,
            effective_date=current_year.start_date,
            entry_type=ContractLeaveLedgerEntry.EntryType.LAPSE,
            quantity_days=-lapsed_days,
            balance_after_days=allowed_balance,
            snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.CARRY_FORWARD,
            trace_json=evaluation.trace,
            remarks="Carry forward cap / lapse applied",
            reference_type="LEAVE_YEAR",
            reference_id=current_year.start_date.isoformat(),
            opening_balance=opening_balance,
            carried_forward_days=allowed_balance,
            lapsed_days=lapsed_days,
        )
        return {"created": True, "carried_forward_days": str(allowed_balance), "lapsed_days": str(lapsed_days), "ledger_id": str(ledger.id), "snapshot_id": str(snapshot.id), "trace": evaluation.trace}

    @classmethod
    @transaction.atomic
    def consume_for_application(cls, *, application: LeaveApplication, approved_days: Decimal | None = None) -> dict[str, Any]:
        contract = application.contract
        leave_type = application.leave_type
        approved_days = _decimal(approved_days if approved_days is not None else application.requested_days)
        leave_policy = application.leave_policy or cls._active_leave_policy(contract=contract, as_of_date=application.end_date)
        evaluation = LeaveRuleEngine.evaluate_leave_type(
            contract=contract,
            leave_type=leave_type,
            as_of_date=application.end_date,
            leave_policy=leave_policy,
        )
        opening_balance = cls.get_balance_days(contract=contract, leave_type=leave_type, as_of_date=application.end_date)
        paid_days = ZERO2
        unpaid_days = ZERO2
        consumed_days = ZERO2
        closing_balance = opening_balance

        if evaluation.payroll_impact == "paid":
            if leave_type.requires_balance:
                paid_days = min(opening_balance, approved_days)
                unpaid_days = max(approved_days - paid_days, ZERO2)
                consumed_days = paid_days
                closing_balance = max(opening_balance - consumed_days, ZERO2)
            else:
                paid_days = approved_days
        else:
            unpaid_days = approved_days

        ledger_id = None
        snapshot_id = None
        if consumed_days > ZERO2:
            ledger, snapshot = cls._create_ledger_and_snapshot(
                contract=contract,
                leave_type=leave_type,
                leave_policy=leave_policy,
                effective_date=application.end_date,
                entry_type=ContractLeaveLedgerEntry.EntryType.CONSUMPTION,
                quantity_days=-consumed_days,
                balance_after_days=closing_balance,
                snapshot_source=ContractLeaveBalanceSnapshot.SnapshotSource.CONSUMPTION,
                trace_json=evaluation.trace,
                remarks="Leave application approved",
                reference_type="LEAVE_APPLICATION",
                reference_id=str(application.id),
                opening_balance=opening_balance,
                consumed_days=consumed_days,
                attendance_percentage=evaluation.attendance_percentage,
            )
            ledger_id = str(ledger.id)
            snapshot_id = str(snapshot.id)

        return {
            "approved_days": str(approved_days),
            "paid_days": str(paid_days),
            "unpaid_days": str(unpaid_days),
            "consumed_days": str(consumed_days),
            "balance_after_days": str(closing_balance),
            "ledger_id": ledger_id,
            "snapshot_id": snapshot_id,
            "trace": evaluation.trace,
        }

    @classmethod
    def get_encashment_eligibility(cls, *, contract: HrEmploymentContract, as_of_date: date) -> dict[str, Any]:
        leave_policy = cls._active_leave_policy(contract=contract, as_of_date=as_of_date)
        if leave_policy is None:
            return {"eligible_days": "0.00", "items": []}
        leave_year = LeaveYearService.current_leave_year(leave_policy=leave_policy, anchor_date=as_of_date)
        items: list[dict[str, Any]] = []
        total_eligible = ZERO2
        leave_types = LeaveType.objects.filter(
            policy_rules__leave_policy=leave_policy,
            is_active=True,
            deleted_at__isnull=True,
        ).distinct().order_by("code")
        for leave_type in leave_types:
            summary = cls.get_latest_balance_summary(contract=contract, leave_type=leave_type, as_of_date=min(as_of_date, leave_year.end_date))
            if summary.encashable_days <= ZERO2:
                continue
            total_eligible += summary.encashable_days
            items.append(
                {
                    "leave_type_id": summary.leave_type_id,
                    "leave_type_code": summary.leave_type_code,
                    "leave_type_name": summary.leave_type_name,
                    "balance_days": str(summary.balance_days),
                    "encashable_days": str(summary.encashable_days),
                    "trace": summary.trace,
                }
            )
        return {"eligible_days": str(total_eligible), "items": items}
