from __future__ import annotations

from rest_framework.exceptions import ValidationError

from entity.models import Entity, EntityFinancialYear, SubEntity
from subscriptions.services import SubscriptionService


class ScopedEntitlementMixin:
    subscription_feature_code: str | None = None
    subscription_access_mode: str = SubscriptionService.ACCESS_MODE_OPERATIONAL

    def enforce_scope(
        self,
        request,
        *,
        entity_id: int,
        entityfinid_id: int | None = None,
        subentity_id: int | None = None,
        access_mode: str | None = None,
        feature_code: str | None = None,
    ):
        entity = Entity.objects.filter(id=entity_id, isactive=True).select_related("customer_account").first()
        if entity is None:
            raise ValidationError({"entity": "Entity not found."})

        SubscriptionService.assert_entity_access(
            user=request.user,
            entity=entity,
            access_mode=access_mode or self.subscription_access_mode,
            feature_code=feature_code or self.subscription_feature_code,
        )

        if entityfinid_id and not EntityFinancialYear.objects.filter(id=entityfinid_id, entity_id=entity.id).exists():
            raise ValidationError({"entityfinid": "Financial year is not valid for this entity."})

        if subentity_id and not SubEntity.objects.filter(id=subentity_id, entity_id=entity.id, isactive=True).exists():
            raise ValidationError({"subentity": "Subentity is not valid for this entity."})

        return entity
