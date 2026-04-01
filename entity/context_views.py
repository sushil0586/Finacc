from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from entity.context_serializers import (
    EntityContextSerializer,
    EntityFinancialYearOptionSerializer,
    SubEntityOptionSerializer,
    UserContextSelectionSerializer,
)
from entity.models import Entity, EntityFinancialYear, SubEntity, UserEntityContext
from rbac.models import UserRoleAssignment
from rbac.services import EffectivePermissionService


def _primary_gst(entity):
    row = entity.gst_registrations.filter(isactive=True, is_primary=True).first()
    return row.gstin if row else None


def _default_financial_year_id(entity):
    active = entity.fy.filter(isactive=True).order_by("finstartyear", "id").first()
    if active:
        return active.id
    fallback = entity.fy.order_by("finstartyear", "id").first()
    return fallback.id if fallback else None


def _default_subentity_id(entity):
    head_office = entity.subentity.filter(isactive=True, is_head_office=True).order_by("sort_order", "id").first()
    if head_office:
        return head_office.id
    fallback = entity.subentity.filter(isactive=True).order_by("sort_order", "id").first()
    return fallback.id if fallback else None


def _can_access_entity(user, entity):
    if getattr(settings, "RBAC_DEV_ALLOW_ALL_ACCESS", False):
        return True
    if entity.createdby_id == user.id:
        return True
    now = timezone.now()
    return UserRoleAssignment.objects.filter(user=user, entity=entity, isactive=True).filter(
        Q(effective_from__isnull=True) | Q(effective_from__lte=now),
        Q(effective_to__isnull=True) | Q(effective_to__gte=now),
    ).exists()


def _resolve_user_context(user, entity):
    context = UserEntityContext.objects.filter(user=user, entity=entity).first()
    default_entityfinid = context.entityfinid_id if context else None
    default_subentity = context.subentity_id if context else None

    if default_entityfinid and not EntityFinancialYear.objects.filter(id=default_entityfinid, entity=entity).exists():
        default_entityfinid = None
    if default_subentity and not SubEntity.objects.filter(id=default_subentity, entity=entity).exists():
        default_subentity = None

    if default_entityfinid is None:
        default_entityfinid = _default_financial_year_id(entity)
    if default_subentity is None:
        default_subentity = _default_subentity_id(entity)

    return default_entityfinid, default_subentity


class UserEntitiesV2View(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        include_param = (request.query_params.get("include") or "").strip().lower()
        include_set = {item.strip() for item in include_param.split(",") if item.strip()}
        include_financial_years = "financial_years" in include_set
        include_subentities = "subentities" in include_set

        def build_include_maps(entity_ids):
            financial_years_map = {}
            subentities_map = {}
            if include_financial_years:
                for row in (
                    EntityFinancialYear.objects.filter(entity_id__in=entity_ids)
                    .order_by("finstartyear", "id")
                    .values(
                        "entity_id",
                        "id",
                        "desc",
                        "year_code",
                        "assessment_year_label",
                        "finstartyear",
                        "finendyear",
                        "isactive",
                    )
                ):
                    financial_years_map.setdefault(row["entity_id"], []).append(
                        {
                            "id": row["id"],
                            "desc": row["desc"],
                            "year_code": row["year_code"],
                            "assessment_year_label": row["assessment_year_label"],
                            "finstartyear": row["finstartyear"],
                            "finendyear": row["finendyear"],
                            "isactive": row["isactive"],
                        }
                    )

            if include_subentities:
                for row in (
                    SubEntity.objects.filter(entity_id__in=entity_ids, isactive=True)
                    .order_by("sort_order", "id")
                    .values("entity_id", "id", "subentityname", "subentity_code", "is_head_office", "branch_type")
                ):
                    subentities_map.setdefault(row["entity_id"], []).append(
                        {
                            "id": row["id"],
                            "subentityname": row["subentityname"],
                            "subentity_code": row["subentity_code"],
                            "is_head_office": row["is_head_office"],
                            "branch_type": row["branch_type"],
                        }
                    )
            return financial_years_map, subentities_map

        if getattr(settings, "RBAC_DEV_ALLOW_ALL_ACCESS", False):
            entities = Entity.objects.filter(isactive=True).order_by("entityname", "id")
            entity_ids = list(entities.values_list("id", flat=True))
            financial_years_map, subentities_map = build_include_maps(entity_ids)
            data = []
            for entity in entities:
                default_entityfinid, default_subentity = _resolve_user_context(user, entity)
                item = {
                    "entityid": entity.id,
                    "entityname": entity.entityname,
                    "gstno": _primary_gst(entity),
                    "email": user.email,
                    "role": "Development Full Access",
                    "roleid": 0,
                    "roles": EffectivePermissionService.role_summaries_for_user(user, entity.id),
                    "default_entityfinid": default_entityfinid,
                    "default_subentity": default_subentity,
                    "default_subentity_id": default_subentity,
                }
                if include_financial_years:
                    item["financial_years"] = financial_years_map.get(entity.id, [])
                if include_subentities:
                    item["subentities"] = subentities_map.get(entity.id, [])
                data.append(item)
            serializer = EntityContextSerializer(data, many=True)
            return Response(serializer.data)

        entity_map = {}
        now = timezone.now()
        assignments = (
            UserRoleAssignment.objects.filter(user=user, isactive=True, role__isactive=True)
            .filter(
                Q(effective_from__isnull=True) | Q(effective_from__lte=now),
                Q(effective_to__isnull=True) | Q(effective_to__gte=now),
            )
            .select_related("entity", "role")
            .order_by("entity__entityname", "id")
        )
        entity_ids = []
        for assignment in assignments:
            if assignment.entity_id in entity_map:
                continue
            entity_ids.append(assignment.entity_id)
            roles = EffectivePermissionService.role_summaries_for_user(user, assignment.entity_id)
            primary_role = next((role for role in roles if role.get("is_primary")), roles[0] if roles else None)
            default_entityfinid, default_subentity = _resolve_user_context(user, assignment.entity)
            entity_map[assignment.entity_id] = {
                "entityid": assignment.entity_id,
                "entityname": assignment.entity.entityname,
                "gstno": _primary_gst(assignment.entity),
                "email": user.email,
                "role": primary_role["name"] if primary_role else assignment.role.name,
                "roleid": primary_role["id"] if primary_role else assignment.role_id,
                "roles": roles,
                "default_entityfinid": default_entityfinid,
                "default_subentity": default_subentity,
                "default_subentity_id": default_subentity,
            }

        # Include entities owned by the user even if explicit RBAC assignments
        # are not present yet (common right after onboarding).
        owned_entities = Entity.objects.filter(isactive=True, createdby=user).order_by("entityname", "id")
        for entity in owned_entities:
            if entity.id in entity_map:
                continue
            entity_ids.append(entity.id)
            roles = EffectivePermissionService.role_summaries_for_user(user, entity.id)
            primary_role = next((role for role in roles if role.get("is_primary")), roles[0] if roles else None)
            default_entityfinid, default_subentity = _resolve_user_context(user, entity)
            entity_map[entity.id] = {
                "entityid": entity.id,
                "entityname": entity.entityname,
                "gstno": _primary_gst(entity),
                "email": user.email,
                "role": primary_role["name"] if primary_role else "Owner",
                "roleid": primary_role["id"] if primary_role else 0,
                "roles": roles,
                "default_entityfinid": default_entityfinid,
                "default_subentity": default_subentity,
                "default_subentity_id": default_subentity,
            }

        financial_years_map, subentities_map = build_include_maps(entity_ids)
        if include_financial_years or include_subentities:
            for entity_id, item in entity_map.items():
                if include_financial_years:
                    item["financial_years"] = financial_years_map.get(entity_id, [])
                if include_subentities:
                    item["subentities"] = subentities_map.get(entity_id, [])

        serializer = EntityContextSerializer(list(entity_map.values()), many=True)
        return Response(serializer.data)


class UserEntityFinancialYearsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, entity_id):
        entity = Entity.objects.filter(id=entity_id).first()
        if not entity or not _can_access_entity(request.user, entity):
            return Response({"detail": "Entity not found or access denied."}, status=status.HTTP_404_NOT_FOUND)

        rows = list(
            entity.fy.order_by("finstartyear", "id").values(
                "id",
                "desc",
                "year_code",
                "assessment_year_label",
                "finstartyear",
                "finendyear",
                "isactive",
            )
        )
        serializer = EntityFinancialYearOptionSerializer(rows, many=True)
        default_entityfinid, _ = _resolve_user_context(request.user, entity)
        return Response({
            "entity_id": entity.id,
            "default_entityfinid": default_entityfinid,
            "financial_years": serializer.data,
        })


class UserEntitySubentitiesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, entity_id):
        entity = Entity.objects.filter(id=entity_id).first()
        if not entity or not _can_access_entity(request.user, entity):
            return Response({"detail": "Entity not found or access denied."}, status=status.HTTP_404_NOT_FOUND)

        rows = list(
            entity.subentity.filter(isactive=True)
            .order_by("sort_order", "id")
            .values("id", "subentityname", "subentity_code", "is_head_office", "branch_type")
        )
        serializer = SubEntityOptionSerializer(rows, many=True)
        _, default_subentity = _resolve_user_context(request.user, entity)
        return Response({
            "entity_id": entity.id,
            "default_subentity_id": default_subentity,
            "subentities": serializer.data,
        })


class UserEntityContextPatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, entity_id):
        entity = Entity.objects.filter(id=entity_id).first()
        if not entity or not _can_access_entity(request.user, entity):
            return Response({"detail": "Entity not found or access denied."}, status=status.HTTP_404_NOT_FOUND)

        entityfinid = request.data.get("entityfinid")
        subentity = request.data.get("subentity")

        entityfinid_obj = None
        subentity_obj = None

        if entityfinid is not None:
            entityfinid_obj = EntityFinancialYear.objects.filter(id=entityfinid, entity=entity).first()
            if not entityfinid_obj:
                raise ValidationError({"entityfinid": "Invalid financial year for this entity."})

        if subentity is not None:
            subentity_obj = SubEntity.objects.filter(id=subentity, entity=entity, isactive=True).first()
            if not subentity_obj:
                raise ValidationError({"subentity": "Invalid subentity for this entity."})

        context, _ = UserEntityContext.objects.update_or_create(
            user=request.user,
            entity=entity,
            defaults={
                "entityfinid": entityfinid_obj,
                "subentity": subentity_obj,
                "updated_by": request.user,
                "isactive": True,
            },
        )
        payload = {
            "entity_id": entity.id,
            "entityfinid": context.entityfinid_id,
            "subentity": context.subentity_id,
        }
        serializer = UserContextSelectionSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserEntityContextGetView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity_id")
        if not entity_id:
            raise ValidationError({"entity_id": "entity_id is required."})

        entity = Entity.objects.filter(id=entity_id).first()
        if not entity or not _can_access_entity(request.user, entity):
            return Response({"detail": "Entity not found or access denied."}, status=status.HTTP_404_NOT_FOUND)

        default_entityfinid, default_subentity = _resolve_user_context(request.user, entity)
        payload = {
            "entity_id": entity.id,
            "entityfinid": default_entityfinid,
            "subentity": default_subentity,
        }
        serializer = UserContextSelectionSerializer(payload)
        return Response(serializer.data)
