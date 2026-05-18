from __future__ import annotations

from rbac.services import EffectivePermissionService


class PayrollPermissionService:
    ENTITY_PERMISSION_CODES = {
        "run_view": {"payroll.run.view"},
        "run_create": {"payroll.run.manage", "payroll.run.create"},
        "run_calculate": {"payroll.run.calculate", "payroll.run.manage"},
        "run_submit": {"payroll.run.submit", "payroll.run.manage"},
        "run_approve": {"payroll.run.approve"},
        "run_post": {"payroll.run.post"},
        "run_reverse": {"payroll.run.reverse"},
        "run_payment_handoff": {"payroll.run.payment_handoff", "payments.payroll.handoff"},
        "run_payment_reconcile": {"payroll.run.payment_reconcile", "payments.payroll.reconcile"},
        "payment_batch_view": {"payroll.run.payment_handoff", "payments.payroll.handoff", "payroll.run.view"},
        "payment_batch_create": {"payroll.run.payment_handoff", "payments.payroll.handoff"},
        "payment_batch_validate": {"payroll.run.payment_handoff", "payments.payroll.handoff"},
        "payment_batch_approve": {"payroll.run.payment_handoff", "payments.payroll.handoff"},
        "payment_batch_export": {"payroll.run.payment_handoff", "payments.payroll.handoff"},
        "payment_batch_mark_paid": {"payroll.run.payment_reconcile", "payments.payroll.reconcile"},
        "payment_batch_mark_failed": {"payroll.run.payment_reconcile", "payments.payroll.reconcile"},
        "payment_batch_cancel": {"payroll.run.payment_handoff", "payments.payroll.handoff"},
        "component_view": {"payroll.component.view", "payroll.component.manage"},
        "component_create": {"payroll.component.create", "payroll.component.manage"},
        "component_edit": {"payroll.component.edit", "payroll.component.manage"},
        "structure_view": {"payroll.structure.view", "payroll.structure.manage"},
        "structure_create": {"payroll.structure.create", "payroll.structure.manage"},
        "structure_edit": {"payroll.structure.edit", "payroll.structure.manage"},
        "global_salary_template_view": {"payroll.global_salary_template.view", "payroll.global_salary_template.manage"},
        "global_salary_template_adopt": {"payroll.global_salary_template.adopt", "payroll.global_salary_template.manage"},
        "period_view": {"payroll.period.view", "payroll.period.manage"},
        "period_create": {"payroll.period.create", "payroll.period.manage"},
        "period_edit": {"payroll.period.edit", "payroll.period.manage"},
        "policy_view": {"payroll.policies.view", "payroll.run.view", "payroll.run.manage"},
        "policy_create": {"payroll.policies.create", "payroll.run.manage"},
        "policy_edit": {"payroll.policies.update", "payroll.run.manage"},
        "policy_delete": {"payroll.policies.delete", "payroll.run.manage"},
        "recurring_pay_item_view": {"payroll.recurring_pay_items.view", "payroll.run.view", "payroll.run.manage"},
        "recurring_pay_item_create": {"payroll.recurring_pay_items.create", "payroll.run.manage"},
        "recurring_pay_item_edit": {"payroll.recurring_pay_items.update", "payroll.run.manage"},
        "recurring_pay_item_delete": {"payroll.recurring_pay_items.delete", "payroll.run.manage"},
        "one_time_pay_item_view": {"payroll.one_time_pay_items.view", "payroll.run.view", "payroll.run.manage"},
        "one_time_pay_item_create": {"payroll.one_time_pay_items.create", "payroll.run.manage"},
        "one_time_pay_item_edit": {"payroll.one_time_pay_items.update", "payroll.run.manage"},
        "one_time_pay_item_delete": {"payroll.one_time_pay_items.delete", "payroll.run.manage"},
        "statutory_scheme_view": {"payroll.statutory_schemes.view", "payroll.run.view", "payroll.run.manage"},
        "statutory_scheme_create": {"payroll.statutory_schemes.create", "payroll.run.manage"},
        "statutory_scheme_edit": {"payroll.statutory_schemes.update", "payroll.run.manage"},
        "statutory_scheme_delete": {"payroll.statutory_schemes.delete", "payroll.run.manage"},
        "statutory_rule_view": {"payroll.statutory_rules.view", "payroll.run.view", "payroll.run.manage"},
        "statutory_rule_create": {"payroll.statutory_rules.create", "payroll.run.manage"},
        "statutory_rule_edit": {"payroll.statutory_rules.update", "payroll.run.manage"},
        "statutory_rule_delete": {"payroll.statutory_rules.delete", "payroll.run.manage"},
        "statutory_registration_view": {"payroll.statutory_registrations.view", "payroll.run.view", "payroll.run.manage"},
        "statutory_registration_create": {"payroll.statutory_registrations.create", "payroll.run.manage"},
        "statutory_registration_edit": {"payroll.statutory_registrations.update", "payroll.run.manage"},
        "statutory_registration_delete": {"payroll.statutory_registrations.delete", "payroll.run.manage"},
        "contract_statutory_profile_view": {"payroll.contract_statutory_profiles.view", "payroll.run.view", "payroll.run.manage"},
        "contract_statutory_profile_create": {"payroll.contract_statutory_profiles.create", "payroll.run.manage"},
        "contract_statutory_profile_edit": {"payroll.contract_statutory_profiles.update", "payroll.run.manage"},
        "contract_statutory_profile_delete": {"payroll.contract_statutory_profiles.delete", "payroll.run.manage"},
        "runtime_readiness_view": {"payroll.runtime_readiness.view", "payroll.run.view", "payroll.run.manage"},
        "report_view": {"reports.payroll.view"},
        "report_export": {"reports.payroll.export"},
    }

    ACTION_GROUPS = {
        "create": {"payroll_operator"},
        "calculate": {"payroll_operator"},
        "submit": {"payroll_operator"},
        "approve": {"payroll_reviewer"},
        "post": {"payroll_finance"},
        "payment_handoff": {"payroll_finance"},
        "payment_reconcile": {"payroll_finance"},
        "reverse": {"payroll_admin"},
        "payment_batch_create": {"payroll_finance"},
        "payment_batch_validate": {"payroll_finance"},
        "payment_batch_approve": {"payroll_finance"},
        "payment_batch_export": {"payroll_finance"},
        "payment_batch_mark_paid": {"payroll_finance"},
        "payment_batch_mark_failed": {"payroll_finance"},
        "payment_batch_cancel": {"payroll_finance"},
    }

    ACTION_PERMISSIONS = {
        "create": {"payroll.add_payrollrun"},
        "calculate": {"payroll.change_payrollrun"},
        "submit": {"payroll.change_payrollrun"},
        "approve": set(),
        "post": set(),
        "payment_handoff": set(),
        "payment_reconcile": set(),
        "reverse": set(),
        "payment_batch_create": set(),
        "payment_batch_validate": set(),
        "payment_batch_approve": set(),
        "payment_batch_export": set(),
        "payment_batch_mark_paid": set(),
        "payment_batch_mark_failed": set(),
        "payment_batch_cancel": set(),
    }

    ACTION_ENTITY_PERMISSION_KEYS = {
        "create": "run_create",
        "calculate": "run_calculate",
        "submit": "run_submit",
        "approve": "run_approve",
        "post": "run_post",
        "payment_handoff": "run_payment_handoff",
        "payment_reconcile": "run_payment_reconcile",
        "reverse": "run_reverse",
        "payment_batch_create": "payment_batch_create",
        "payment_batch_validate": "payment_batch_validate",
        "payment_batch_approve": "payment_batch_approve",
        "payment_batch_export": "payment_batch_export",
        "payment_batch_mark_paid": "payment_batch_mark_paid",
        "payment_batch_mark_failed": "payment_batch_mark_failed",
        "payment_batch_cancel": "payment_batch_cancel",
    }

    ACTION_LABELS = {
        "create": "create payroll runs",
        "calculate": "calculate payroll runs",
        "submit": "submit payroll runs",
        "approve": "approve payroll runs",
        "post": "post payroll runs",
        "payment_handoff": "hand off payroll to payments",
        "payment_reconcile": "reconcile payroll payments",
        "reverse": "reverse payroll runs",
        "payment_batch_create": "create payroll payment batches",
        "payment_batch_validate": "validate payroll payment batches",
        "payment_batch_approve": "approve payroll payment batches",
        "payment_batch_export": "export payroll payment batches",
        "payment_batch_mark_paid": "mark payroll payment batches paid",
        "payment_batch_mark_failed": "mark payroll payment batches failed",
        "payment_batch_cancel": "cancel payroll payment batches",
    }

    @staticmethod
    def has_named_access(*, user, groups: set[str] | None = None, permissions: set[str] | None = None) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        groups = groups or set()
        permissions = permissions or set()
        if groups and user.groups.filter(name__in=groups).exists():
            return True
        for perm in permissions:
            if user.has_perm(perm):
                return True
        return False

    @classmethod
    def has_entity_permission_access(cls, *, user, entity_id: int | None, permission_key: str) -> bool:
        if not entity_id:
            return False
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        available_codes = set(EffectivePermissionService.permission_codes_for_user(user, entity_id))
        required_codes = cls.ENTITY_PERMISSION_CODES.get(permission_key, set())
        return bool(required_codes & available_codes)

    @classmethod
    def assert_entity_permission_access(cls, *, user, entity_id: int | None, permission_key: str, label: str) -> None:
        if cls.has_entity_permission_access(user=user, entity_id=entity_id, permission_key=permission_key):
            return
        raise PermissionError(f"You do not have permission to {label}.")

    @classmethod
    def assert_named_access(cls, *, user, groups: set[str] | None = None, permissions: set[str] | None = None, label: str) -> None:
        if cls.has_named_access(user=user, groups=groups, permissions=permissions):
            return
        raise PermissionError(f"You do not have permission to {label}.")

    @classmethod
    def has_action_access(cls, *, user, action: str, entity_id: int | None = None) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        permission_key = cls.ACTION_ENTITY_PERMISSION_KEYS.get(action)
        if permission_key and cls.has_entity_permission_access(user=user, entity_id=entity_id, permission_key=permission_key):
            return True
        group_names = cls.ACTION_GROUPS.get(action, set())
        if group_names and user.groups.filter(name__in=group_names).exists():
            return True
        for perm in cls.ACTION_PERMISSIONS.get(action, set()):
            if user.has_perm(perm):
                return True
        return False

    @classmethod
    def assert_action_access(cls, *, user, action: str, entity_id: int | None = None) -> None:
        if cls.has_action_access(user=user, action=action, entity_id=entity_id):
            return
        raise PermissionError(
            f"You do not have permission to {cls.ACTION_LABELS.get(action, action.replace('_', ' '))}."
        )
