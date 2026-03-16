from __future__ import annotations


class PayrollPermissionService:
    ACTION_GROUPS = {
        "create": {"payroll_operator"},
        "calculate": {"payroll_operator"},
        "submit": {"payroll_operator"},
        "approve": {"payroll_reviewer"},
        "post": {"payroll_finance"},
        "payment_handoff": {"payroll_finance"},
        "payment_reconcile": {"payroll_finance"},
        "reverse": {"payroll_admin"},
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
    }

    @classmethod
    def has_action_access(cls, *, user, action: str) -> bool:
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        group_names = cls.ACTION_GROUPS.get(action, set())
        if group_names and user.groups.filter(name__in=group_names).exists():
            return True
        for perm in cls.ACTION_PERMISSIONS.get(action, set()):
            if user.has_perm(perm):
                return True
        return False

    @classmethod
    def assert_action_access(cls, *, user, action: str) -> None:
        if cls.has_action_access(user=user, action=action):
            return
        raise PermissionError(
            f"You do not have permission to {cls.ACTION_LABELS.get(action, action.replace('_', ' '))}."
        )
