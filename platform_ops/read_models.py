from django.db.models import Count, Prefetch, Q
from django.utils import timezone

from entity.models import Entity
from subscriptions.models import CustomerAccount, CustomerSubscription, UserEntityAccess


def mask_email(value):
    value = (value or "").strip()
    if not value or "@" not in value:
        return value
    local, domain = value.split("@", 1)
    visible = local[:2]
    return f"{visible}{'*' * max(len(local) - len(visible), 1)}@{domain}"


def mask_phone(value):
    value = (value or "").strip()
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * (len(value) - 4)}{value[-4:]}"


def mask_gstin(value):
    value = (value or "").strip().upper()
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 6)}{value[-4:]}"


def user_display_name(user):
    if user is None:
        return ""
    return " ".join(part for part in (user.first_name, user.last_name) if part).strip() or user.username


def current_subscription(account):
    rows = getattr(account, "platform_current_subscriptions", None)
    if rows is not None:
        return rows[0] if rows else None
    return (
        account.subscriptions.filter(
            is_active=True,
            status__in=("trialing", "active", "past_due", "paused"),
            ended_at__isnull=True,
        )
        .select_related("plan")
        .order_by("-started_at", "-id")
        .first()
    )


def account_queryset():
    now = timezone.now()
    return (
        CustomerAccount.objects.select_related("owner")
        .annotate(
            entity_count=Count("entities", filter=Q(entities__isactive=True), distinct=True),
            member_count=Count(
                "user_accesses",
                filter=Q(user_accesses__is_active=True)
                & (Q(user_accesses__expires_at__isnull=True) | Q(user_accesses__expires_at__gt=now)),
                distinct=True,
            ),
        )
        .prefetch_related(
            models_prefetch_current_subscriptions(),
        )
        .order_by("-created_at", "-id")
    )


def models_prefetch_current_subscriptions():
    from django.db.models import Prefetch

    return Prefetch(
        "subscriptions",
        queryset=CustomerSubscription.objects.filter(
            is_active=True,
            status__in=("trialing", "active", "past_due", "paused"),
            ended_at__isnull=True,
        ).select_related("plan").order_by("-started_at", "-id"),
        to_attr="platform_current_subscriptions",
    )


def entity_queryset():
    from entity.models import EntityGstRegistration

    return (
        Entity.objects.select_related("customer_account", "createdby")
        .prefetch_related(
            Prefetch(
                "gst_registrations",
                queryset=EntityGstRegistration.objects.filter(isactive=True).order_by("-is_primary", "id"),
                to_attr="platform_active_gst_registrations",
            )
        )
        .annotate(
            branch_count=Count("subentity", filter=Q(subentity__isactive=True), distinct=True),
            financial_year_count=Count("fy", filter=Q(fy__isactive=True), distinct=True),
            gst_registration_count=Count(
                "gst_registrations",
                filter=Q(gst_registrations__isactive=True),
                distinct=True,
            ),
        )
        .order_by("-created_at", "-id")
    )


def account_health(account):
    findings = []
    subscription = current_subscription(account)
    if not account.owner_id:
        findings.append({"code": "owner_missing", "severity": "high", "message": "Customer owner is missing."})
    if account.status != CustomerAccount.Status.ACTIVE:
        findings.append({"code": "account_not_active", "severity": "medium", "message": "Customer account is not active."})
    if subscription is None:
        findings.append({"code": "subscription_missing", "severity": "high", "message": "Current subscription is missing."})
    entity_count = account.entity_count if hasattr(account, "entity_count") else account.entities.filter(isactive=True).count()
    if entity_count == 0:
        findings.append({"code": "entity_missing", "severity": "high", "message": "No active entity is configured."})
    return {"status": "attention" if findings else "healthy", "findings": findings}


def entity_health(entity):
    findings = []
    branch_count = entity.branch_count if hasattr(entity, "branch_count") else entity.subentity.filter(isactive=True).count()
    financial_year_count = entity.financial_year_count if hasattr(entity, "financial_year_count") else entity.fy.filter(isactive=True).count()
    gst_count = entity.gst_registration_count if hasattr(entity, "gst_registration_count") else entity.gst_registrations.filter(isactive=True).count()
    if not entity.customer_account_id:
        findings.append({"code": "customer_account_missing", "severity": "high", "message": "Customer account link is missing."})
    if branch_count == 0:
        findings.append({"code": "branch_missing", "severity": "high", "message": "No active branch is configured."})
    if financial_year_count == 0:
        findings.append({"code": "financial_year_missing", "severity": "high", "message": "No active financial year is configured."})
    if entity.gst_registration_status in {Entity.GstStatus.REGISTERED, Entity.GstStatus.COMPOSITION, Entity.GstStatus.SEZ} and gst_count == 0:
        findings.append({"code": "gst_registration_missing", "severity": "high", "message": "GST registration is required but missing."})
    if entity.organization_status != Entity.OrganizationStatus.ACTIVE:
        findings.append({"code": "entity_not_active", "severity": "medium", "message": "Entity is not active."})
    return {"status": "attention" if findings else "healthy", "findings": findings}


def serialize_subscription(subscription):
    if subscription is None:
        return None
    return {
        "id": subscription.id,
        "status": subscription.status,
        "plan": {
            "id": subscription.plan_id,
            "code": subscription.plan.code,
            "name": subscription.plan.name,
            "tier": subscription.plan.tier,
        },
        "trial_ends_at": subscription.trial_ends_at,
        "current_period_end": subscription.current_period_end,
        "seats_purchased": subscription.seats_purchased,
        "auto_renew": subscription.auto_renew,
        "updated_at": subscription.updated_at,
    }


def serialize_account(account, *, reveal_sensitive=False, include_detail=False):
    email = account.primary_contact_email or getattr(account.owner, "email", "")
    payload = {
        "id": account.id,
        "name": account.name,
        "legal_name": account.legal_name,
        "trade_name": account.trade_name,
        "slug": account.slug,
        "account_type": account.account_type,
        "status": account.status,
        "owner": {
            "id": account.owner_id,
            "name": user_display_name(account.owner) if account.owner_id else "",
            "email": (getattr(account.owner, "email", "") if reveal_sensitive else mask_email(getattr(account.owner, "email", ""))),
        },
        "primary_contact_email": email if reveal_sensitive else mask_email(email),
        "primary_contact_phone": account.primary_contact_phone if reveal_sensitive else mask_phone(account.primary_contact_phone),
        "entity_count": getattr(account, "entity_count", 0),
        "member_count": getattr(account, "member_count", 0),
        "subscription": serialize_subscription(current_subscription(account)),
        "health": account_health(account),
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }
    if include_detail:
        payload["billing"] = {
            "contact_name": account.billing_contact_name,
            "email": account.billing_email if reveal_sensitive else mask_email(account.billing_email),
            "phone": account.billing_contact_phone if reveal_sensitive else mask_phone(account.billing_contact_phone),
            "provider": account.billing_provider,
            "external_customer_id": account.external_customer_id if reveal_sensitive else None,
        }
    return payload


def serialize_entity(entity, *, reveal_sensitive=False, include_detail=False):
    gst_rows = getattr(entity, "platform_active_gst_registrations", None)
    primary_gst = (
        next((row for row in gst_rows if row.is_primary), None)
        if gst_rows is not None
        else entity.gst_registrations.filter(isactive=True, is_primary=True).first()
    )
    payload = {
        "id": entity.id,
        "customer_account_id": entity.customer_account_id,
        "customer_account_name": getattr(entity.customer_account, "name", ""),
        "entity_name": entity.entityname,
        "legal_name": entity.legalname,
        "trade_name": entity.trade_name,
        "entity_code": entity.entity_code,
        "organization_status": entity.organization_status,
        "business_type": entity.business_type,
        "gst_registration_status": entity.gst_registration_status,
        "primary_gstin": (primary_gst.gstin if reveal_sensitive else mask_gstin(primary_gst.gstin)) if primary_gst else "",
        "branch_count": getattr(entity, "branch_count", 0),
        "financial_year_count": getattr(entity, "financial_year_count", 0),
        "health": entity_health(entity),
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
    }
    if include_detail:
        payload["branches"] = [
            {
                "id": row.id,
                "name": row.subentityname,
                "code": row.subentity_code,
                "branch_type": row.branch_type,
                "is_head_office": row.is_head_office,
                "is_active": row.isactive,
            }
            for row in entity.subentity.all().order_by("sort_order", "subentityname")
        ]
        payload["financial_years"] = [
            {
                "id": row.id,
                "year_code": row.year_code,
                "description": row.desc,
                "period_status": row.period_status,
                "is_active": row.isactive,
                "start": row.finstartyear,
                "end": row.finendyear,
            }
            for row in entity.fy.all().order_by("-finstartyear", "-id")
        ]
    return payload
