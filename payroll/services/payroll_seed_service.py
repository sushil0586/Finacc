from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.color import no_style
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from entity.models import Entity, EntityFinancialYear
from financial.models import account
from payments.models import PaymentMode
from payroll.models import (
    PayrollComponent,
    PayrollLedgerPolicy,
    SalaryStructure,
    SalaryStructureLine,
    SalaryStructureVersion,
)
from rbac.models import Menu, Permission
from rbac.seeding import PayrollRBACSeedService

User = get_user_model()


@dataclass
class SeedSectionResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "notes": self.notes,
        }


class PayrollSeedService:
    SEED_MARKER = "payroll_master_seed"
    TEMPLATE_CODE = "IND_MONTHLY_CTC_STD"
    TEMPLATE_NAME = "India Monthly CTC Standard"
    LEDGER_POLICY_CODE = "DEFAULT_PAYROLL_LEDGER_POLICY"

    COMPONENT_SPECS = (
        {
            "code": "BASIC",
            "name": "Basic Salary",
            "semantic_code": PayrollComponent.SemanticCode.BASIC_PAY,
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 100,
            "description": "Seeded default payroll earning component.",
        },
        {
            "code": "HRA",
            "name": "House Rent Allowance",
            "semantic_code": PayrollComponent.SemanticCode.HRA,
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 110,
            "description": "Seeded default payroll earning component.",
        },
        {
            "code": "SPECIAL_ALLOWANCE",
            "name": "Special Allowance",
            "semantic_code": PayrollComponent.SemanticCode.SPECIAL_ALLOWANCE,
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 120,
            "description": "Seeded default payroll earning component.",
        },
        {
            "code": "OTHER_ALLOWANCE",
            "name": "Other Allowance",
            "semantic_code": PayrollComponent.SemanticCode.OTHER_EARNING,
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 130,
            "description": "Seeded default payroll earning component.",
        },
        {
            "code": "BONUS",
            "name": "Bonus",
            "semantic_code": PayrollComponent.SemanticCode.OTHER_EARNING,
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 200,
            "description": "Seeded default payroll variable earning component.",
        },
        {
            "code": "INCENTIVE",
            "name": "Incentive",
            "semantic_code": PayrollComponent.SemanticCode.OTHER_EARNING,
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 210,
            "description": "Seeded default payroll variable earning component.",
        },
        {
            "code": "COMMISSION",
            "name": "Commission",
            "semantic_code": PayrollComponent.SemanticCode.OTHER_EARNING,
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 220,
            "description": "Seeded default payroll variable earning component.",
        },
        {
            "code": "ARREARS",
            "name": "Arrears",
            "semantic_code": PayrollComponent.SemanticCode.OTHER_EARNING,
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 230,
            "description": "Seeded default payroll earning adjustment component.",
        },
        {
            "code": "OVERTIME",
            "name": "Overtime",
            "semantic_code": PayrollComponent.SemanticCode.OTHER_EARNING,
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 240,
            "description": "Seeded default payroll overtime component.",
        },
        {
            "code": "LEAVE_ENCASHMENT",
            "name": "Leave Encashment",
            "semantic_code": PayrollComponent.SemanticCode.OTHER_EARNING,
            "component_type": PayrollComponent.ComponentType.EARNING,
            "posting_behavior": PayrollComponent.PostingBehavior.GROSS_EARNING,
            "is_taxable": True,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 250,
            "description": "Seeded default leave encashment component.",
        },
        {
            "code": "REIMBURSEMENT",
            "name": "Reimbursement",
            "semantic_code": PayrollComponent.SemanticCode.REIMBURSEMENT,
            "component_type": PayrollComponent.ComponentType.REIMBURSEMENT,
            "posting_behavior": PayrollComponent.PostingBehavior.REIMBURSEMENT,
            "is_taxable": False,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 500,
            "description": "Seeded default reimbursement component.",
        },
        {
            "code": "LOAN_RECOVERY",
            "name": "Loan Recovery",
            "semantic_code": PayrollComponent.SemanticCode.RECOVERY,
            "component_type": PayrollComponent.ComponentType.RECOVERY,
            "posting_behavior": PayrollComponent.PostingBehavior.RECOVERY,
            "is_taxable": False,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 510,
            "description": "Seeded default recovery component.",
        },
        {
            "code": "ADVANCE_RECOVERY",
            "name": "Advance Recovery",
            "semantic_code": PayrollComponent.SemanticCode.RECOVERY,
            "component_type": PayrollComponent.ComponentType.RECOVERY,
            "posting_behavior": PayrollComponent.PostingBehavior.RECOVERY,
            "is_taxable": False,
            "is_statutory": False,
            "affects_net_pay": True,
            "default_sequence": 520,
            "description": "Seeded default recovery component.",
        },
        {
            "code": "PF_EMPLOYEE",
            "name": "Provident Fund Employee",
            "semantic_code": PayrollComponent.SemanticCode.PF_EMPLOYEE,
            "component_type": PayrollComponent.ComponentType.DEDUCTION,
            "posting_behavior": PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            "is_taxable": False,
            "is_statutory": True,
            "affects_net_pay": True,
            "default_sequence": 300,
            "description": "Seeded default payroll deduction component.",
        },
        {
            "code": "PF_EMPLOYER",
            "name": "Provident Fund Employer",
            "semantic_code": PayrollComponent.SemanticCode.PF_EMPLOYER,
            "component_type": PayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION,
            "posting_behavior": PayrollComponent.PostingBehavior.EMPLOYER_LIABILITY,
            "is_taxable": False,
            "is_statutory": True,
            "affects_net_pay": False,
            "default_sequence": 400,
            "description": "Seeded default employer contribution component.",
        },
        {
            "code": "PROFESSIONAL_TAX",
            "name": "Professional Tax",
            "semantic_code": PayrollComponent.SemanticCode.PT,
            "component_type": PayrollComponent.ComponentType.DEDUCTION,
            "posting_behavior": PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            "is_taxable": False,
            "is_statutory": True,
            "affects_net_pay": True,
            "default_sequence": 310,
            "description": "Seeded default payroll deduction component.",
        },
        {
            "code": "ESI_EMPLOYEE",
            "name": "ESI Employee",
            "semantic_code": PayrollComponent.SemanticCode.ESI_EMPLOYEE,
            "component_type": PayrollComponent.ComponentType.DEDUCTION,
            "posting_behavior": PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            "is_taxable": False,
            "is_statutory": True,
            "affects_net_pay": True,
            "default_sequence": 305,
            "description": "Seeded default payroll deduction component.",
        },
        {
            "code": "ESI_EMPLOYER",
            "name": "ESI Employer",
            "semantic_code": PayrollComponent.SemanticCode.ESI_EMPLOYER,
            "component_type": PayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION,
            "posting_behavior": PayrollComponent.PostingBehavior.EMPLOYER_LIABILITY,
            "is_taxable": False,
            "is_statutory": True,
            "affects_net_pay": False,
            "default_sequence": 405,
            "description": "Seeded default employer contribution component.",
        },
        {
            "code": "TDS",
            "name": "Tax Deducted at Source",
            "semantic_code": PayrollComponent.SemanticCode.TDS,
            "component_type": PayrollComponent.ComponentType.DEDUCTION,
            "posting_behavior": PayrollComponent.PostingBehavior.EMPLOYEE_LIABILITY,
            "is_taxable": False,
            "is_statutory": True,
            "affects_net_pay": True,
            "default_sequence": 320,
            "description": "Seeded default payroll deduction component.",
        },
    )
    TEMPLATE_SPECS = (
        {
            "code": "IND_MONTHLY_CTC_STD",
            "name": "India Monthly CTC Standard",
            "salary_mode": "ctc",
            "proration_basis": "calendar_days",
            "rounding_policy": "half_up",
            "lines": (
                {"code": "BASIC", "sequence": 100, "calculation_basis": SalaryStructureLine.CalculationBasis.PERCENT_OF_CTC, "rate": Decimal("40.0000")},
                {"code": "HRA", "sequence": 110, "calculation_basis": SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT, "basis_component_code": "BASIC", "rate": Decimal("40.0000")},
                {"code": "SPECIAL_ALLOWANCE", "sequence": 120, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT},
                {"code": "BONUS", "sequence": 200, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "recurrence_frequency": SalaryStructureLine.RecurrenceFrequency.QUARTERLY, "compensation_bucket": SalaryStructureLine.CompensationBucket.VARIABLE_PAY, "ctc_treatment": SalaryStructureLine.CTCTreatment.TARGET_ONLY, "gross_treatment": SalaryStructureLine.GrossTreatment.EXCLUDED},
                {"code": "INCENTIVE", "sequence": 210, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.VARIABLE_PAY},
                {"code": "PF_EMPLOYEE", "sequence": 300, "calculation_basis": SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT, "basis_component_code": "BASIC", "rate": Decimal("12.0000"), "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
                {"code": "PF_EMPLOYER", "sequence": 400, "calculation_basis": SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT, "basis_component_code": "BASIC", "rate": Decimal("12.0000"), "compensation_bucket": SalaryStructureLine.CompensationBucket.EMPLOYER_COST, "gross_treatment": SalaryStructureLine.GrossTreatment.EXCLUDED},
                {"code": "ESI_EMPLOYEE", "sequence": 305, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
                {"code": "ESI_EMPLOYER", "sequence": 405, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.EMPLOYER_COST, "gross_treatment": SalaryStructureLine.GrossTreatment.EXCLUDED},
                {"code": "PROFESSIONAL_TAX", "sequence": 310, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
                {"code": "TDS", "sequence": 320, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
                {"code": "REIMBURSEMENT", "sequence": 500, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.REIMBURSEMENT, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
                {"code": "LOAN_RECOVERY", "sequence": 510, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.RECOVERY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
            ),
        },
        {
            "code": "IND_MONTHLY_GROSS_STD",
            "name": "India Monthly Gross Standard",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "lines": (
                {"code": "BASIC", "sequence": 100, "calculation_basis": SalaryStructureLine.CalculationBasis.PERCENT_OF_CTC, "rate": Decimal("40.0000")},
                {"code": "HRA", "sequence": 110, "calculation_basis": SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT, "basis_component_code": "BASIC", "rate": Decimal("40.0000")},
                {"code": "SPECIAL_ALLOWANCE", "sequence": 120, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT},
                {"code": "PF_EMPLOYEE", "sequence": 300, "calculation_basis": SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT, "basis_component_code": "BASIC", "rate": Decimal("12.0000"), "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
                {"code": "PF_EMPLOYER", "sequence": 400, "calculation_basis": SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT, "basis_component_code": "BASIC", "rate": Decimal("12.0000"), "compensation_bucket": SalaryStructureLine.CompensationBucket.EMPLOYER_COST, "gross_treatment": SalaryStructureLine.GrossTreatment.EXCLUDED},
                {"code": "ESI_EMPLOYEE", "sequence": 305, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
                {"code": "ESI_EMPLOYER", "sequence": 405, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.EMPLOYER_COST, "gross_treatment": SalaryStructureLine.GrossTreatment.EXCLUDED},
                {"code": "PROFESSIONAL_TAX", "sequence": 310, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
                {"code": "TDS", "sequence": 320, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
            ),
        },
        {
            "code": "IND_CONSULTANT_STD",
            "name": "India Consultant Standard",
            "salary_mode": "gross",
            "proration_basis": "payable_days",
            "rounding_policy": "half_up",
            "lines": (
                {"code": "BASIC", "sequence": 100, "calculation_basis": SalaryStructureLine.CalculationBasis.PERCENT_OF_CTC, "rate": Decimal("100.0000")},
                {"code": "BONUS", "sequence": 200, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "recurrence_frequency": SalaryStructureLine.RecurrenceFrequency.YEARLY, "compensation_bucket": SalaryStructureLine.CompensationBucket.VARIABLE_PAY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED, "gross_treatment": SalaryStructureLine.GrossTreatment.EXCLUDED},
                {"code": "INCENTIVE", "sequence": 210, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.VARIABLE_PAY},
                {"code": "REIMBURSEMENT", "sequence": 500, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.REIMBURSEMENT, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
                {"code": "TDS", "sequence": 320, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
            ),
        },
        {
            "code": "IND_ATTENDANCE_WORKER_STD",
            "name": "India Attendance Worker Standard",
            "salary_mode": "gross",
            "proration_basis": "attendance_days",
            "rounding_policy": "half_up",
            "lines": (
                {"code": "BASIC", "sequence": 100, "calculation_basis": SalaryStructureLine.CalculationBasis.PERCENT_OF_CTC, "rate": Decimal("60.0000")},
                {"code": "HRA", "sequence": 110, "calculation_basis": SalaryStructureLine.CalculationBasis.PERCENT_OF_COMPONENT, "basis_component_code": "BASIC", "rate": Decimal("20.0000")},
                {"code": "OTHER_ALLOWANCE", "sequence": 130, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT},
                {"code": "OVERTIME", "sequence": 240, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.VARIABLE_PAY},
                {"code": "ARREARS", "sequence": 230, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.VARIABLE_PAY},
                {"code": "ESI_EMPLOYEE", "sequence": 305, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
                {"code": "ESI_EMPLOYER", "sequence": 405, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.EMPLOYER_COST, "gross_treatment": SalaryStructureLine.GrossTreatment.EXCLUDED},
                {"code": "PROFESSIONAL_TAX", "sequence": 310, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
                {"code": "TDS", "sequence": 320, "calculation_basis": SalaryStructureLine.CalculationBasis.INPUT, "compensation_bucket": SalaryStructureLine.CompensationBucket.STATUTORY, "ctc_treatment": SalaryStructureLine.CTCTreatment.EXCLUDED},
            ),
        },
    )

    PAYMENT_MODE_SPECS = (
        {"paymentmodecode": "BANK_TRANSFER", "paymentmode": "Bank Transfer", "iscash": False},
        {"paymentmodecode": "CASH", "paymentmode": "Cash", "iscash": True},
        {"paymentmodecode": "CHEQUE", "paymentmode": "Cheque", "iscash": False},
    )

    @classmethod
    def _base_policy_defaults(cls, *, salary_mode: str, proration_basis: str, rounding_policy: str) -> dict:
        flat = {
            "country_code": "IN",
            "salary_mode": salary_mode,
            "proration_basis": proration_basis,
            "rounding_policy": rounding_policy,
            "pf_wage_cap": "15000.00",
            "pf_employee_rate": "12.00",
            "pf_employer_rate": "12.00",
            "professional_tax_threshold": "15000.00",
            "professional_tax_amount": "200.00",
            "esi_wage_threshold": "21000.00",
            "esi_employee_rate": "0.75",
            "esi_employer_rate": "3.25",
            "tds_default_remaining_periods": "12",
            "tds_projection_rate": "10.00",
            "tds_projection_rate_old_regime": "10.00",
            "tds_projection_rate_new_regime": "12.00",
            "tds_standard_deduction_old_regime": "50000.00",
            "tds_standard_deduction_new_regime": "50000.00",
            "tds_old_regime_slabs": [
                {"upto": "250000.00", "rate": "0.00"},
                {"upto": "500000.00", "rate": "5.00"},
                {"upto": "1000000.00", "rate": "20.00"},
                {"rate": "30.00"},
            ],
            "tds_new_regime_slabs": [
                {"upto": "400000.00", "rate": "0.00"},
                {"upto": "800000.00", "rate": "5.00"},
                {"upto": "1200000.00", "rate": "10.00"},
                {"upto": "1600000.00", "rate": "15.00"},
                {"upto": "2000000.00", "rate": "20.00"},
                {"upto": "2400000.00", "rate": "25.00"},
                {"rate": "30.00"},
            ],
            "tds_rebate_threshold_old_regime": "500000.00",
            "tds_rebate_max_old_regime": "12500.00",
            "tds_rebate_threshold_new_regime": "1200000.00",
            "tds_rebate_max_new_regime": "60000.00",
            "tds_old_regime_surcharge_slabs": [
                {"upto": "5000000.00", "rate": "0.00"},
                {"upto": "10000000.00", "rate": "10.00"},
                {"upto": "20000000.00", "rate": "15.00"},
                {"upto": "50000000.00", "rate": "25.00"},
                {"rate": "37.00"},
            ],
            "tds_new_regime_surcharge_slabs": [
                {"upto": "5000000.00", "rate": "0.00"},
                {"upto": "10000000.00", "rate": "10.00"},
                {"upto": "20000000.00", "rate": "15.00"},
                {"upto": "50000000.00", "rate": "25.00"},
                {"rate": "25.00"},
            ],
            "tds_health_education_cess_rate": "4.00",
            "tds_apply_marginal_relief": True,
            "tds_allow_80c_old_regime": True,
            "tds_allow_80d_old_regime": True,
            "tds_allow_hra_exemption_old_regime": True,
            "tds_require_verified_hra_evidence_for_approval": False,
            "tds_require_verified_tax_declarations_for_approval": False,
            "tds_80c_cap": "150000.00",
            "tds_80d_cap": "25000.00",
        }
        return {
            **flat,
            "compensation_policy": {
                "country_code": flat["country_code"],
                "salary_mode": flat["salary_mode"],
                "proration_basis": flat["proration_basis"],
                "rounding_policy": flat["rounding_policy"],
            },
            "statutory_policy": {
                "pf": {
                    "wage_cap": flat["pf_wage_cap"],
                    "employee_rate": flat["pf_employee_rate"],
                    "employer_rate": flat["pf_employer_rate"],
                },
                "professional_tax": {
                    "threshold": flat["professional_tax_threshold"],
                    "amount": flat["professional_tax_amount"],
                },
                "esi": {
                    "wage_threshold": flat["esi_wage_threshold"],
                    "employee_rate": flat["esi_employee_rate"],
                    "employer_rate": flat["esi_employer_rate"],
                },
            },
            "tax_policy": {
                "code": "IN_TDS",
                "version": "FY2026_27_V1",
                "financial_year": "FY 2026-27",
                "effective_from": "2026-04-01",
                "tds": {
                    "default_remaining_periods": flat["tds_default_remaining_periods"],
                    "projection_rate": flat["tds_projection_rate"],
                    "projection_rate_old_regime": flat["tds_projection_rate_old_regime"],
                    "projection_rate_new_regime": flat["tds_projection_rate_new_regime"],
                    "standard_deduction_old_regime": flat["tds_standard_deduction_old_regime"],
                    "standard_deduction_new_regime": flat["tds_standard_deduction_new_regime"],
                    "allow_80c_old_regime": flat["tds_allow_80c_old_regime"],
                    "allow_80d_old_regime": flat["tds_allow_80d_old_regime"],
                    "allow_hra_exemption_old_regime": flat["tds_allow_hra_exemption_old_regime"],
                    "cap_80c": flat["tds_80c_cap"],
                    "cap_80d": flat["tds_80d_cap"],
                    "old_regime_slabs": flat["tds_old_regime_slabs"],
                    "new_regime_slabs": flat["tds_new_regime_slabs"],
                    "rebate_threshold_old_regime": flat["tds_rebate_threshold_old_regime"],
                    "rebate_max_old_regime": flat["tds_rebate_max_old_regime"],
                    "rebate_threshold_new_regime": flat["tds_rebate_threshold_new_regime"],
                    "rebate_max_new_regime": flat["tds_rebate_max_new_regime"],
                    "old_regime_surcharge_slabs": flat["tds_old_regime_surcharge_slabs"],
                    "new_regime_surcharge_slabs": flat["tds_new_regime_surcharge_slabs"],
                    "health_education_cess_rate": flat["tds_health_education_cess_rate"],
                    "apply_marginal_relief": flat["tds_apply_marginal_relief"],
                }
            },
            "review_policy": {
                "require_verified_hra_evidence_for_approval": flat["tds_require_verified_hra_evidence_for_approval"],
                "require_verified_tax_declarations_for_approval": flat["tds_require_verified_tax_declarations_for_approval"],
            },
        }

    @classmethod
    def _template_line_defaults(cls, *, line_spec: dict, component_map: dict) -> dict:
        return {
            "sequence": line_spec["sequence"],
            "rule_mode": line_spec.get("rule_mode", SalaryStructureLine.RuleMode.STANDARD),
            "calculation_basis": line_spec.get("calculation_basis", SalaryStructureLine.CalculationBasis.INPUT),
            "basis_component": component_map.get(line_spec["basis_component_code"]) if line_spec.get("basis_component_code") else None,
            "rate": line_spec.get("rate", Decimal("0.0000")),
            "fixed_amount": line_spec.get("fixed_amount", Decimal("0.00")),
            "is_pro_rated": line_spec.get("is_pro_rated", True),
            "is_override_allowed": line_spec.get("is_override_allowed", True),
            "is_active": line_spec.get("is_active", True),
            "recurrence_frequency": line_spec.get("recurrence_frequency", SalaryStructureLine.RecurrenceFrequency.MONTHLY),
            "compensation_bucket": line_spec.get("compensation_bucket", SalaryStructureLine.CompensationBucket.FIXED_PAY),
            "ctc_treatment": line_spec.get("ctc_treatment", SalaryStructureLine.CTCTreatment.INCLUDED),
            "gross_treatment": line_spec.get("gross_treatment", SalaryStructureLine.GrossTreatment.INCLUDED),
            "rule_json": line_spec.get("rule_json"),
        }

    @classmethod
    @transaction.atomic
    def seed_all(cls, *, entity_id: int | None = None) -> dict:
        summary = {
            "payment_modes": cls.seed_payment_modes(),
            "payroll_components": cls.seed_payroll_components(entity_id=entity_id),
            "salary_structure_templates": cls.seed_salary_structure_templates(entity_id=entity_id),
            "ledger_policies": cls.seed_ledger_policies(entity_id=entity_id),
            "readiness_checks": cls.seed_readiness_checks(),
            "rbac_permissions": cls.seed_rbac_permissions(),
            "menu_entries": cls.seed_menu_entries(),
        }
        totals = defaultdict(int)
        for result in summary.values():
            totals["created"] += result["created"]
            totals["updated"] += result["updated"]
            totals["skipped"] += result["skipped"]
        summary["totals"] = dict(totals)
        return summary

    @classmethod
    def seed_payment_modes(cls) -> dict:
        result = SeedSectionResult()
        actor = cls._default_actor()
        if not actor:
            result.skipped = len(cls.PAYMENT_MODE_SPECS)
            result.notes.append("No user exists to attribute PaymentMode.createdby; payment mode seeding skipped.")
            return result.as_dict()

        cls._repair_pk_sequence(PaymentMode)

        for row in cls.PAYMENT_MODE_SPECS:
            mode = PaymentMode.objects.filter(paymentmodecode=row["paymentmodecode"]).first()
            if not mode:
                PaymentMode.objects.create(createdby=actor, **row)
                result.created += 1
                continue

            if not cls._is_seeded_metadata(getattr(mode, "paymentmode", "")):
                result.skipped += 1
                result.notes.append(
                    f"Skipped payment mode {row['paymentmodecode']} because it already exists and was not seed-tagged."
                )
                continue

            changed = False
            for field in ("paymentmode", "iscash"):
                if getattr(mode, field) != row[field]:
                    setattr(mode, field, row[field])
                    changed = True
            if changed:
                mode.save(update_fields=["paymentmode", "iscash"])
                result.updated += 1
            else:
                result.skipped += 1
        return result.as_dict()

    @classmethod
    def seed_payroll_components(cls, *, entity_id: int | None = None) -> dict:
        result = SeedSectionResult()
        for entity in cls._active_entities(entity_id=entity_id):
            for spec in cls.COMPONENT_SPECS:
                component = PayrollComponent.objects.filter(entity=entity, code=spec["code"]).first()
                if not component:
                    create_kwargs = dict(spec)
                    create_kwargs["description"] = cls._seed_text(spec["description"])
                    PayrollComponent.objects.create(
                        entity=entity,
                        **create_kwargs,
                    )
                    result.created += 1
                    continue

                if not cls._is_seeded_metadata(component.description):
                    result.skipped += 1
                    continue

                changed = False
                for field, value in spec.items():
                    if field == "description":
                        value = cls._seed_text(value)
                    if getattr(component, field) != value:
                        setattr(component, field, value)
                        changed = True
                if changed:
                    component.save()
                    result.updated += 1
                else:
                    result.skipped += 1
        if result.created == 0 and result.updated == 0 and result.skipped == 0:
            result.notes.append("No active entities found for payroll component seeding.")
        return result.as_dict()

    @classmethod
    def seed_salary_structure_templates(cls, *, entity_id: int | None = None) -> dict:
        result = SeedSectionResult()
        actor = cls._default_actor()
        for entity in cls._active_entities(entity_id=entity_id):
            for template_spec in cls.TEMPLATE_SPECS:
                structure = SalaryStructure.objects.filter(
                    entity=entity,
                    entityfinid__isnull=True,
                    subentity__isnull=True,
                    code=template_spec["code"],
                ).first()
                if not structure:
                    structure = SalaryStructure.objects.create(
                        entity=entity,
                        code=template_spec["code"],
                        name=template_spec["name"],
                        status=SalaryStructure.Status.ACTIVE,
                        notes=cls._seed_text(f"Seeded {template_spec['name']} salary structure template."),
                        is_active=True,
                        is_template=True,
                    )
                    result.created += 1
                elif cls._is_seeded_metadata(structure.notes):
                    changed = False
                    desired = {
                        "name": template_spec["name"],
                        "status": SalaryStructure.Status.ACTIVE,
                        "notes": cls._seed_text(f"Seeded {template_spec['name']} salary structure template."),
                        "is_active": True,
                        "is_template": True,
                    }
                    for field, value in desired.items():
                        if getattr(structure, field) != value:
                            setattr(structure, field, value)
                            changed = True
                    if changed:
                        structure.save()
                        result.updated += 1
                    else:
                        result.skipped += 1
                else:
                    result.skipped += 1
                    continue

                desired_policy = cls._base_policy_defaults(
                    salary_mode=template_spec["salary_mode"],
                    proration_basis=template_spec["proration_basis"],
                    rounding_policy=template_spec["rounding_policy"],
                )
                version, created = SalaryStructureVersion.objects.get_or_create(
                    salary_structure=structure,
                    version_no=1,
                    defaults={
                        "effective_from": timezone.localdate(),
                        "status": SalaryStructureVersion.Status.APPROVED,
                        "calculation_policy_json": desired_policy,
                        "approved_by": actor,
                        "approved_at": timezone.now() if actor else None,
                        "notes": cls._seed_text(f"Seeded {template_spec['name']} structure version."),
                    },
                )
                if created:
                    result.created += 1
                else:
                    changed = False
                    desired_status = SalaryStructureVersion.Status.APPROVED
                    desired_notes = cls._seed_text(f"Seeded {template_spec['name']} structure version.")
                    if version.status != desired_status:
                        version.status = desired_status
                        changed = True
                    if version.notes != desired_notes and cls._is_seeded_metadata(version.notes):
                        version.notes = desired_notes
                        changed = True
                    if version.calculation_policy_json != desired_policy:
                        version.calculation_policy_json = desired_policy
                        changed = True
                    if actor and version.approved_by_id is None:
                        version.approved_by = actor
                        version.approved_at = version.approved_at or timezone.now()
                        changed = True
                    if changed:
                        version.save()
                        result.updated += 1
                    else:
                        result.skipped += 1

                if structure.current_version_id != version.id:
                    structure.current_version = version
                    structure.save(update_fields=["current_version"])

                component_map = {
                    component.code: component
                    for component in PayrollComponent.objects.filter(
                        entity=entity,
                        code__in=[row["code"] for row in template_spec["lines"]],
                    )
                }
                for line_spec in template_spec["lines"]:
                    component = component_map.get(line_spec["code"])
                    if not component:
                        result.skipped += 1
                        result.notes.append(
                            f"Template line {line_spec['code']} skipped for entity={entity.id} structure={template_spec['code']} because component is missing."
                        )
                        continue
                    line, line_created = SalaryStructureLine.objects.get_or_create(
                        salary_structure=structure,
                        salary_structure_version=version,
                        component=component,
                        defaults=cls._template_line_defaults(line_spec=line_spec, component_map=component_map),
                    )
                    if line_created:
                        result.created += 1
                        continue
                    changed = False
                    desired_line = {
                        "salary_structure": structure,
                        "salary_structure_version": version,
                        **cls._template_line_defaults(line_spec=line_spec, component_map=component_map),
                    }
                    for field, value in desired_line.items():
                        current = getattr(line, field)
                        compare_value = value.id if hasattr(value, "id") else value
                        current_value = current.id if hasattr(current, "id") else current
                        if current_value != compare_value:
                            setattr(line, field, value)
                            changed = True
                    if changed:
                        line.save()
                        result.updated += 1
                    else:
                        result.skipped += 1
        if result.created == 0 and result.updated == 0 and result.skipped == 0:
            result.notes.append("No active entities found for salary structure template seeding.")
        return result.as_dict()

    @classmethod
    def seed_ledger_policies(cls, *, entity_id: int | None = None) -> dict:
        result = SeedSectionResult()
        actor = cls._default_actor()
        for entity in cls._active_entities(entity_id=entity_id):
            salary_payable_account = cls._find_salary_payable_account(entity=entity)
            if not salary_payable_account:
                result.notes.append(
                    f"Skipped ledger policy for entity={entity.id} because no Salary Payable account placeholder was found."
                )
                result.skipped += cls._active_financial_years(entity).count() or 1
                continue
            for entityfinid in cls._active_financial_years(entity):
                policy, created = PayrollLedgerPolicy.objects.get_or_create(
                    entity=entity,
                    entityfinid=entityfinid,
                    subentity=None,
                    policy_code=cls.LEDGER_POLICY_CODE,
                    version_no=1,
                    defaults={
                        "salary_payable_account": salary_payable_account,
                        "is_active": True,
                        "effective_from": timezone.localdate(),
                        "policy_json": {
                            "seed": cls.SEED_MARKER,
                            "note": "Seeded default payroll ledger policy placeholder.",
                        },
                        "approved_by": actor,
                        "approved_at": timezone.now() if actor else None,
                    },
                )
                if created:
                    result.created += 1
                    continue

                if not cls._is_seeded_policy(policy.policy_json):
                    result.skipped += 1
                    continue

                changed = False
                if policy.salary_payable_account_id != salary_payable_account.id:
                    policy.salary_payable_account = salary_payable_account
                    changed = True
                if not policy.is_active:
                    policy.is_active = True
                    changed = True
                desired_policy_json = {
                    **(policy.policy_json or {}),
                    "seed": cls.SEED_MARKER,
                    "note": "Seeded default payroll ledger policy placeholder.",
                }
                if policy.policy_json != desired_policy_json:
                    policy.policy_json = desired_policy_json
                    changed = True
                if actor and policy.approved_by_id is None:
                    policy.approved_by = actor
                    policy.approved_at = policy.approved_at or timezone.now()
                    changed = True
                if changed:
                    policy.save()
                    result.updated += 1
                else:
                    result.skipped += 1
        if result.created == 0 and result.updated == 0 and result.skipped == 0:
            result.notes.append("No active entities found for payroll ledger policy seeding.")
        return result.as_dict()

    @classmethod
    def seed_readiness_checks(cls) -> dict:
        result = SeedSectionResult()
        result.skipped = 4
        result.notes.append(
            "Readiness checks are currently service-driven; no standalone readiness-check master table exists to seed."
        )
        return result.as_dict()

    @classmethod
    def seed_rbac_permissions(cls) -> dict:
        result = SeedSectionResult()
        before_codes = set(
            Permission.objects.filter(code__in=[code for code, *_rest in PayrollRBACSeedService.PERMISSION_SPECS]).values_list(
                "code", flat=True
            )
        )
        catalog = PayrollRBACSeedService.seed_global_catalog()
        result.created = len([code for code in catalog["permissions"] if code not in before_codes])
        result.skipped = len(catalog["permissions"]) - result.created
        result.notes.append("Payroll RBAC permissions ensured via PayrollRBACSeedService global catalog.")
        return result.as_dict()

    @classmethod
    def seed_menu_entries(cls) -> dict:
        result = SeedSectionResult()
        before_codes = set(Menu.objects.filter(code__in=[spec["code"] for spec in PayrollRBACSeedService.MENU_SPECS]).values_list("code", flat=True))
        catalog = PayrollRBACSeedService.seed_global_catalog()
        result.created = len([code for code in catalog["menus"] if code not in before_codes])
        result.skipped = len(catalog["menus"]) - result.created
        result.notes.append("Payroll menu entries ensured via PayrollRBACSeedService global catalog.")
        return result.as_dict()

    @classmethod
    def _active_entities(cls, *, entity_id: int | None = None):
        qs = Entity.objects.filter(isactive=True).order_by("id")
        if entity_id is not None:
            qs = qs.filter(id=entity_id)
        return qs

    @classmethod
    def _active_financial_years(cls, entity: Entity):
        return EntityFinancialYear.objects.filter(entity=entity, isactive=True).order_by("id")

    @classmethod
    def _default_actor(cls):
        actor = User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()
        if actor:
            return actor
        return User.objects.filter(is_active=True).order_by("id").first()

    @classmethod
    def _find_salary_payable_account(cls, *, entity: Entity):
        return (
            account.objects.filter(entity=entity)
            .filter(
                Q(accountname__icontains="salary payable")
                | Q(accountname__icontains="payroll payable")
                | Q(ledger__name__icontains="salary payable")
                | Q(ledger__name__icontains="payroll payable")
            )
            .order_by("id")
            .first()
        )

    @classmethod
    def _seed_text(cls, text: str) -> str:
        return f"{text} [{cls.SEED_MARKER}]"

    @classmethod
    def _is_seeded_metadata(cls, value: str | None) -> bool:
        return cls.SEED_MARKER in (value or "")

    @classmethod
    def _is_seeded_policy(cls, payload: dict | None) -> bool:
        return (payload or {}).get("seed") == cls.SEED_MARKER

    @classmethod
    def _repair_pk_sequence(cls, model):
        """Bring a Postgres sequence back in sync with the table's max primary key.

        Some older environments were populated through manual inserts or legacy
        migration flows, which can leave the underlying sequence behind the
        current max(id). Running Django's sequence reset SQL here keeps seeders
        idempotent without requiring manual DBA cleanup first.
        """
        statements = connection.ops.sequence_reset_sql(no_style(), [model])
        if not statements:
            return
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
