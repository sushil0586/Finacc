from __future__ import annotations

from collections.abc import Callable

from rest_framework.exceptions import ValidationError

from entity.models import Entity, EntityFinancialYear, SubEntity
from subscriptions.services import SubscriptionService


def enforce_operational_entity_access(
    *,
    request,
    entity_id: int,
    feature_code: str | None = None,
    access_mode: str = SubscriptionService.ACCESS_MODE_OPERATIONAL,
    permission_check: Callable[..., None] | None = None,
    entityfinid_id: int | None = None,
    subentity_id: int | None = None,
):
    entity = Entity.objects.filter(id=entity_id, isactive=True).select_related("customer_account").first()
    if entity is None:
        raise ValidationError({"entity": "Entity not found."})

    if permission_check is not None:
        permission_check(user=request.user, entity=entity)

    SubscriptionService.assert_entity_access(
        user=request.user,
        entity=entity,
        access_mode=access_mode,
        feature_code=feature_code,
    )

    if entityfinid_id and not EntityFinancialYear.objects.filter(id=entityfinid_id, entity_id=entity.id).exists():
        raise ValidationError({"entityfinid": "Financial year is not valid for this entity."})

    if subentity_id and not SubEntity.objects.filter(id=subentity_id, entity_id=entity.id, isactive=True).exists():
        raise ValidationError({"subentity": "Subentity is not valid for this entity."})

    return entity


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
        return enforce_operational_entity_access(
            request=request,
            entity_id=entity_id,
            feature_code=feature_code or self.subscription_feature_code,
            access_mode=access_mode or self.subscription_access_mode,
            entityfinid_id=entityfinid_id,
            subentity_id=subentity_id,
        )
