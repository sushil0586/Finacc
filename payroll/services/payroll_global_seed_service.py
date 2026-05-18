from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from payroll.models import (
    GlobalPayrollComponent,
    GlobalPayrollComponentGroup,
    GlobalSalaryStructureTemplate,
    GlobalSalaryStructureTemplateLine,
)
from payroll.services.payroll_global_catalog_service import GlobalPayrollCatalogService
from payroll.services.payroll_global_template_service import GlobalSalaryTemplateService


@dataclass
class SeedSectionResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
        }


@dataclass
class GlobalSeedExecutionResult:
    country: str
    dry_run: bool = False
    force: bool = False
    only: str = "all"
    groups: SeedSectionResult = field(default_factory=SeedSectionResult)
    components: SeedSectionResult = field(default_factory=SeedSectionResult)
    templates: SeedSectionResult = field(default_factory=SeedSectionResult)
    lines: SeedSectionResult = field(default_factory=SeedSectionResult)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "country": self.country,
            "dry_run": self.dry_run,
            "force": self.force,
            "only": self.only,
            "groups": self.groups.as_dict(),
            "components": self.components.as_dict(),
            "templates": self.templates.as_dict(),
            "lines": self.lines.as_dict(),
            "warnings": self.warnings,
            "conflicts": self.conflicts,
        }


class PayrollGlobalSeedService:
    GROUPS = (
        {
            "code": "EARNINGS",
            "name": "Earnings",
            "description": "System default earnings group for Indian payroll setup.",
            "group_type": GlobalPayrollComponentGroup.GroupType.EARNINGS,
            "sort_order": 100,
        },
        {
            "code": "DEDUCTIONS",
            "name": "Deductions",
            "description": "System default deductions group for Indian payroll setup.",
            "group_type": GlobalPayrollComponentGroup.GroupType.DEDUCTIONS,
            "sort_order": 200,
        },
        {
            "code": "EMPLOYER_CONTRIBUTIONS",
            "name": "Employer Contributions",
            "description": "System default employer contributions group for Indian payroll setup.",
            "group_type": GlobalPayrollComponentGroup.GroupType.EMPLOYER_CONTRIBUTIONS,
            "sort_order": 300,
        },
        {
            "code": "REIMBURSEMENTS",
            "name": "Reimbursements",
            "description": "System default reimbursements group for Indian payroll setup.",
            "group_type": GlobalPayrollComponentGroup.GroupType.REIMBURSEMENTS,
            "sort_order": 400,
        },
        {
            "code": "RECOVERIES",
            "name": "Recoveries",
            "description": "System default recoveries group for Indian payroll setup.",
            "group_type": GlobalPayrollComponentGroup.GroupType.RECOVERIES,
            "sort_order": 500,
        },
        {
            "code": "INFORMATIONAL",
            "name": "Informational",
            "description": "System default informational group for Indian payroll setup.",
            "group_type": GlobalPayrollComponentGroup.GroupType.INFORMATIONAL,
            "sort_order": 600,
        },
    )

    COMPONENTS = (
        {
            "group": "EARNINGS",
            "code": "BASIC",
            "name": "Basic Salary",
            "description": "Core fixed earning used as a configurable basis for other components.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.PERCENTAGE,
            "default_sequence": 100,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": True,
            "pro_rata": True,
            "default_formula": "config.basic_percentage_of_ctc * CTC",
            "default_rule_json": {"rule_type": "percentage", "basis": ["CTC"], "config_key": "basic_percentage_of_ctc"},
        },
        {
            "group": "EARNINGS",
            "code": "HRA",
            "name": "House Rent Allowance",
            "description": "Configurable allowance commonly based on basic salary.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.PERCENTAGE,
            "default_sequence": 110,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": True,
            "pro_rata": True,
            "default_formula": "config.hra_percentage_of_basic * BASIC",
            "default_rule_json": {"rule_type": "percentage", "basis": ["BASIC"], "config_key": "hra_percentage_of_basic"},
        },
        {
            "group": "EARNINGS",
            "code": "DA",
            "name": "Dearness Allowance",
            "description": "Configurable dearness allowance used in worker and factory structures.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.FIXED,
            "default_sequence": 120,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": True,
            "pro_rata": True,
        },
        {
            "group": "EARNINGS",
            "code": "SPECIAL_ALLOWANCE",
            "name": "Special Allowance",
            "description": "Flexible balancing component for configurable salary structures.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.MANUAL,
            "default_sequence": 130,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": True,
            "pro_rata": True,
            "default_rule_json": {"rule_type": "balancing", "balance_against": ["CTC"]},
        },
        {
            "group": "EARNINGS",
            "code": "CONVEYANCE_ALLOWANCE",
            "name": "Conveyance Allowance",
            "description": "Configurable conveyance allowance.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.FIXED,
            "default_sequence": 140,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": True,
            "pro_rata": True,
        },
        {
            "group": "EARNINGS",
            "code": "MEDICAL_ALLOWANCE",
            "name": "Medical Allowance",
            "description": "Configurable medical allowance.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.FIXED,
            "default_sequence": 150,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": True,
            "pro_rata": True,
        },
        {
            "group": "EARNINGS",
            "code": "EDUCATION_ALLOWANCE",
            "name": "Education Allowance",
            "description": "Configurable education allowance.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.FIXED,
            "default_sequence": 160,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": True,
            "pro_rata": True,
        },
        {
            "group": "EARNINGS",
            "code": "FOOD_ALLOWANCE",
            "name": "Food Allowance",
            "description": "Configurable food allowance.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.FIXED,
            "default_sequence": 170,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": True,
            "pro_rata": True,
        },
        {
            "group": "EARNINGS",
            "code": "BONUS",
            "name": "Bonus",
            "description": "Configurable bonus component with optional statutory relevance.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 180,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": True,
            "pro_rata": False,
            "statutory_code": GlobalPayrollComponent.StatutoryCode.BONUS,
            "default_formula": "config.bonus_formula",
            "default_rule_json": {
                "rule_type": "statutory_or_policy",
                "scheme_code": "BONUS",
                "recurrence_frequency": "YEARLY",
                "applicability_mode": "configurable",
            },
        },
        {
            "group": "EARNINGS",
            "code": "PERFORMANCE_INCENTIVE",
            "name": "Performance Incentive",
            "description": "Configurable performance-linked incentive component.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 190,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "default_formula": "config.performance_incentive_formula",
            "default_rule_json": {"rule_type": "variable_pay", "compensation_bucket": "VARIABLE_PAY"},
        },
        {
            "group": "EARNINGS",
            "code": "SALES_INCENTIVE",
            "name": "Sales Incentive",
            "description": "Configurable sales-linked incentive component.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 200,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "default_formula": "config.sales_incentive_formula",
            "default_rule_json": {"rule_type": "variable_pay", "compensation_bucket": "VARIABLE_PAY"},
        },
        {
            "group": "EARNINGS",
            "code": "OVERTIME",
            "name": "Overtime",
            "description": "Configurable overtime earning based on captured overtime inputs.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 210,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": False,
            "attendance_dependent": True,
            "overtime_dependent": True,
            "pro_rata": False,
            "default_formula": "config.overtime_rate * OVERTIME_HOURS",
            "default_rule_json": {"rule_type": "input_driven", "input_code": "OVERTIME_HOURS", "rate_key": "overtime_rate"},
        },
        {
            "group": "EARNINGS",
            "code": "LEAVE_ENCASHMENT",
            "name": "Leave Encashment",
            "description": "Configurable leave encashment earning.",
            "component_type": GlobalPayrollComponent.ComponentType.EARNING,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 220,
            "taxable": True,
            "affects_gross": True,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "default_formula": "config.leave_encashment_formula",
            "default_rule_json": {"rule_type": "input_driven", "input_code": "leave_balance"},
        },
        {
            "group": "DEDUCTIONS",
            "code": "PF_EMPLOYEE",
            "name": "Provident Fund Employee",
            "description": "Employee PF deduction as a configurable statutory component.",
            "component_type": GlobalPayrollComponent.ComponentType.DEDUCTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 300,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "statutory_code": GlobalPayrollComponent.StatutoryCode.PF,
            "default_formula": "config.pf_employee_formula",
            "default_rule_json": {"rule_type": "statutory_or_policy", "scheme_code": "PF", "basis": ["BASIC"], "applicability_mode": "configurable"},
        },
        {
            "group": "DEDUCTIONS",
            "code": "ESI_EMPLOYEE",
            "name": "ESI Employee",
            "description": "Employee ESI deduction as a configurable statutory component.",
            "component_type": GlobalPayrollComponent.ComponentType.DEDUCTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 310,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "statutory_code": GlobalPayrollComponent.StatutoryCode.ESI,
            "default_formula": "config.esi_employee_formula",
            "default_rule_json": {"rule_type": "statutory_or_policy", "scheme_code": "ESI", "eligibility_mode": "configurable"},
        },
        {
            "group": "DEDUCTIONS",
            "code": "PROFESSIONAL_TAX",
            "name": "Professional Tax",
            "description": "State-configurable professional tax deduction.",
            "component_type": GlobalPayrollComponent.ComponentType.DEDUCTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.SLAB,
            "default_sequence": 320,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "statutory_code": GlobalPayrollComponent.StatutoryCode.PT,
            "default_formula": "config.professional_tax_rule",
            "default_rule_json": {"rule_type": "statutory_or_policy", "scheme_code": "PT", "state_dependent": True, "applicability_mode": "configurable"},
        },
        {
            "group": "DEDUCTIONS",
            "code": "TDS",
            "name": "Tax Deducted at Source",
            "description": "Tax withholding deduction driven by policy and declarations.",
            "component_type": GlobalPayrollComponent.ComponentType.DEDUCTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 330,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "statutory_code": GlobalPayrollComponent.StatutoryCode.TDS,
            "default_formula": "config.tds_formula",
            "default_rule_json": {"rule_type": "statutory_or_policy", "scheme_code": "TDS", "regime_dependent": True, "applicability_mode": "configurable"},
        },
        {
            "group": "DEDUCTIONS",
            "code": "LWF_EMPLOYEE",
            "name": "Labour Welfare Fund Employee",
            "description": "Employee labour welfare fund deduction.",
            "component_type": GlobalPayrollComponent.ComponentType.DEDUCTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.SLAB,
            "default_sequence": 340,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "statutory_code": GlobalPayrollComponent.StatutoryCode.LWF,
            "default_formula": "config.lwf_employee_rule",
            "default_rule_json": {"rule_type": "statutory_or_policy", "scheme_code": "LWF", "state_dependent": True, "applicability_mode": "configurable"},
        },
        {
            "group": "DEDUCTIONS",
            "code": "LOAN_DEDUCTION",
            "name": "Loan Deduction",
            "description": "Configurable loan repayment deduction.",
            "component_type": GlobalPayrollComponent.ComponentType.DEDUCTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.MANUAL,
            "default_sequence": 350,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
        },
        {
            "group": "DEDUCTIONS",
            "code": "ADVANCE_DEDUCTION",
            "name": "Advance Deduction",
            "description": "Configurable salary advance recovery deduction.",
            "component_type": GlobalPayrollComponent.ComponentType.DEDUCTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.MANUAL,
            "default_sequence": 360,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
        },
        {
            "group": "DEDUCTIONS",
            "code": "LATE_DEDUCTION",
            "name": "Late Deduction",
            "description": "Configurable late-attendance deduction.",
            "component_type": GlobalPayrollComponent.ComponentType.DEDUCTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 370,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "attendance_dependent": True,
            "pro_rata": False,
            "default_formula": "config.late_deduction_formula",
            "default_rule_json": {"rule_type": "input_driven", "input_code": "late_instances"},
        },
        {
            "group": "DEDUCTIONS",
            "code": "LOP_DEDUCTION",
            "name": "Loss of Pay Deduction",
            "description": "Configurable loss-of-pay deduction.",
            "component_type": GlobalPayrollComponent.ComponentType.DEDUCTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 380,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "attendance_dependent": True,
            "lop_dependent": True,
            "pro_rata": False,
            "default_formula": "config.lop_deduction_formula",
            "default_rule_json": {"rule_type": "input_driven", "input_code": "LOP_DAYS"},
        },
        {
            "group": "EMPLOYER_CONTRIBUTIONS",
            "code": "PF_EMPLOYER",
            "name": "Provident Fund Employer",
            "description": "Employer PF contribution as a configurable statutory component.",
            "component_type": GlobalPayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 400,
            "taxable": False,
            "affects_gross": False,
            "affects_net": False,
            "affects_ctc": True,
            "pro_rata": False,
            "statutory_code": GlobalPayrollComponent.StatutoryCode.PF,
            "default_formula": "config.pf_employer_formula",
            "default_rule_json": {"rule_type": "statutory_or_policy", "scheme_code": "PF", "basis": ["BASIC"], "applicability_mode": "configurable"},
        },
        {
            "group": "EMPLOYER_CONTRIBUTIONS",
            "code": "ESI_EMPLOYER",
            "name": "ESI Employer",
            "description": "Employer ESI contribution as a configurable statutory component.",
            "component_type": GlobalPayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 410,
            "taxable": False,
            "affects_gross": False,
            "affects_net": False,
            "affects_ctc": True,
            "pro_rata": False,
            "statutory_code": GlobalPayrollComponent.StatutoryCode.ESI,
            "default_formula": "config.esi_employer_formula",
            "default_rule_json": {"rule_type": "statutory_or_policy", "scheme_code": "ESI", "eligibility_mode": "configurable"},
        },
        {
            "group": "EMPLOYER_CONTRIBUTIONS",
            "code": "LWF_EMPLOYER",
            "name": "Labour Welfare Fund Employer",
            "description": "Employer labour welfare fund contribution.",
            "component_type": GlobalPayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.SLAB,
            "default_sequence": 420,
            "taxable": False,
            "affects_gross": False,
            "affects_net": False,
            "affects_ctc": True,
            "pro_rata": False,
            "statutory_code": GlobalPayrollComponent.StatutoryCode.LWF,
            "default_formula": "config.lwf_employer_rule",
            "default_rule_json": {"rule_type": "statutory_or_policy", "scheme_code": "LWF", "state_dependent": True, "applicability_mode": "configurable"},
        },
        {
            "group": "EMPLOYER_CONTRIBUTIONS",
            "code": "GRATUITY_PROVISION",
            "name": "Gratuity Provision",
            "description": "Employer gratuity provision as a configurable statutory component.",
            "component_type": GlobalPayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 430,
            "taxable": False,
            "affects_gross": False,
            "affects_net": False,
            "affects_ctc": True,
            "pro_rata": False,
            "statutory_code": GlobalPayrollComponent.StatutoryCode.GRATUITY,
            "default_formula": "config.gratuity_formula",
            "default_rule_json": {"rule_type": "statutory_or_policy", "scheme_code": "GRATUITY", "applicability_mode": "configurable"},
        },
        {
            "group": "EMPLOYER_CONTRIBUTIONS",
            "code": "BONUS_PROVISION",
            "name": "Bonus Provision",
            "description": "Employer-side bonus provision component.",
            "component_type": GlobalPayrollComponent.ComponentType.EMPLOYER_CONTRIBUTION,
            "calculation_type": GlobalPayrollComponent.CalculationType.FORMULA,
            "default_sequence": 440,
            "taxable": False,
            "affects_gross": False,
            "affects_net": False,
            "affects_ctc": True,
            "pro_rata": False,
            "statutory_code": GlobalPayrollComponent.StatutoryCode.BONUS,
            "default_formula": "config.bonus_provision_formula",
            "default_rule_json": {"rule_type": "statutory_or_policy", "scheme_code": "BONUS", "applicability_mode": "configurable"},
        },
        {
            "group": "REIMBURSEMENTS",
            "code": "FUEL_REIMBURSEMENT",
            "name": "Fuel Reimbursement",
            "description": "Configurable fuel reimbursement component.",
            "component_type": GlobalPayrollComponent.ComponentType.REIMBURSEMENT,
            "calculation_type": GlobalPayrollComponent.CalculationType.MANUAL,
            "default_sequence": 500,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "default_rule_json": {"rule_type": "input_driven", "input_code": "fuel_reimbursement_amount"},
        },
        {
            "group": "REIMBURSEMENTS",
            "code": "MOBILE_REIMBURSEMENT",
            "name": "Mobile Reimbursement",
            "description": "Configurable mobile reimbursement component.",
            "component_type": GlobalPayrollComponent.ComponentType.REIMBURSEMENT,
            "calculation_type": GlobalPayrollComponent.CalculationType.MANUAL,
            "default_sequence": 510,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "default_rule_json": {"rule_type": "input_driven", "input_code": "mobile_reimbursement_amount"},
        },
        {
            "group": "REIMBURSEMENTS",
            "code": "TRAVEL_REIMBURSEMENT",
            "name": "Travel Reimbursement",
            "description": "Configurable travel reimbursement component.",
            "component_type": GlobalPayrollComponent.ComponentType.REIMBURSEMENT,
            "calculation_type": GlobalPayrollComponent.CalculationType.MANUAL,
            "default_sequence": 520,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "default_rule_json": {"rule_type": "input_driven", "input_code": "travel_reimbursement_amount"},
        },
        {
            "group": "REIMBURSEMENTS",
            "code": "MEDICAL_REIMBURSEMENT",
            "name": "Medical Reimbursement",
            "description": "Configurable medical reimbursement component.",
            "component_type": GlobalPayrollComponent.ComponentType.REIMBURSEMENT,
            "calculation_type": GlobalPayrollComponent.CalculationType.MANUAL,
            "default_sequence": 530,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "default_rule_json": {"rule_type": "input_driven", "input_code": "medical_reimbursement_amount"},
        },
        {
            "group": "REIMBURSEMENTS",
            "code": "INTERNET_REIMBURSEMENT",
            "name": "Internet Reimbursement",
            "description": "Configurable internet reimbursement component.",
            "component_type": GlobalPayrollComponent.ComponentType.REIMBURSEMENT,
            "calculation_type": GlobalPayrollComponent.CalculationType.MANUAL,
            "default_sequence": 540,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
            "default_rule_json": {"rule_type": "input_driven", "input_code": "internet_reimbursement_amount"},
        },
        {
            "group": "RECOVERIES",
            "code": "ASSET_RECOVERY",
            "name": "Asset Recovery",
            "description": "Recovery component for lost or unreturned assets.",
            "component_type": GlobalPayrollComponent.ComponentType.RECOVERY,
            "calculation_type": GlobalPayrollComponent.CalculationType.MANUAL,
            "default_sequence": 600,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
        },
        {
            "group": "RECOVERIES",
            "code": "NOTICE_PAY_RECOVERY",
            "name": "Notice Pay Recovery",
            "description": "Recovery component for notice shortfall.",
            "component_type": GlobalPayrollComponent.ComponentType.RECOVERY,
            "calculation_type": GlobalPayrollComponent.CalculationType.MANUAL,
            "default_sequence": 610,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
        },
        {
            "group": "RECOVERIES",
            "code": "EXCESS_PAYMENT_RECOVERY",
            "name": "Excess Payment Recovery",
            "description": "Recovery component for previously overpaid amounts.",
            "component_type": GlobalPayrollComponent.ComponentType.RECOVERY,
            "calculation_type": GlobalPayrollComponent.CalculationType.MANUAL,
            "default_sequence": 620,
            "taxable": False,
            "affects_gross": False,
            "affects_net": True,
            "affects_ctc": False,
            "pro_rata": False,
        },
        {
            "group": "INFORMATIONAL",
            "code": "CTC",
            "name": "Cost to Company",
            "description": "Informational component representing total cost to company.",
            "component_type": GlobalPayrollComponent.ComponentType.INFORMATIONAL,
            "calculation_type": GlobalPayrollComponent.CalculationType.DERIVED,
            "default_sequence": 900,
            "taxable": False,
            "affects_gross": False,
            "affects_net": False,
            "affects_ctc": False,
            "pro_rata": False,
            "default_formula": "sum(ctc_components)",
        },
        {
            "group": "INFORMATIONAL",
            "code": "GROSS_SALARY",
            "name": "Gross Salary",
            "description": "Informational component representing gross salary.",
            "component_type": GlobalPayrollComponent.ComponentType.INFORMATIONAL,
            "calculation_type": GlobalPayrollComponent.CalculationType.DERIVED,
            "default_sequence": 910,
            "taxable": False,
            "affects_gross": False,
            "affects_net": False,
            "affects_ctc": False,
            "pro_rata": False,
            "default_formula": "sum(gross_earnings)",
        },
        {
            "group": "INFORMATIONAL",
            "code": "NET_PAY",
            "name": "Net Pay",
            "description": "Informational component representing final payable net amount.",
            "component_type": GlobalPayrollComponent.ComponentType.INFORMATIONAL,
            "calculation_type": GlobalPayrollComponent.CalculationType.DERIVED,
            "default_sequence": 920,
            "taxable": False,
            "affects_gross": False,
            "affects_net": False,
            "affects_ctc": False,
            "pro_rata": False,
            "default_formula": "gross_salary - total_deductions + reimbursements - recoveries",
        },
        {
            "group": "INFORMATIONAL",
            "code": "PAYABLE_DAYS",
            "name": "Payable Days",
            "description": "Informational component for payable days input/output.",
            "component_type": GlobalPayrollComponent.ComponentType.INFORMATIONAL,
            "calculation_type": GlobalPayrollComponent.CalculationType.DERIVED,
            "default_sequence": 930,
            "taxable": False,
            "affects_gross": False,
            "affects_net": False,
            "affects_ctc": False,
            "attendance_dependent": True,
            "pro_rata": False,
        },
        {
            "group": "INFORMATIONAL",
            "code": "LOP_DAYS",
            "name": "Loss of Pay Days",
            "description": "Informational component for LOP days input/output.",
            "component_type": GlobalPayrollComponent.ComponentType.INFORMATIONAL,
            "calculation_type": GlobalPayrollComponent.CalculationType.DERIVED,
            "default_sequence": 940,
            "taxable": False,
            "affects_gross": False,
            "affects_net": False,
            "affects_ctc": False,
            "attendance_dependent": True,
            "lop_dependent": True,
            "pro_rata": False,
        },
        {
            "group": "INFORMATIONAL",
            "code": "OVERTIME_HOURS",
            "name": "Overtime Hours",
            "description": "Informational component for overtime hours input/output.",
            "component_type": GlobalPayrollComponent.ComponentType.INFORMATIONAL,
            "calculation_type": GlobalPayrollComponent.CalculationType.DERIVED,
            "default_sequence": 950,
            "taxable": False,
            "affects_gross": False,
            "affects_net": False,
            "affects_ctc": False,
            "attendance_dependent": True,
            "overtime_dependent": True,
            "pro_rata": False,
        },
    )

    TEMPLATES = (
        {
            "code": "INDIA_SME_MONTHLY_STAFF",
            "name": "India SME Monthly Staff",
            "description": "Baseline monthly salaried staff template for India SMB onboarding.",
            "template_type": GlobalSalaryStructureTemplate.TemplateType.MONTHLY_STAFF,
            "pay_frequency": GlobalSalaryStructureTemplate.PayFrequency.MONTHLY,
            "is_default": True,
            "lines": [
                {"component": "BASIC", "sequence": 100, "calculation_type": "PERCENTAGE", "percentage_default": "40.0000", "formula": "config.basic_percentage_of_ctc * CTC", "taxable_override": True, "affects_gross_override": True, "affects_net_override": True, "affects_ctc_override": True},
                {"component": "HRA", "sequence": 110, "calculation_type": "PERCENTAGE", "percentage_default": "40.0000", "formula": "config.hra_percentage_of_basic * BASIC", "basis_components": ["BASIC"], "taxable_override": True, "affects_gross_override": True, "affects_net_override": True, "affects_ctc_override": True},
                {"component": "SPECIAL_ALLOWANCE", "sequence": 120, "calculation_type": "MANUAL", "rule_json": {"rule_type": "balancing", "balance_against": ["CTC"]}},
                {"component": "CONVEYANCE_ALLOWANCE", "sequence": 130, "calculation_type": "FIXED", "amount_default": "0.00"},
                {"component": "PF_EMPLOYEE", "sequence": 300, "calculation_type": "FORMULA", "percentage_default": "12.0000", "formula": "config.pf_employee_formula", "basis_components": ["BASIC"], "rule_json": {"scheme_code": "PF"}, "applicability_json": {"mode": "configurable", "condition_key": "if_pf_enabled"}},
                {"component": "ESI_EMPLOYEE", "sequence": 310, "calculation_type": "FORMULA", "formula": "config.esi_employee_formula", "rule_json": {"scheme_code": "ESI"}, "applicability_json": {"mode": "configurable", "condition_key": "if_esi_enabled"}},
                {"component": "PROFESSIONAL_TAX", "sequence": 320, "calculation_type": "SLAB", "formula": "config.professional_tax_rule", "rule_json": {"scheme_code": "PT"}, "applicability_json": {"mode": "configurable", "condition_key": "if_pt_enabled"}},
                {"component": "TDS", "sequence": 330, "calculation_type": "FORMULA", "formula": "config.tds_formula", "rule_json": {"scheme_code": "TDS"}, "applicability_json": {"mode": "configurable", "condition_key": "if_tds_enabled"}},
            ],
        },
        {
            "code": "INDIA_CTC_BASED_STAFF",
            "name": "India CTC Based Staff",
            "description": "CTC-led template for salaried staff with configurable employer contributions.",
            "template_type": GlobalSalaryStructureTemplate.TemplateType.CTC_BASED,
            "pay_frequency": GlobalSalaryStructureTemplate.PayFrequency.MONTHLY,
            "lines": [
                {"component": "BASIC", "sequence": 100, "calculation_type": "PERCENTAGE", "percentage_default": "40.0000", "formula": "config.basic_percentage_of_ctc * CTC"},
                {"component": "HRA", "sequence": 110, "calculation_type": "PERCENTAGE", "percentage_default": "40.0000", "formula": "config.hra_percentage_of_basic * BASIC", "basis_components": ["BASIC"]},
                {"component": "SPECIAL_ALLOWANCE", "sequence": 120, "calculation_type": "MANUAL", "rule_json": {"rule_type": "balancing", "balance_against": ["CTC"]}},
                {"component": "PF_EMPLOYEE", "sequence": 300, "calculation_type": "FORMULA", "percentage_default": "12.0000", "formula": "config.pf_employee_formula", "basis_components": ["BASIC"], "rule_json": {"scheme_code": "PF"}, "applicability_json": {"mode": "configurable", "condition_key": "if_pf_enabled"}},
                {"component": "PF_EMPLOYER", "sequence": 400, "calculation_type": "FORMULA", "percentage_default": "12.0000", "formula": "config.pf_employer_formula", "basis_components": ["BASIC"], "rule_json": {"scheme_code": "PF"}, "applicability_json": {"mode": "configurable", "condition_key": "if_pf_enabled"}},
                {"component": "ESI_EMPLOYEE", "sequence": 310, "calculation_type": "FORMULA", "formula": "config.esi_employee_formula", "rule_json": {"scheme_code": "ESI"}, "applicability_json": {"mode": "configurable", "condition_key": "if_esi_enabled"}},
                {"component": "ESI_EMPLOYER", "sequence": 410, "calculation_type": "FORMULA", "formula": "config.esi_employer_formula", "rule_json": {"scheme_code": "ESI"}, "applicability_json": {"mode": "configurable", "condition_key": "if_esi_enabled"}},
                {"component": "GRATUITY_PROVISION", "sequence": 430, "calculation_type": "FORMULA", "formula": "config.gratuity_formula", "rule_json": {"scheme_code": "GRATUITY"}, "applicability_json": {"mode": "configurable", "condition_key": "if_gratuity_enabled"}},
                {"component": "PROFESSIONAL_TAX", "sequence": 320, "calculation_type": "SLAB", "formula": "config.professional_tax_rule", "rule_json": {"scheme_code": "PT"}, "applicability_json": {"mode": "configurable", "condition_key": "if_pt_enabled"}},
                {"component": "TDS", "sequence": 330, "calculation_type": "FORMULA", "formula": "config.tds_formula", "rule_json": {"scheme_code": "TDS"}, "applicability_json": {"mode": "configurable", "condition_key": "if_tds_enabled"}},
            ],
        },
        {
            "code": "INDIA_FACTORY_WORKER",
            "name": "India Factory Worker",
            "description": "Factory worker template with overtime and configurable worker statutory defaults.",
            "template_type": GlobalSalaryStructureTemplate.TemplateType.FACTORY_WORKER,
            "pay_frequency": GlobalSalaryStructureTemplate.PayFrequency.MONTHLY,
            "lines": [
                {"component": "BASIC", "sequence": 100, "calculation_type": "FIXED", "amount_default": "0.00"},
                {"component": "DA", "sequence": 110, "calculation_type": "FIXED", "amount_default": "0.00"},
                {"component": "OVERTIME", "sequence": 210, "calculation_type": "FORMULA", "formula": "config.overtime_rate * OVERTIME_HOURS", "attendance_dependent": True, "lop_dependent": True, "rule_json": {"input_code": "OVERTIME_HOURS"}},
                {"component": "BONUS", "sequence": 220, "calculation_type": "FORMULA", "formula": "config.bonus_formula", "rule_json": {"scheme_code": "BONUS"}, "applicability_json": {"mode": "configurable", "condition_key": "if_bonus_enabled"}},
                {"component": "PF_EMPLOYEE", "sequence": 300, "calculation_type": "FORMULA", "percentage_default": "12.0000", "formula": "config.pf_employee_formula", "basis_components": ["BASIC"], "rule_json": {"scheme_code": "PF"}, "applicability_json": {"mode": "configurable", "condition_key": "if_pf_enabled"}},
                {"component": "PF_EMPLOYER", "sequence": 400, "calculation_type": "FORMULA", "percentage_default": "12.0000", "formula": "config.pf_employer_formula", "basis_components": ["BASIC"], "rule_json": {"scheme_code": "PF"}, "applicability_json": {"mode": "configurable", "condition_key": "if_pf_enabled"}},
                {"component": "ESI_EMPLOYEE", "sequence": 310, "calculation_type": "FORMULA", "formula": "config.esi_employee_formula", "rule_json": {"scheme_code": "ESI"}, "applicability_json": {"mode": "configurable", "condition_key": "if_esi_enabled"}},
                {"component": "ESI_EMPLOYER", "sequence": 410, "calculation_type": "FORMULA", "formula": "config.esi_employer_formula", "rule_json": {"scheme_code": "ESI"}, "applicability_json": {"mode": "configurable", "condition_key": "if_esi_enabled"}},
                {"component": "LWF_EMPLOYEE", "sequence": 340, "calculation_type": "SLAB", "formula": "config.lwf_employee_rule", "rule_json": {"scheme_code": "LWF"}, "applicability_json": {"mode": "configurable", "condition_key": "if_lwf_enabled"}},
                {"component": "LWF_EMPLOYER", "sequence": 420, "calculation_type": "SLAB", "formula": "config.lwf_employer_rule", "rule_json": {"scheme_code": "LWF"}, "applicability_json": {"mode": "configurable", "condition_key": "if_lwf_enabled"}},
                {"component": "PROFESSIONAL_TAX", "sequence": 320, "calculation_type": "SLAB", "formula": "config.professional_tax_rule", "rule_json": {"scheme_code": "PT"}, "applicability_json": {"mode": "configurable", "condition_key": "if_pt_enabled"}},
            ],
        },
        {
            "code": "INDIA_EXECUTIVE",
            "name": "India Executive",
            "description": "Executive template with reimbursement-friendly defaults.",
            "template_type": GlobalSalaryStructureTemplate.TemplateType.EXECUTIVE,
            "pay_frequency": GlobalSalaryStructureTemplate.PayFrequency.MONTHLY,
            "lines": [
                {"component": "BASIC", "sequence": 100, "calculation_type": "PERCENTAGE", "percentage_default": "35.0000", "formula": "config.basic_percentage_of_ctc * CTC"},
                {"component": "HRA", "sequence": 110, "calculation_type": "PERCENTAGE", "percentage_default": "40.0000", "formula": "config.hra_percentage_of_basic * BASIC", "basis_components": ["BASIC"]},
                {"component": "SPECIAL_ALLOWANCE", "sequence": 120, "calculation_type": "MANUAL", "rule_json": {"rule_type": "balancing", "balance_against": ["CTC"]}},
                {"component": "PERFORMANCE_INCENTIVE", "sequence": 190, "calculation_type": "FORMULA", "formula": "config.performance_incentive_formula", "rule_json": {"rule_type": "variable_pay", "compensation_bucket": "VARIABLE_PAY"}, "applicability_json": {"mode": "configurable", "condition_key": "if_performance_plan_enabled"}},
                {"component": "TDS", "sequence": 330, "calculation_type": "FORMULA", "formula": "config.tds_formula", "rule_json": {"scheme_code": "TDS"}, "applicability_json": {"mode": "configurable", "condition_key": "if_tds_enabled"}},
            ],
        },
        {
            "code": "INDIA_SALES_INCENTIVE",
            "name": "India Sales Incentive",
            "description": "Sales compensation template with incentive-led earnings mix.",
            "template_type": GlobalSalaryStructureTemplate.TemplateType.SALES_INCENTIVE,
            "pay_frequency": GlobalSalaryStructureTemplate.PayFrequency.MONTHLY,
            "lines": [
                {"component": "BASIC", "sequence": 100, "calculation_type": "PERCENTAGE", "percentage_default": "30.0000", "formula": "config.basic_percentage_of_ctc * CTC"},
                {"component": "HRA", "sequence": 110, "calculation_type": "PERCENTAGE", "percentage_default": "40.0000", "formula": "config.hra_percentage_of_basic * BASIC", "basis_components": ["BASIC"]},
                {"component": "SPECIAL_ALLOWANCE", "sequence": 120, "calculation_type": "MANUAL", "rule_json": {"rule_type": "balancing", "balance_against": ["CTC"]}},
                {"component": "SALES_INCENTIVE", "sequence": 200, "calculation_type": "FORMULA", "formula": "config.sales_incentive_formula", "rule_json": {"rule_type": "variable_pay", "compensation_bucket": "VARIABLE_PAY"}, "applicability_json": {"mode": "configurable", "condition_key": "if_sales_plan_enabled"}},
                {"component": "PERFORMANCE_INCENTIVE", "sequence": 210, "calculation_type": "FORMULA", "formula": "config.performance_incentive_formula", "rule_json": {"rule_type": "variable_pay", "compensation_bucket": "VARIABLE_PAY"}, "applicability_json": {"mode": "configurable", "condition_key": "if_performance_plan_enabled"}},
                {"component": "TDS", "sequence": 330, "calculation_type": "FORMULA", "formula": "config.tds_formula", "rule_json": {"scheme_code": "TDS"}, "applicability_json": {"mode": "configurable", "condition_key": "if_tds_enabled"}},
            ],
        },
        {
            "code": "INDIA_CONTRACTOR_FIXED_PAYOUT",
            "name": "India Contractor Fixed Payout",
            "description": "Simple contractor payout template with configurable withholding.",
            "template_type": GlobalSalaryStructureTemplate.TemplateType.CONTRACTOR,
            "pay_frequency": GlobalSalaryStructureTemplate.PayFrequency.MONTHLY,
            "lines": [
                {"component": "BASIC", "sequence": 100, "calculation_type": "FIXED", "amount_default": "0.00"},
                {"component": "TDS", "sequence": 330, "calculation_type": "FORMULA", "formula": "config.tds_formula", "rule_json": {"scheme_code": "TDS"}, "applicability_json": {"mode": "configurable", "condition_key": "if_tds_enabled"}},
            ],
        },
        {
            "code": "INDIA_INTERN_STIPEND",
            "name": "India Intern Stipend",
            "description": "Simple stipend template for interns with configurable withholding.",
            "template_type": GlobalSalaryStructureTemplate.TemplateType.INTERN_STIPEND,
            "pay_frequency": GlobalSalaryStructureTemplate.PayFrequency.MONTHLY,
            "lines": [
                {"component": "BASIC", "sequence": 100, "calculation_type": "FIXED", "amount_default": "0.00"},
                {"component": "TDS", "sequence": 330, "calculation_type": "FORMULA", "formula": "config.tds_formula", "rule_json": {"scheme_code": "TDS"}, "applicability_json": {"mode": "configurable", "condition_key": "if_tds_enabled"}},
            ],
        },
    )

    @classmethod
    def seed_default_catalog(
        cls,
        *,
        country: str = "IN",
        force: bool = False,
        dry_run: bool = False,
        only: str = "all",
        verbose: bool = False,
    ) -> dict:
        country = (country or "IN").upper()
        if country != "IN":
            raise ValueError(f"No global payroll seed defaults are registered for country '{country}'.")
        if only not in {"all", "groups", "components", "templates"}:
            raise ValueError("Invalid seed target. Use one of: groups, components, templates, all.")

        result = GlobalSeedExecutionResult(country=country, dry_run=dry_run, force=force, only=only)

        with transaction.atomic():
            groups = cls._seed_groups(result=result, force=force, country=country, enabled=only in {"all", "groups", "components", "templates"})
            components = cls._seed_components(
                result=result,
                force=force,
                country=country,
                enabled=only in {"all", "components", "templates"},
                groups=groups,
            )
            cls._seed_templates(
                result=result,
                force=force,
                country=country,
                enabled=only in {"all", "templates"},
                components=components,
                verbose=verbose,
            )
            if dry_run:
                transaction.set_rollback(True)

        return result.as_dict()

    @classmethod
    def _seed_groups(
        cls,
        *,
        result: GlobalSeedExecutionResult,
        force: bool,
        country: str,
        enabled: bool,
    ) -> dict[str, GlobalPayrollComponentGroup]:
        groups: dict[str, GlobalPayrollComponentGroup] = {}
        if not enabled:
            for spec in cls.GROUPS:
                existing = GlobalPayrollComponentGroup.objects.filter(code=spec["code"]).first()
                if existing is not None:
                    groups[spec["code"]] = existing
            return groups

        for spec in cls.GROUPS:
            existing = GlobalPayrollComponentGroup.objects.filter(code=spec["code"]).first()
            if existing is not None and not force:
                result.groups.skipped += 1
                groups[spec["code"]] = existing
                if not existing.is_system:
                    result.warnings.append(
                        f"Group {spec['code']} exists as a non-system record and was left unchanged. Use --force to update it."
                    )
                continue

            payload = {
                "code": spec["code"],
                "name": spec["name"],
                "description": spec["description"],
                "group_type": spec["group_type"],
                "sort_order": spec["sort_order"],
                "is_system": True,
                "is_active": True,
                "metadata": {"seed_country": country, "seed_key": spec["code"]},
            }
            created = existing is None
            group = GlobalPayrollCatalogService.create_or_update_component_group(payload, instance=existing)
            groups[spec["code"]] = group
            if created:
                result.groups.created += 1
            else:
                result.groups.updated += 1
        return groups

    @classmethod
    def _seed_components(
        cls,
        *,
        result: GlobalSeedExecutionResult,
        force: bool,
        country: str,
        enabled: bool,
        groups: dict[str, GlobalPayrollComponentGroup],
    ) -> dict[str, GlobalPayrollComponent]:
        components: dict[str, GlobalPayrollComponent] = {}
        if not enabled:
            for spec in cls.COMPONENTS:
                existing = GlobalPayrollComponent.objects.filter(code=spec["code"]).first()
                if existing is not None:
                    components[spec["code"]] = existing
            return components

        for spec in cls.COMPONENTS:
            group = groups.get(spec["group"]) or GlobalPayrollComponentGroup.objects.filter(code=spec["group"]).first()
            if group is None:
                raise ValueError(f"Missing global payroll component group reference '{spec['group']}' for component {spec['code']}.")

            existing = GlobalPayrollComponent.objects.filter(code=spec["code"]).first()
            if existing is not None and not force:
                result.components.skipped += 1
                components[spec["code"]] = existing
                if not existing.is_system:
                    result.warnings.append(
                        f"Component {spec['code']} exists as a non-system record and was left unchanged. Use --force to update it."
                    )
                continue

            payload = {
                "group": group,
                "code": spec["code"],
                "name": spec["name"],
                "description": spec["description"],
                "component_type": spec["component_type"],
                "calculation_type": spec["calculation_type"],
                "default_sequence": spec["default_sequence"],
                "default_formula": spec.get("default_formula", ""),
                "default_rule_json": spec.get("default_rule_json") or {},
                "taxable": spec["taxable"],
                "affects_gross": spec["affects_gross"],
                "affects_net": spec["affects_net"],
                "affects_ctc": spec["affects_ctc"],
                "attendance_dependent": spec.get("attendance_dependent", False),
                "lop_dependent": spec.get("lop_dependent", False),
                "overtime_dependent": spec.get("overtime_dependent", False),
                "pro_rata": spec.get("pro_rata", True),
                "statutory_code": spec.get("statutory_code", ""),
                "country_code": country,
                "state_code": spec.get("state_code", ""),
                "is_system": True,
                "is_active": True,
                "metadata": {"seed_country": country, "seed_key": spec["code"], "group_code": spec["group"]},
            }
            created = existing is None
            component = GlobalPayrollCatalogService.create_or_update_component(payload, instance=existing)
            components[spec["code"]] = component
            if created:
                result.components.created += 1
            else:
                result.components.updated += 1
        return components

    @classmethod
    def _seed_templates(
        cls,
        *,
        result: GlobalSeedExecutionResult,
        force: bool,
        country: str,
        enabled: bool,
        components: dict[str, GlobalPayrollComponent],
        verbose: bool,
    ) -> None:
        if not enabled:
            return

        for spec in cls.TEMPLATES:
            existing = GlobalSalaryStructureTemplate.objects.filter(code=spec["code"]).first()
            if existing is not None and not force:
                template = existing
                result.templates.skipped += 1
                if not existing.is_system:
                    result.warnings.append(
                        f"Template {spec['code']} exists as a non-system record and was left unchanged. Use --force to update it."
                    )
            else:
                payload = {
                    "code": spec["code"],
                    "name": spec["name"],
                    "description": spec["description"],
                    "template_type": spec["template_type"],
                    "country_code": country,
                    "pay_frequency": spec["pay_frequency"],
                    "is_default": spec.get("is_default", False),
                    "is_system": True,
                    "is_active": True,
                    "metadata": {"seed_country": country, "seed_key": spec["code"]},
                }
                created = existing is None
                template = GlobalSalaryTemplateService.create_or_update_template(payload, instance=existing)
                if created:
                    result.templates.created += 1
                else:
                    result.templates.updated += 1

            for line_spec in spec["lines"]:
                component = components.get(line_spec["component"]) or GlobalPayrollComponent.objects.filter(code=line_spec["component"]).first()
                if component is None:
                    raise ValueError(
                        f"Missing global payroll component reference '{line_spec['component']}' while seeding template {spec['code']}."
                    )
                if not component.is_active:
                    raise ValueError(
                        f"Global payroll component '{component.code}' is inactive and cannot be used while seeding template {spec['code']}."
                    )

                existing_line = GlobalSalaryStructureTemplateLine.objects.filter(template=template, component=component).first()
                if existing_line is not None and not force:
                    result.lines.skipped += 1
                    continue

                payload = {
                    "component": component,
                    "sequence": line_spec["sequence"],
                    "calculation_type": line_spec["calculation_type"],
                    "formula": line_spec.get("formula", ""),
                    "rule_json": line_spec.get("rule_json") or {},
                    "amount_default": line_spec.get("amount_default", "0.00"),
                    "percentage_default": line_spec.get("percentage_default", "0.0000"),
                    "basis_components": line_spec.get("basis_components") or [],
                    "min_amount": line_spec.get("min_amount"),
                    "max_amount": line_spec.get("max_amount"),
                    "taxable_override": line_spec.get("taxable_override"),
                    "affects_gross_override": line_spec.get("affects_gross_override"),
                    "affects_net_override": line_spec.get("affects_net_override"),
                    "affects_ctc_override": line_spec.get("affects_ctc_override"),
                    "pro_rata": line_spec.get("pro_rata", component.pro_rata),
                    "attendance_dependent": line_spec.get("attendance_dependent", component.attendance_dependent),
                    "lop_dependent": line_spec.get("lop_dependent", component.lop_dependent),
                    "applicability_json": line_spec.get("applicability_json") or {},
                    "is_active": True,
                    "metadata": {"seed_country": country, "seed_template": spec["code"], "seed_component": component.code},
                }
                created = existing_line is None
                GlobalSalaryTemplateService.create_or_update_line(template, payload, instance=existing_line)
                if created:
                    result.lines.created += 1
                else:
                    result.lines.updated += 1

            if verbose and not spec["lines"]:
                result.warnings.append(f"Template {spec['code']} has no lines configured.")
