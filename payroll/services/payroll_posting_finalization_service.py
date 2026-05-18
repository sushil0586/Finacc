from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from django.db import transaction
from django.db.models import Q

from financial.models import account
from payroll.models import FnFSettlement, PayrollComponentPosting, PayrollLedgerPolicy, PayrollRun
from posting.common.journal_descriptions import payroll_prefix
from posting.models import EntityStaticAccountMap, Entry, StaticAccount, TxnType
from posting.services.posting_service import JLInput, PostingService

ZERO2 = Decimal("0.00")
Q2 = Decimal("0.01")


def q2(value) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        return ZERO2


@dataclass(frozen=True)
class _ResolvedAccount:
    account: account | None
    resolution_type: str
    resolution_code: str


class PayrollPostingFinalizationService:
    STATIC_ACCOUNT_DEFINITIONS: tuple[tuple[str, str, str, bool], ...] = (
        ("PAYROLL_SALARY_PAYABLE", "Payroll Salary Payable", "Other", True),
        ("PAYROLL_REIMBURSEMENT_PAYABLE", "Payroll Reimbursement Payable", "Other", False),
        ("PAYROLL_EMPLOYER_CONTRIBUTION_PAYABLE", "Payroll Employer Contribution Payable", "Other", False),
        ("PAYROLL_PF_PAYABLE", "Payroll PF Payable", "Other", False),
        ("PAYROLL_ESI_PAYABLE", "Payroll ESI Payable", "Other", False),
        ("PAYROLL_PT_PAYABLE", "Payroll PT Payable", "Other", False),
        ("PAYROLL_LWF_PAYABLE", "Payroll LWF Payable", "Other", False),
        ("PAYROLL_FNF_PAYABLE", "Payroll FnF Payable", "Other", False),
        ("PAYROLL_FNF_RECOVERABLE", "Payroll FnF Recoverable", "Other", False),
    )

    STATUTORY_STATIC_CODES = {
        "PF_EMPLOYEE": "PAYROLL_PF_PAYABLE",
        "PF_EMPLOYER": "PAYROLL_PF_PAYABLE",
        "ESI_EMPLOYEE": "PAYROLL_ESI_PAYABLE",
        "ESI_EMPLOYER": "PAYROLL_ESI_PAYABLE",
        "PT": "PAYROLL_PT_PAYABLE",
        "TDS": "TDS_PAYABLE",
        "LWF_EMPLOYEE": "PAYROLL_LWF_PAYABLE",
        "LWF_EMPLOYER": "PAYROLL_LWF_PAYABLE",
    }

    @classmethod
    def preview_run(cls, run: PayrollRun) -> dict:
        source_run = cls._posting_source_run(run)
        policy = cls._policy_for_run(run)
        issues: list[dict] = []
        raw_rows: list[dict] = []
        salary_counterparty = ZERO2
        reimbursement_counterparty = ZERO2

        for employee_row in cls._iter_run_rows(source_run):
            salary_counterparty = q2(
                salary_counterparty + q2(employee_row.payable_amount) - q2(employee_row.reimbursement_amount)
            )
            reimbursement_counterparty = q2(reimbursement_counterparty + q2(employee_row.reimbursement_amount))
            for component_row in employee_row.components.all():
                amount = q2(component_row.amount)
                if amount <= ZERO2:
                    continue
                component = component_row.component
                semantic_code = cls._component_semantic_code(component_row)
                source_reference = employee_row.employee_code or employee_row.employee_name or str(employee_row.id)
                if component.component_type in {
                    component.ComponentType.EARNING,
                    component.ComponentType.REIMBURSEMENT,
                }:
                    expense = cls._resolve_component_expense_account(
                        entity_id=run.entity_id,
                        posting_map=getattr(component_row, "component_posting_version", None),
                        issues=issues,
                        component_code=component_row.component_code,
                    )
                    if expense.account:
                        raw_rows.append(
                            cls._journal_row(
                                account_obj=expense.account,
                                drcr=True,
                                amount=amount,
                                description=payroll_prefix(run),
                                category="expense",
                                source_reference=source_reference,
                                component_code=component_row.component_code,
                            )
                        )
                elif component.component_type == component.ComponentType.EMPLOYER_CONTRIBUTION:
                    expense = cls._resolve_component_expense_account(
                        entity_id=run.entity_id,
                        posting_map=getattr(component_row, "component_posting_version", None),
                        issues=issues,
                        component_code=component_row.component_code,
                    )
                    liability = cls._resolve_run_component_liability_account(
                        run=run,
                        policy=policy,
                        posting_map=getattr(component_row, "component_posting_version", None),
                        component_type=component.component_type,
                        semantic_code=semantic_code,
                        issues=issues,
                        component_code=component_row.component_code,
                    )
                    if expense.account:
                        raw_rows.append(
                            cls._journal_row(
                                account_obj=expense.account,
                                drcr=True,
                                amount=amount,
                                description=payroll_prefix(run),
                                category="expense",
                                source_reference=source_reference,
                                component_code=component_row.component_code,
                            )
                        )
                    if liability.account:
                        raw_rows.append(
                            cls._journal_row(
                                account_obj=liability.account,
                                drcr=False,
                                amount=amount,
                                description=payroll_prefix(run),
                                category="employer_liability",
                                source_reference=source_reference,
                                component_code=component_row.component_code,
                            )
                        )
                else:
                    liability = cls._resolve_run_component_liability_account(
                        run=run,
                        policy=policy,
                        posting_map=getattr(component_row, "component_posting_version", None),
                        component_type=component.component_type,
                        semantic_code=semantic_code,
                        issues=issues,
                        component_code=component_row.component_code,
                    )
                    if liability.account:
                        raw_rows.append(
                            cls._journal_row(
                                account_obj=liability.account,
                                drcr=False,
                                amount=amount,
                                description=payroll_prefix(run),
                                category="liability",
                                source_reference=source_reference,
                                component_code=component_row.component_code,
                            )
                        )

        salary_payable = None
        if salary_counterparty > ZERO2:
            salary_payable = cls._resolve_run_salary_payable_account(run=run, policy=policy, issues=issues)
        if salary_counterparty > ZERO2 and salary_payable and salary_payable.account:
            raw_rows.append(
                cls._journal_row(
                    account_obj=salary_payable.account,
                    drcr=False,
                    amount=salary_counterparty,
                    description=payroll_prefix(run),
                    category="salary_payable",
                    source_reference=run.run_number or str(run.id),
                )
            )
        elif salary_counterparty < ZERO2:
            issues.append(
                cls._issue(
                    code="NEGATIVE_SALARY_PAYABLE",
                    message="Payroll net salary payable is negative. Posting requires a dedicated recoverable design before it can proceed.",
                    source="payroll_run",
                )
            )

        reimbursement_payable = None
        if reimbursement_counterparty > ZERO2:
            reimbursement_payable = cls._resolve_run_reimbursement_account(run=run, policy=policy, issues=issues)
        if reimbursement_counterparty > ZERO2 and reimbursement_payable and reimbursement_payable.account:
            raw_rows.append(
                cls._journal_row(
                    account_obj=reimbursement_payable.account,
                    drcr=False,
                    amount=reimbursement_counterparty,
                    description=payroll_prefix(run),
                    category="reimbursement_payable",
                    source_reference=run.run_number or str(run.id),
                )
            )
        elif reimbursement_counterparty < ZERO2:
            issues.append(
                cls._issue(
                    code="NEGATIVE_REIMBURSEMENT_PAYABLE",
                    message="Payroll reimbursement payable is negative. Posting cannot continue until the reimbursement snapshot is corrected.",
                    source="payroll_run",
                )
            )

        return cls._finalize_preview(
            source_type="PAYROLL_RUN",
            source_id=run.id,
            source_number=run.run_number or f"{run.doc_code}-{run.doc_no or run.id}",
            status=run.status,
            posting_date=run.posting_date,
            raw_rows=raw_rows,
            issues=issues,
            narration=payroll_prefix(run),
            is_reversal=bool(run.reversed_run_id),
            txn_type=TxnType.PAYROLL,
            txn_id=run.id,
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            voucher_no=run.run_number or (str(run.doc_no) if run.doc_no else None),
            voucher_date=run.payroll_period.period_end,
        )

    @classmethod
    def preview_fnf(cls, settlement: FnFSettlement) -> dict:
        issues: list[dict] = []
        raw_rows: list[dict] = []
        employee_counterparty = ZERO2

        for component_row in settlement.components.select_related("component", "source_structure_line"):
            amount = q2(component_row.amount)
            if amount <= ZERO2:
                continue
            component = component_row.component
            semantic_code = str(getattr(component, "semantic_code", "") or "")
            posting_map = cls._resolve_fnf_component_posting(settlement=settlement, component=component)
            source_reference = settlement.contract_payroll_profile.employee_code or settlement.contract_payroll_profile.employee_name or str(settlement.id)
            if component_row.component_type in {
                FnFSettlementComponentType.EARNING,
                FnFSettlementComponentType.REIMBURSEMENT,
            }:
                employee_counterparty = q2(employee_counterparty + amount)
                expense = cls._resolve_component_expense_account(
                    entity_id=settlement.entity_id,
                    posting_map=posting_map,
                    issues=issues,
                    component_code=component_row.component_code,
                )
                if expense.account:
                    raw_rows.append(
                        cls._journal_row(
                            account_obj=expense.account,
                            drcr=True,
                            amount=amount,
                            description=cls._fnf_prefix(settlement),
                            category="expense",
                            source_reference=source_reference,
                            component_code=component_row.component_code,
                        )
                    )
            elif component_row.component_type == FnFSettlementComponentType.EMPLOYER_CONTRIBUTION:
                expense = cls._resolve_component_expense_account(
                    entity_id=settlement.entity_id,
                    posting_map=posting_map,
                    issues=issues,
                    component_code=component_row.component_code,
                )
                liability = cls._resolve_fnf_component_liability_account(
                    settlement=settlement,
                    posting_map=posting_map,
                    component_type=component_row.component_type,
                    semantic_code=semantic_code,
                    issues=issues,
                    component_code=component_row.component_code,
                )
                if expense.account:
                    raw_rows.append(
                        cls._journal_row(
                            account_obj=expense.account,
                            drcr=True,
                            amount=amount,
                            description=cls._fnf_prefix(settlement),
                            category="expense",
                            source_reference=source_reference,
                            component_code=component_row.component_code,
                        )
                    )
                if liability.account:
                    raw_rows.append(
                        cls._journal_row(
                            account_obj=liability.account,
                            drcr=False,
                            amount=amount,
                            description=cls._fnf_prefix(settlement),
                            category="employer_liability",
                            source_reference=source_reference,
                            component_code=component_row.component_code,
                        )
                    )
            else:
                employee_counterparty = q2(employee_counterparty - amount)
                liability = cls._resolve_fnf_component_liability_account(
                    settlement=settlement,
                    posting_map=posting_map,
                    component_type=component_row.component_type,
                    semantic_code=semantic_code,
                    issues=issues,
                    component_code=component_row.component_code,
                )
                if liability.account:
                    raw_rows.append(
                        cls._journal_row(
                            account_obj=liability.account,
                            drcr=False,
                            amount=amount,
                            description=cls._fnf_prefix(settlement),
                            category="liability",
                            source_reference=source_reference,
                            component_code=component_row.component_code,
                        )
                    )

        if employee_counterparty > ZERO2:
            payable = cls._resolve_static_account(
                entity_id=settlement.entity_id,
                subentity_id=settlement.subentity_id,
                code="PAYROLL_FNF_PAYABLE",
                issues=issues,
                component_code="FNF_PAYABLE",
            )
            if payable.account:
                raw_rows.append(
                    cls._journal_row(
                        account_obj=payable.account,
                        drcr=False,
                        amount=employee_counterparty,
                        description=cls._fnf_prefix(settlement),
                        category="fnf_payable",
                        source_reference=settlement.settlement_number or str(settlement.id),
                    )
                )
        elif employee_counterparty < ZERO2:
            recoverable = cls._resolve_static_account(
                entity_id=settlement.entity_id,
                subentity_id=settlement.subentity_id,
                code="PAYROLL_FNF_RECOVERABLE",
                issues=issues,
                component_code="FNF_RECOVERABLE",
            )
            if recoverable.account:
                raw_rows.append(
                    cls._journal_row(
                        account_obj=recoverable.account,
                        drcr=True,
                        amount=abs(employee_counterparty),
                        description=cls._fnf_prefix(settlement),
                        category="fnf_recoverable",
                        source_reference=settlement.settlement_number or str(settlement.id),
                    )
                )

        return cls._finalize_preview(
            source_type="FNF_SETTLEMENT",
            source_id=settlement.id,
            source_number=settlement.settlement_number or f"FNF-{settlement.id}",
            status=settlement.status,
            posting_date=settlement.settlement_date,
            raw_rows=raw_rows,
            issues=issues,
            narration=cls._fnf_prefix(settlement),
            is_reversal=False,
            txn_type=TxnType.PAYROLL_FNF,
            txn_id=settlement.id,
            entity_id=settlement.entity_id,
            entityfinid_id=settlement.entityfinid_id,
            subentity_id=settlement.subentity_id,
            voucher_no=settlement.settlement_number or f"FNF-{settlement.id}",
            voucher_date=settlement.settlement_date,
        )

    @classmethod
    def validate_run(cls, run: PayrollRun) -> dict:
        return cls.preview_run(run)

    @classmethod
    def validate_fnf(cls, settlement: FnFSettlement) -> dict:
        return cls.preview_fnf(settlement)

    @classmethod
    @transaction.atomic
    def post_run(cls, run: PayrollRun, *, user_id: int) -> Entry:
        preview = cls.preview_run(run)
        cls._raise_for_blocking_issues(preview)
        posting_service = PostingService(
            entity_id=run.entity_id,
            entityfin_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            user_id=user_id,
        )
        return posting_service.post(
            txn_type=preview["posting"]["txn_type"],
            txn_id=preview["posting"]["txn_id"],
            voucher_no=preview["posting"]["voucher_no"],
            voucher_date=preview["posting"]["voucher_date"],
            posting_date=preview["posting"]["posting_date"],
            narration=preview["posting"]["narration"],
            jl_inputs=preview["posting"]["jl_inputs"],
            im_inputs=[],
            mark_posted=True,
        )

    @classmethod
    @transaction.atomic
    def post_fnf(cls, settlement: FnFSettlement, *, user_id: int) -> Entry:
        preview = cls.preview_fnf(settlement)
        cls._raise_for_blocking_issues(preview)
        posting_service = PostingService(
            entity_id=settlement.entity_id,
            entityfin_id=settlement.entityfinid_id,
            subentity_id=settlement.subentity_id,
            user_id=user_id,
        )
        return posting_service.post(
            txn_type=preview["posting"]["txn_type"],
            txn_id=preview["posting"]["txn_id"],
            voucher_no=preview["posting"]["voucher_no"],
            voucher_date=preview["posting"]["voucher_date"],
            posting_date=preview["posting"]["posting_date"],
            narration=preview["posting"]["narration"],
            jl_inputs=preview["posting"]["jl_inputs"],
            im_inputs=[],
            mark_posted=True,
        )

    @classmethod
    def posting_status_for_run(cls, run: PayrollRun) -> dict:
        preview = cls.preview_run(run)
        return preview["posting_status"]

    @classmethod
    def posting_status_for_fnf(cls, settlement: FnFSettlement) -> dict:
        preview = cls.preview_fnf(settlement)
        return preview["posting_status"]

    @classmethod
    def _finalize_preview(
        cls,
        *,
        source_type: str,
        source_id: int,
        source_number: str,
        status: str,
        posting_date,
        raw_rows: list[dict],
        issues: list[dict],
        narration: str,
        is_reversal: bool,
        txn_type: str,
        txn_id: int,
        entity_id: int,
        entityfinid_id: int | None,
        subentity_id: int | None,
        voucher_no: str | None,
        voucher_date,
    ) -> dict:
        normalized_rows = cls._aggregate_rows(raw_rows, is_reversal=is_reversal)
        debit_total = q2(sum(row["amount"] for row in normalized_rows if row["entry_side"] == "DEBIT"))
        credit_total = q2(sum(row["amount"] for row in normalized_rows if row["entry_side"] == "CREDIT"))
        if debit_total != credit_total:
            issues.append(
                cls._issue(
                    code="DEBIT_CREDIT_MISMATCH",
                    message=f"Journal preview is unbalanced. Debit total {debit_total} does not match credit total {credit_total}.",
                    source=source_type.lower(),
                )
            )
        blocking = [issue for issue in issues if issue["severity"] == "blocking"]
        warnings = [issue for issue in issues if issue["severity"] == "warning"]
        jl_inputs = [
            JLInput(
                account_id=row["account_id"],
                drcr=row["entry_side"] == "DEBIT",
                amount=row["amount"],
                description=row["description"],
            )
            for row in normalized_rows
        ]
        serializable_rows = [
            {
                **row,
                "amount": f"{row['amount']:.2f}",
            }
            for row in normalized_rows
        ]
        return {
            "source_type": source_type,
            "source_id": source_id,
            "source_number": source_number,
            "status": status,
            "posting_date": posting_date,
            "journal_rows": serializable_rows,
            "totals": {
                "debit_total": f"{debit_total:.2f}",
                "credit_total": f"{credit_total:.2f}",
                "is_balanced": debit_total == credit_total,
                "row_count": len(serializable_rows),
            },
            "validation": {
                "is_valid": not blocking,
                "blocking_count": len(blocking),
                "warning_count": len(warnings),
                "issues": issues,
            },
            "posting_status": {
                "source_type": source_type,
                "source_id": source_id,
                "status": status,
                "posted": status in {getattr(PayrollRun.Status, "POSTED", "POSTED"), getattr(FnFSettlement.Status, "POSTED", "POSTED"), getattr(FnFSettlement.Status, "PAID", "PAID"), getattr(PayrollRun.Status, "REVERSED", "REVERSED")},
                "can_post": not blocking and status in {getattr(PayrollRun.Status, "APPROVED", "APPROVED"), getattr(FnFSettlement.Status, "APPROVED", "APPROVED")},
                "can_reverse": source_type == "PAYROLL_RUN" and status == PayrollRun.Status.POSTED,
                "is_reversal": is_reversal,
            },
            "posting": {
                "txn_type": txn_type,
                "txn_id": txn_id,
                "entity_id": entity_id,
                "entityfinid_id": entityfinid_id,
                "subentity_id": subentity_id,
                "voucher_no": voucher_no,
                "voucher_date": voucher_date,
                "posting_date": posting_date,
                "narration": narration,
                "jl_inputs": jl_inputs,
            },
        }

    @classmethod
    def _aggregate_rows(cls, raw_rows: Iterable[dict], *, is_reversal: bool) -> list[dict]:
        aggregated: dict[tuple, dict] = {}
        for row in raw_rows:
            drcr = not row["drcr"] if is_reversal else bool(row["drcr"])
            key = (
                row["account_id"],
                drcr,
                row["category"],
                row["description"],
            )
            if key not in aggregated:
                aggregated[key] = {
                    **row,
                    "drcr": drcr,
                    "entry_side": "DEBIT" if drcr else "CREDIT",
                    "amount": ZERO2,
                }
            aggregated[key]["amount"] = q2(aggregated[key]["amount"] + q2(row["amount"]))
        rows = [row for row in aggregated.values() if q2(row["amount"]) > ZERO2]
        rows.sort(key=lambda item: (item["entry_side"], item["account_name"], item["category"]))
        for index, row in enumerate(rows, start=1):
            row["sequence"] = index
        return rows

    @classmethod
    def _journal_row(
        cls,
        *,
        account_obj: account,
        drcr: bool,
        amount: Decimal,
        description: str,
        category: str,
        source_reference: str,
        component_code: str = "",
    ) -> dict:
        return {
            "account_id": account_obj.id,
            "account_name": account_obj.effective_accounting_name or account_obj.accountname or f"Account {account_obj.id}",
            "ledger_id": account_obj.ledger_id,
            "ledger_name": getattr(account_obj.ledger, "name", "") if account_obj.ledger_id else "",
            "drcr": drcr,
            "amount": q2(amount),
            "description": description,
            "category": category,
            "source_reference": source_reference,
            "component_code": component_code,
        }

    @classmethod
    def _policy_for_run(cls, run: PayrollRun) -> PayrollLedgerPolicy:
        if run.ledger_policy_version_id:
            return run.ledger_policy_version
        return PayrollLedgerPolicy.objects.get(
            entity_id=run.entity_id,
            entityfinid_id=run.entityfinid_id,
            subentity_id=run.subentity_id,
            is_active=True,
        )

    @classmethod
    def _posting_source_run(cls, run: PayrollRun) -> PayrollRun:
        if run.reversed_run_id and not run.employee_runs.exists():
            return (
                PayrollRun.objects.select_related("payroll_period", "ledger_policy_version")
                .prefetch_related(
                    "employee_runs__contract_payroll_profile__hrms_contract__employee",
                    "employee_runs__components__component",
                    "employee_runs__components__component_posting_version",
                )
                .get(pk=run.reversed_run_id)
            )
        return run

    @staticmethod
    def _iter_run_rows(run: PayrollRun):
        return run.employee_runs.select_related(
            "contract_payroll_profile__hrms_contract__employee"
        ).prefetch_related("components__component", "components__component_posting_version")

    @staticmethod
    def _component_semantic_code(component_row) -> str:
        snapshot = component_row.calculation_basis_snapshot or {}
        if snapshot.get("semantic_code"):
            return str(snapshot.get("semantic_code") or "")
        metadata = component_row.metadata or {}
        component_snapshot = metadata.get("component_snapshot") or {}
        if component_snapshot.get("semantic_code"):
            return str(component_snapshot.get("semantic_code") or "")
        return str(getattr(getattr(component_row, "component", None), "semantic_code", "") or "")

    @classmethod
    def _resolve_component_expense_account(
        cls,
        *,
        entity_id: int,
        posting_map,
        issues: list[dict],
        component_code: str,
    ) -> _ResolvedAccount:
        account_obj = getattr(posting_map, "expense_account", None)
        if account_obj is None:
            issues.append(
                cls._issue(
                    code="MISSING_COMPONENT_EXPENSE_MAPPING",
                    message=f"Missing expense ledger mapping for component '{component_code}'.",
                    source="component",
                    component_code=component_code,
                )
            )
            return _ResolvedAccount(account=None, resolution_type="component_posting", resolution_code="")
        cls._validate_account(entity_id=entity_id, account_obj=account_obj, issues=issues, component_code=component_code)
        return _ResolvedAccount(account=account_obj, resolution_type="component_posting", resolution_code="expense_account")

    @classmethod
    def _resolve_run_component_liability_account(
        cls,
        *,
        run: PayrollRun,
        policy: PayrollLedgerPolicy,
        posting_map,
        component_type: str,
        semantic_code: str,
        issues: list[dict],
        component_code: str,
    ) -> _ResolvedAccount:
        explicit = getattr(posting_map, "liability_account", None) or getattr(posting_map, "payable_account", None)
        if explicit is not None:
            cls._validate_account(entity_id=run.entity_id, account_obj=explicit, issues=issues, component_code=component_code)
            return _ResolvedAccount(account=explicit, resolution_type="component_posting", resolution_code="liability_account")
        if semantic_code in cls.STATUTORY_STATIC_CODES:
            return cls._resolve_static_account(
                entity_id=run.entity_id,
                subentity_id=run.subentity_id,
                code=cls.STATUTORY_STATIC_CODES[semantic_code],
                issues=issues,
                component_code=component_code,
            )
        if component_type != PayrollComponentKind.EMPLOYER_CONTRIBUTION:
            issues.append(
                cls._issue(
                    code="MISSING_COMPONENT_LIABILITY_MAPPING",
                    message=f"Missing liability ledger mapping for component '{component_code}'.",
                    source="component",
                    component_code=component_code,
                )
            )
            return _ResolvedAccount(account=None, resolution_type="component_posting", resolution_code="")
        if policy.employer_contribution_payable_account_id:
            account_obj = policy.employer_contribution_payable_account
            cls._validate_account(entity_id=run.entity_id, account_obj=account_obj, issues=issues, component_code=component_code)
            return _ResolvedAccount(account=account_obj, resolution_type="ledger_policy", resolution_code="employer_contribution_payable_account")
        return cls._resolve_static_account(
            entity_id=run.entity_id,
            subentity_id=run.subentity_id,
            code="PAYROLL_EMPLOYER_CONTRIBUTION_PAYABLE",
            issues=issues,
            component_code=component_code,
        )

    @classmethod
    def _resolve_run_salary_payable_account(
        cls,
        *,
        run: PayrollRun,
        policy: PayrollLedgerPolicy,
        issues: list[dict],
    ) -> _ResolvedAccount:
        if policy.salary_payable_account_id:
            account_obj = policy.salary_payable_account
            cls._validate_account(entity_id=run.entity_id, account_obj=account_obj, issues=issues, component_code="SALARY_PAYABLE")
            return _ResolvedAccount(account=account_obj, resolution_type="ledger_policy", resolution_code="salary_payable_account")
        return cls._resolve_static_account(
            entity_id=run.entity_id,
            subentity_id=run.subentity_id,
            code="PAYROLL_SALARY_PAYABLE",
            issues=issues,
            component_code="SALARY_PAYABLE",
        )

    @classmethod
    def _resolve_run_reimbursement_account(
        cls,
        *,
        run: PayrollRun,
        policy: PayrollLedgerPolicy,
        issues: list[dict],
    ) -> _ResolvedAccount:
        if policy.reimbursement_payable_account_id:
            account_obj = policy.reimbursement_payable_account
            cls._validate_account(entity_id=run.entity_id, account_obj=account_obj, issues=issues, component_code="REIMBURSEMENT_PAYABLE")
            return _ResolvedAccount(account=account_obj, resolution_type="ledger_policy", resolution_code="reimbursement_payable_account")
        return cls._resolve_static_account(
            entity_id=run.entity_id,
            subentity_id=run.subentity_id,
            code="PAYROLL_REIMBURSEMENT_PAYABLE",
            issues=issues,
            component_code="REIMBURSEMENT_PAYABLE",
        )

    @classmethod
    def _resolve_fnf_component_posting(cls, *, settlement: FnFSettlement, component) -> PayrollComponentPosting | None:
        if component is None:
            return None
        return (
            PayrollComponentPosting.objects.filter(
                entity_id=settlement.entity_id,
                entityfinid_id=settlement.entityfinid_id,
                subentity_id=settlement.subentity_id,
                component=component,
                is_active=True,
                effective_from__lte=settlement.settlement_date,
            )
            .filter(effective_to__isnull=True)
            .order_by("-version_no", "-effective_from", "-id")
            .first()
            or PayrollComponentPosting.objects.filter(
                entity_id=settlement.entity_id,
                entityfinid_id=settlement.entityfinid_id,
                subentity_id=settlement.subentity_id,
                component=component,
                is_active=True,
                effective_from__lte=settlement.settlement_date,
                effective_to__gte=settlement.settlement_date,
            )
            .order_by("-version_no", "-effective_from", "-id")
            .first()
        )

    @classmethod
    def _resolve_fnf_component_liability_account(
        cls,
        *,
        settlement: FnFSettlement,
        posting_map,
        component_type: str,
        semantic_code: str,
        issues: list[dict],
        component_code: str,
    ) -> _ResolvedAccount:
        explicit = getattr(posting_map, "liability_account", None) or getattr(posting_map, "payable_account", None)
        if explicit is not None:
            cls._validate_account(entity_id=settlement.entity_id, account_obj=explicit, issues=issues, component_code=component_code)
            return _ResolvedAccount(account=explicit, resolution_type="component_posting", resolution_code="liability_account")
        if semantic_code in cls.STATUTORY_STATIC_CODES:
            return cls._resolve_static_account(
                entity_id=settlement.entity_id,
                subentity_id=settlement.subentity_id,
                code=cls.STATUTORY_STATIC_CODES[semantic_code],
                issues=issues,
                component_code=component_code,
            )
        if component_type != FnFSettlementComponentType.EMPLOYER_CONTRIBUTION:
            issues.append(
                cls._issue(
                    code="MISSING_COMPONENT_LIABILITY_MAPPING",
                    message=f"Missing liability ledger mapping for component '{component_code}'.",
                    source="component",
                    component_code=component_code,
                )
            )
            return _ResolvedAccount(account=None, resolution_type="component_posting", resolution_code="")
        return cls._resolve_static_account(
            entity_id=settlement.entity_id,
            subentity_id=settlement.subentity_id,
            code="PAYROLL_EMPLOYER_CONTRIBUTION_PAYABLE",
            issues=issues,
            component_code=component_code,
        )

    @classmethod
    def _resolve_static_account(
        cls,
        *,
        entity_id: int,
        subentity_id: int | None,
        code: str,
        issues: list[dict],
        component_code: str,
    ) -> _ResolvedAccount:
        if not StaticAccount.objects.filter(code=code, is_active=True).exists():
            issues.append(
                cls._issue(
                    code="MISSING_STATIC_ACCOUNT_DEFINITION",
                    message=f"Static account definition '{code}' is not seeded in posting master data.",
                    source="static_account",
                    component_code=component_code,
                )
            )
            return _ResolvedAccount(account=None, resolution_type="static_account", resolution_code=code)
        mapping = (
            EntityStaticAccountMap.objects.filter(
                entity_id=entity_id,
                is_active=True,
                static_account__code=code,
                static_account__is_active=True,
            )
            .filter(Q(sub_entity_id=subentity_id) | Q(sub_entity__isnull=True))
            .select_related("account", "ledger")
            .order_by("-sub_entity_id", "-effective_from", "-id")
            .first()
        )
        if not mapping or not mapping.account_id:
            issues.append(
                cls._issue(
                    code="MISSING_STATIC_ACCOUNT_MAPPING",
                    message=f"Static account mapping '{code}' is missing for this entity.",
                    source="static_account",
                    component_code=component_code,
                )
            )
            return _ResolvedAccount(account=None, resolution_type="static_account", resolution_code=code)
        account_obj = mapping.account or account.objects.select_related("ledger").filter(pk=mapping.account_id).first()
        if account_obj is None:
            issues.append(
                cls._issue(
                    code="MISSING_STATIC_ACCOUNT_MAPPING",
                    message=f"Static account mapping '{code}' points to an account that no longer exists.",
                    source="static_account",
                    component_code=component_code,
                )
            )
            return _ResolvedAccount(account=None, resolution_type="static_account", resolution_code=code)
        cls._validate_account(entity_id=entity_id, account_obj=account_obj, issues=issues, component_code=component_code)
        return _ResolvedAccount(account=account_obj, resolution_type="static_account", resolution_code=code)

    @classmethod
    def _validate_account(
        cls,
        *,
        entity_id: int,
        account_obj: account,
        issues: list[dict],
        component_code: str,
    ) -> None:
        if account_obj.entity_id not in (None, entity_id):
            issues.append(
                cls._issue(
                    code="ACCOUNT_ENTITY_MISMATCH",
                    message=f"Mapped account '{account_obj.accountname}' does not belong to the payroll entity.",
                    source="account",
                    component_code=component_code,
                )
            )
        if not bool(getattr(account_obj, "isactive", True)):
            issues.append(
                cls._issue(
                    code="INACTIVE_LEDGER_MAPPING",
                    message=f"Mapped account '{account_obj.accountname}' is inactive.",
                    source="account",
                    component_code=component_code,
                )
            )
        if not account_obj.ledger_id:
            issues.append(
                cls._issue(
                    code="MISSING_LEDGER_LINK",
                    message=f"Mapped account '{account_obj.accountname}' is not linked to a ledger.",
                    source="account",
                    component_code=component_code,
                )
            )

    @staticmethod
    def _issue(*, code: str, message: str, source: str, component_code: str = "", severity: str = "blocking") -> dict:
        return {
            "severity": severity,
            "code": code,
            "message": message,
            "source": source,
            "component_code": component_code,
        }

    @staticmethod
    def _raise_for_blocking_issues(preview: dict) -> None:
        issues = preview.get("validation", {}).get("issues") or []
        blocking = [issue for issue in issues if issue.get("severity") == "blocking"]
        if blocking:
            raise ValueError(
                {
                    "posting_validation_issues": blocking,
                    "detail": "Posting validation failed. Resolve the journal issues and try again.",
                }
            )

    @staticmethod
    def _fnf_prefix(settlement: FnFSettlement) -> str:
        return settlement.settlement_number or f"FnF Settlement {settlement.id}"


class FnFSettlementComponentType:
    EARNING = "EARNING"
    DEDUCTION = "DEDUCTION"
    EMPLOYER_CONTRIBUTION = "EMPLOYER_CONTRIBUTION"
    REIMBURSEMENT = "REIMBURSEMENT"
    RECOVERY = "RECOVERY"


class PayrollComponentKind:
    EMPLOYER_CONTRIBUTION = "EMPLOYER_CONTRIBUTION"
