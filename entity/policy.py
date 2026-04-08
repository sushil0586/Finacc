from entity.models import EntityPolicy


class EntityPolicyService:
    DEFAULT_POLICY = {
        "gstin_state_match_mode": EntityPolicy.ValidationMode.HARD,
        "require_subentity_mode": EntityPolicy.ValidationMode.HARD,
        "require_head_office_subentity_mode": EntityPolicy.ValidationMode.HARD,
        "require_entity_primary_gstin_mode": EntityPolicy.ValidationMode.HARD,
        "subentity_gstin_state_match_mode": EntityPolicy.ValidationMode.HARD,
        "metadata": {},
    }

    @classmethod
    def ensure_policy(cls, *, entity, actor=None):
        policy, created = EntityPolicy.objects.get_or_create(
            entity=entity,
            defaults={
                **cls.DEFAULT_POLICY,
                "createdby": actor,
            },
        )
        if created:
            return policy

        changed = False
        for key, value in cls.DEFAULT_POLICY.items():
            if getattr(policy, key, None) in (None, ""):
                setattr(policy, key, value)
                changed = True
        if actor and not policy.createdby_id:
            policy.createdby = actor
            changed = True
        if changed:
            policy.save()
        return policy

    @classmethod
    def sync_policy(cls, *, entity, policy_data=None, actor=None):
        policy = cls.ensure_policy(entity=entity, actor=actor)
        if not policy_data:
            return policy

        changed = False
        for key in cls.DEFAULT_POLICY.keys():
            if key not in policy_data:
                continue
            value = policy_data.get(key)
            if key == "metadata":
                value = value or {}
            if getattr(policy, key) != value:
                setattr(policy, key, value)
                changed = True
        if actor and policy.createdby_id is None:
            policy.createdby = actor
            changed = True
        if changed:
            policy.save()
        return policy

    @classmethod
    def build_payload(cls, *, entity):
        policy = cls.ensure_policy(entity=entity)
        return {
            "gstin_state_match_mode": policy.gstin_state_match_mode,
            "require_subentity_mode": policy.require_subentity_mode,
            "require_head_office_subentity_mode": policy.require_head_office_subentity_mode,
            "require_entity_primary_gstin_mode": policy.require_entity_primary_gstin_mode,
            "subentity_gstin_state_match_mode": policy.subentity_gstin_state_match_mode,
            "metadata": policy.metadata or {},
        }

    @staticmethod
    def is_hard(mode):
        return mode == EntityPolicy.ValidationMode.HARD

    @staticmethod
    def is_soft(mode):
        return mode == EntityPolicy.ValidationMode.SOFT

    @classmethod
    def enforce(cls, *, mode, field, message, warnings=None, code=None):
        if cls.is_hard(mode):
            from rest_framework.exceptions import ValidationError

            raise ValidationError({field: message})
        if cls.is_soft(mode) and warnings is not None:
            warnings.append(
                {
                    "field": field,
                    "code": code or field,
                    "message": message,
                    "severity": "warning",
                }
            )
