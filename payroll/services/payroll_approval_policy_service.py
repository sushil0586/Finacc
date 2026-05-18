from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Case, IntegerField, Q, Value, When

from entity.models import EntityApprovalPolicy, EntityEmploymentProfile, EntityOrgUnit
from payroll.models import PayrollRun
from rbac.services import EffectivePermissionService


@dataclass(frozen=True)
class ResolvedApprovalPolicy:
    policy: EntityApprovalPolicy | None
    source: str


class PayrollApprovalPolicyService:
    @staticmethod
    def _policy_context_label(policy_key: str) -> str:
        labels = {
            EntityApprovalPolicy.PolicyKey.PAYROLL_RUN: "payroll run approval",
            EntityApprovalPolicy.PolicyKey.PAYROLL_PAYMENT_HANDOFF: "payroll payment handoff",
            EntityApprovalPolicy.PolicyKey.PAYROLL_POSTING: "payroll posting",
        }
        return labels.get(policy_key, policy_key.replace("_", " "))

    @staticmethod
    def _resolve_user_profile(*, entity_id: int, subentity_id: int | None, actor_user_id: int | None) -> EntityEmploymentProfile | None:
        if not actor_user_id:
            return None

        queryset = EntityEmploymentProfile.objects.filter(
            entity_id=entity_id,
            employee_user_id=actor_user_id,
            isactive=True,
        ).exclude(status=EntityEmploymentProfile.EmploymentStatus.EXITED)

        if subentity_id is not None:
            queryset = queryset.filter(Q(subentity_id=subentity_id) | Q(subentity__isnull=True))
            subentity_order = Case(
                When(subentity_id=subentity_id, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
            return queryset.select_related(
                "subentity",
                "business_unit",
                "department",
                "work_location",
                "cost_center",
                "grade",
                "designation",
                "manager_user",
            ).order_by(subentity_order, "-effective_from", "-id").first()

        return queryset.select_related(
            "subentity",
            "business_unit",
            "department",
            "work_location",
            "cost_center",
            "grade",
            "designation",
            "manager_user",
        ).order_by("-effective_from", "-id").first()

    @classmethod
    def _resolve_actor_profile(cls, *, run: PayrollRun) -> EntityEmploymentProfile | None:
        return cls._resolve_user_profile(
            entity_id=run.entity_id,
            subentity_id=run.subentity_id,
            actor_user_id=run.submitted_by_id or run.created_by_id,
        )

    @staticmethod
    def _actor_org_units(actor_profile: EntityEmploymentProfile | None) -> list[tuple[str, EntityOrgUnit]]:
        if actor_profile is None:
            return []
        scoped_units = [
            ("business_unit", actor_profile.business_unit),
            ("department", actor_profile.department),
            ("designation", actor_profile.designation),
            ("grade", actor_profile.grade),
            ("work_location", actor_profile.work_location),
            ("cost_center", actor_profile.cost_center),
        ]
        return [(field_name, unit) for field_name, unit in scoped_units if unit is not None]

    @classmethod
    def _resolve_policy(
        cls,
        *,
        run: PayrollRun,
        actor_profile: EntityEmploymentProfile | None,
        policy_key: str = EntityApprovalPolicy.PolicyKey.PAYROLL_RUN,
    ) -> ResolvedApprovalPolicy:
        queryset = EntityApprovalPolicy.objects.filter(
            entity_id=run.entity_id,
            policy_key=policy_key,
            isactive=True,
            status=EntityApprovalPolicy.Status.ACTIVE,
        )
        on_date = getattr(run.payroll_period, "period_end", None)
        if on_date:
            queryset = queryset.filter(
                Q(effective_from__isnull=True) | Q(effective_from__lte=on_date),
                Q(effective_to__isnull=True) | Q(effective_to__gte=on_date),
            )

        applicable = Q(subentity__isnull=True, org_unit__isnull=True)
        if run.subentity_id is not None:
            applicable |= Q(subentity_id=run.subentity_id, org_unit__isnull=True)

        actor_units = cls._actor_org_units(actor_profile)
        actor_unit_ids = [unit.id for _, unit in actor_units]
        if actor_unit_ids:
            unit_scope = Q(org_unit_id__in=actor_unit_ids)
            if run.subentity_id is not None:
                unit_scope &= Q(Q(subentity_id=run.subentity_id) | Q(subentity__isnull=True))
            else:
                unit_scope &= Q(subentity__isnull=True)
            applicable |= unit_scope

        queryset = queryset.filter(applicable).select_related("subentity", "org_unit")

        specificity = Case(
            When(org_unit__isnull=False, subentity_id=run.subentity_id, then=Value(0)),
            When(org_unit__isnull=False, then=Value(1)),
            When(subentity_id=run.subentity_id, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
        policy = queryset.order_by(specificity, "name", "id").first()
        if policy is None:
            return ResolvedApprovalPolicy(policy=None, source="unresolved")
        if policy.org_unit_id:
            return ResolvedApprovalPolicy(policy=policy, source="org_unit")
        if policy.subentity_id:
            return ResolvedApprovalPolicy(policy=policy, source="subentity")
        return ResolvedApprovalPolicy(policy=policy, source="entity")

    @classmethod
    def _build_manager_chain(cls, *, run: PayrollRun, actor_profile: EntityEmploymentProfile | None) -> list[dict]:
        if actor_profile is None:
            return []

        chain: list[dict] = []
        visited_user_ids = {actor_profile.employee_user_id}
        current_manager_user_id = actor_profile.manager_user_id

        while current_manager_user_id and len(chain) < 10:
            if current_manager_user_id in visited_user_ids:
                break
            manager_profile = cls._resolve_user_profile(
                entity_id=run.entity_id,
                subentity_id=run.subentity_id,
                actor_user_id=current_manager_user_id,
            )
            if manager_profile is None:
                break

            chain.append({
                "employee_user": manager_profile.employee_user_id,
                "employee_code": manager_profile.employee_code,
                "full_name": manager_profile.full_name,
                "work_email": manager_profile.work_email,
                "department_name": manager_profile.department.name if manager_profile.department_id else None,
                "designation_name": manager_profile.designation.name if manager_profile.designation_id else None,
                "subentity_name": manager_profile.subentity.subentityname if manager_profile.subentity_id else None,
                "manager_user": manager_profile.manager_user_id,
                "manager_name": (
                    f"{(manager_profile.manager_user.first_name or '').strip()} {(manager_profile.manager_user.last_name or '').strip()}".strip()
                    if manager_profile.manager_user_id else None
                ) or (manager_profile.manager_user.email if manager_profile.manager_user_id else None),
                "status": manager_profile.status,
                "status_label": manager_profile.get_status_display(),
            })
            visited_user_ids.add(current_manager_user_id)
            current_manager_user_id = manager_profile.manager_user_id

        return chain

    @classmethod
    def resolve_policy_context(
        cls,
        *,
        run: PayrollRun,
        policy_key: str = EntityApprovalPolicy.PolicyKey.PAYROLL_RUN,
    ) -> dict:
        actor_profile = cls._resolve_actor_profile(run=run)
        resolved_policy = cls._resolve_policy(
            run=run,
            actor_profile=actor_profile,
            policy_key=policy_key,
        )
        manager_chain = cls._build_manager_chain(run=run, actor_profile=actor_profile)
        policy_label = cls._policy_context_label(policy_key)

        notes: list[str] = []
        if actor_profile is None:
            notes.append("No active shared employment profile was found for the payroll operator in this entity scope.")
        if resolved_policy.policy is None:
            notes.append(f"No active {policy_label} policy matched this run scope.")
        elif resolved_policy.policy.approval_mode == EntityApprovalPolicy.ApprovalMode.MANAGER_CHAIN and not manager_chain:
            notes.append(f"The matched {policy_label} policy uses manager-chain routing, but no manager hierarchy was resolved for the payroll operator.")
        elif resolved_policy.policy.approval_mode == EntityApprovalPolicy.ApprovalMode.MANAGER_CHAIN and len(manager_chain) < resolved_policy.policy.manager_levels:
            notes.append(
                f"The matched {policy_label} policy expects {resolved_policy.policy.manager_levels} manager level(s), but only {len(manager_chain)} were resolved."
            )

        return {
            "policy_key": policy_key,
            "resolution_source": resolved_policy.source,
            "matched_policy": (
                {
                    "id": resolved_policy.policy.id,
                    "code": resolved_policy.policy.code,
                    "name": resolved_policy.policy.name,
                    "approval_mode": resolved_policy.policy.approval_mode,
                    "approval_mode_label": resolved_policy.policy.get_approval_mode_display(),
                    "manager_levels": resolved_policy.policy.manager_levels,
                    "min_approvers": resolved_policy.policy.min_approvers,
                    "approver_roles": resolved_policy.policy.approver_roles,
                    "approver_permissions": resolved_policy.policy.approver_permissions,
                    "fallback_manager_required": resolved_policy.policy.fallback_manager_required,
                    "scope_entity_id": resolved_policy.policy.entity_id,
                    "scope_subentity_id": resolved_policy.policy.subentity_id,
                    "scope_subentity_name": resolved_policy.policy.subentity.subentityname if resolved_policy.policy.subentity_id else None,
                    "scope_org_unit_id": resolved_policy.policy.org_unit_id,
                    "scope_org_unit_name": resolved_policy.policy.org_unit.name if resolved_policy.policy.org_unit_id else None,
                    "scope_org_unit_type": resolved_policy.policy.org_unit.unit_type if resolved_policy.policy.org_unit_id else None,
                }
                if resolved_policy.policy
                else None
            ),
            "actor_profile": (
                {
                    "employee_user": actor_profile.employee_user_id,
                    "employee_code": actor_profile.employee_code,
                    "full_name": actor_profile.full_name,
                    "work_email": actor_profile.work_email,
                    "subentity_name": actor_profile.subentity.subentityname if actor_profile.subentity_id else None,
                    "business_unit_name": actor_profile.business_unit.name if actor_profile.business_unit_id else None,
                    "department_name": actor_profile.department.name if actor_profile.department_id else None,
                    "designation_name": actor_profile.designation.name if actor_profile.designation_id else None,
                    "work_location_name": actor_profile.work_location.name if actor_profile.work_location_id else None,
                    "manager_name": (
                        f"{(actor_profile.manager_user.first_name or '').strip()} {(actor_profile.manager_user.last_name or '').strip()}".strip()
                        if actor_profile.manager_user_id else None
                    ) or (actor_profile.manager_user.email if actor_profile.manager_user_id else None),
                }
                if actor_profile
                else None
            ),
            "manager_chain": manager_chain,
            "notes": notes,
        }

    @classmethod
    def resolve_run_context(cls, *, run: PayrollRun) -> dict:
        return cls.resolve_policy_context(
            run=run,
            policy_key=EntityApprovalPolicy.PolicyKey.PAYROLL_RUN,
        )

    @classmethod
    def _resolve_policy_bundle(cls, *, run: PayrollRun, policy_key: str) -> tuple[EntityEmploymentProfile | None, ResolvedApprovalPolicy, list[dict]]:
        actor_profile = cls._resolve_actor_profile(run=run)
        resolved_policy = cls._resolve_policy(run=run, actor_profile=actor_profile, policy_key=policy_key)
        manager_chain = cls._build_manager_chain(run=run, actor_profile=actor_profile)
        return actor_profile, resolved_policy, manager_chain

    @staticmethod
    def _matches_group_roles(*, user, roles: list[str]) -> bool:
        normalized = [str(role).strip() for role in roles if str(role).strip()]
        if not normalized:
            return False
        return user.groups.filter(name__in=normalized).exists()

    @staticmethod
    def _matches_permission_codes(*, user, entity_id: int, permission_codes: list[str]) -> bool:
        normalized = [str(code).strip() for code in permission_codes if str(code).strip()]
        if not normalized:
            return False
        available = set(EffectivePermissionService.permission_codes_for_user(user, entity_id))
        return bool(set(normalized) & available)

    @classmethod
    def can_user_approve_run(cls, *, user, run: PayrollRun) -> tuple[bool, str | None]:
        if not user or not user.is_authenticated:
            return False, "Authentication is required to approve payroll runs."
        if user.is_superuser:
            return True, None

        _, resolved_policy, manager_chain = cls._resolve_policy_bundle(
            run=run,
            policy_key=EntityApprovalPolicy.PolicyKey.PAYROLL_RUN,
        )
        policy = resolved_policy.policy
        if policy is None:
            return True, None

        mode = policy.approval_mode
        if mode == EntityApprovalPolicy.ApprovalMode.NONE:
            return True, None

        role_match = cls._matches_group_roles(user=user, roles=policy.approver_roles or [])
        permission_match = cls._matches_permission_codes(user=user, entity_id=run.entity_id, permission_codes=policy.approver_permissions or [])

        if mode == EntityApprovalPolicy.ApprovalMode.PERMISSION_BASED:
            if permission_match or role_match:
                return True, None
            return False, f"Approval policy {policy.code} requires one of the configured approval permissions or roles."

        if mode == EntityApprovalPolicy.ApprovalMode.FIXED_USERS:
            if role_match or permission_match:
                return True, None
            return False, f"Approval policy {policy.code} requires one of the configured fixed approver roles or permissions."

        allowed_manager_user_ids = {
            node["employee_user"]
            for node in manager_chain[: max(policy.manager_levels, 0)]
            if node.get("employee_user")
        }
        manager_match = user.id in allowed_manager_user_ids

        if mode == EntityApprovalPolicy.ApprovalMode.MANAGER_CHAIN:
            if manager_match:
                return True, None
            if policy.fallback_manager_required:
                return False, f"Approval policy {policy.code} requires approval from the resolved manager chain."
            return False, f"Approval policy {policy.code} uses manager-chain routing and the approver is outside the allowed chain."

        if mode == EntityApprovalPolicy.ApprovalMode.MIXED:
            if manager_match or role_match or permission_match:
                return True, None
            return False, f"Approval policy {policy.code} requires a matched manager-chain approver, role, or permission."

        return True, None

    @classmethod
    def can_user_submit_run(cls, *, user, run: PayrollRun) -> tuple[bool, str | None]:
        if not user or not user.is_authenticated:
            return False, "Authentication is required to submit payroll runs."
        if user.is_superuser:
            return True, None

        _, resolved_policy, manager_chain = cls._resolve_policy_bundle(
            run=run,
            policy_key=EntityApprovalPolicy.PolicyKey.PAYROLL_RUN,
        )
        policy = resolved_policy.policy
        if policy is None or policy.approval_mode == EntityApprovalPolicy.ApprovalMode.NONE:
            return True, None

        has_roles = bool(policy.approver_roles)
        has_permissions = bool(policy.approver_permissions)
        has_manager_chain = len(manager_chain) >= max(policy.manager_levels, 0)

        if policy.approval_mode == EntityApprovalPolicy.ApprovalMode.MANAGER_CHAIN:
            if has_manager_chain:
                return True, None
            if policy.fallback_manager_required:
                return False, f"Approval policy {policy.code} requires a resolved manager chain before the run can be submitted."
            return True, None

        if policy.approval_mode in {EntityApprovalPolicy.ApprovalMode.PERMISSION_BASED, EntityApprovalPolicy.ApprovalMode.FIXED_USERS}:
            if has_roles or has_permissions:
                return True, None
            return False, f"Approval policy {policy.code} does not have any configured approver roles or permissions."

        if policy.approval_mode == EntityApprovalPolicy.ApprovalMode.MIXED:
            if has_manager_chain or has_roles or has_permissions:
                return True, None
            return False, f"Approval policy {policy.code} does not currently resolve any approval route."

        return True, None

    @classmethod
    def can_user_handoff_payment_run(cls, *, user, run: PayrollRun) -> tuple[bool, str | None]:
        if not user or not user.is_authenticated:
            return False, "Authentication is required to hand off payroll runs for payment."
        if user.is_superuser:
            return True, None

        _, resolved_policy, manager_chain = cls._resolve_policy_bundle(
            run=run,
            policy_key=EntityApprovalPolicy.PolicyKey.PAYROLL_PAYMENT_HANDOFF,
        )
        policy = resolved_policy.policy
        if policy is None:
            return True, None

        role_match = cls._matches_group_roles(user=user, roles=policy.approver_roles or [])
        permission_match = cls._matches_permission_codes(user=user, entity_id=run.entity_id, permission_codes=policy.approver_permissions or [])
        manager_match = user.id in {
            node["employee_user"]
            for node in manager_chain[: max(policy.manager_levels, 0)]
            if node.get("employee_user")
        }

        if policy.approval_mode == EntityApprovalPolicy.ApprovalMode.NONE:
            return True, None
        if policy.approval_mode in {EntityApprovalPolicy.ApprovalMode.PERMISSION_BASED, EntityApprovalPolicy.ApprovalMode.FIXED_USERS}:
            if role_match or permission_match:
                return True, None
            return False, f"Payment handoff policy {policy.code} requires one of the configured roles or permissions."
        if policy.approval_mode == EntityApprovalPolicy.ApprovalMode.MANAGER_CHAIN:
            if manager_match:
                return True, None
            return False, f"Payment handoff policy {policy.code} requires approval from the resolved manager chain."
        if policy.approval_mode == EntityApprovalPolicy.ApprovalMode.MIXED:
            if manager_match or role_match or permission_match:
                return True, None
            return False, f"Payment handoff policy {policy.code} requires a matched manager-chain approver, role, or permission."

        return True, None

    @classmethod
    def can_user_post_run(cls, *, user, run: PayrollRun) -> tuple[bool, str | None]:
        if not user or not user.is_authenticated:
            return False, "Authentication is required to post payroll runs."
        if user.is_superuser:
            return True, None

        _, resolved_policy, manager_chain = cls._resolve_policy_bundle(
            run=run,
            policy_key=EntityApprovalPolicy.PolicyKey.PAYROLL_POSTING,
        )
        policy = resolved_policy.policy
        if policy is None:
            return True, None

        role_match = cls._matches_group_roles(user=user, roles=policy.approver_roles or [])
        permission_match = cls._matches_permission_codes(user=user, entity_id=run.entity_id, permission_codes=policy.approver_permissions or [])
        manager_match = user.id in {
            node["employee_user"]
            for node in manager_chain[: max(policy.manager_levels, 0)]
            if node.get("employee_user")
        }

        if policy.approval_mode == EntityApprovalPolicy.ApprovalMode.NONE:
            return True, None
        if policy.approval_mode in {EntityApprovalPolicy.ApprovalMode.PERMISSION_BASED, EntityApprovalPolicy.ApprovalMode.FIXED_USERS}:
            if role_match or permission_match:
                return True, None
            return False, f"Posting policy {policy.code} requires one of the configured roles or permissions."
        if policy.approval_mode == EntityApprovalPolicy.ApprovalMode.MANAGER_CHAIN:
            if manager_match:
                return True, None
            return False, f"Posting policy {policy.code} requires approval from the resolved manager chain."
        if policy.approval_mode == EntityApprovalPolicy.ApprovalMode.MIXED:
            if manager_match or role_match or permission_match:
                return True, None
            return False, f"Posting policy {policy.code} requires a matched manager-chain approver, role, or permission."

        return True, None
