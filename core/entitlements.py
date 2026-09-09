from __future__ import annotations

from collections.abc import Callable

from rest_framework.exceptions import PermissionDenied, ValidationError

from entity.models import Entity, EntityFinancialYear, Godown, SubEntity
from subscriptions.services import SubscriptionService
from rbac.models import DataAccessPolicy
from rbac.services import EffectivePermissionService


def enforce_operational_entity_access(
    *,
    request,
    entity_id: int,
    feature_code: str | None = None,
    access_mode: str = SubscriptionService.ACCESS_MODE_OPERATIONAL,
    permission_check: Callable[..., None] | None = None,
    entityfinid_id: int | None = None,
    subentity_id: int | None = None,
    warehouse_ids: list[int] | tuple[int, ...] | set[int] | None = None,
    batch_numbers: list[str] | tuple[str, ...] | set[str] | None = None,
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

    if not EffectivePermissionService.has_scope_access(request.user, entity.id, subentity_id):
        raise PermissionDenied("You do not have access to the requested branch scope.")

    if entityfinid_id and not EffectivePermissionService.has_data_scope_access(
        request.user,
        entity.id,
        DataAccessPolicy.TYPE_FINANCIAL_YEAR,
        entityfinid_id,
    ):
        raise PermissionDenied("You do not have access to the requested financial year scope.")

    normalized_warehouse_ids = {
        int(warehouse_id)
        for warehouse_id in (warehouse_ids or [])
        if warehouse_id
    }
    if normalized_warehouse_ids:
        valid_warehouse_ids = set(
            Godown.objects.filter(
                id__in=normalized_warehouse_ids,
                entity_id=entity.id,
                is_active=True,
            ).values_list("id", flat=True)
        )
        if valid_warehouse_ids != normalized_warehouse_ids:
            raise ValidationError({"warehouse": "Warehouse is not valid for this entity."})
        for warehouse_id in normalized_warehouse_ids:
            if not EffectivePermissionService.has_data_scope_access(
                request.user,
                entity.id,
                DataAccessPolicy.TYPE_WAREHOUSE,
                warehouse_id,
            ):
                raise PermissionDenied("You do not have access to the requested warehouse scope.")

    normalized_batch_numbers = {
        str(batch_number).strip()
        for batch_number in (batch_numbers or [])
        if str(batch_number).strip()
    }
    for batch_number in normalized_batch_numbers:
        if not EffectivePermissionService.has_data_scope_access(
            request.user,
            entity.id,
            DataAccessPolicy.TYPE_BATCH,
            batch_number,
        ):
            raise PermissionDenied("You do not have access to the requested batch scope.")

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
        warehouse_ids: list[int] | tuple[int, ...] | set[int] | None = None,
        batch_numbers: list[str] | tuple[str, ...] | set[str] | None = None,
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
            warehouse_ids=warehouse_ids,
            batch_numbers=batch_numbers,
        )
