from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from entity.models import Entity, EntityFinancialYear, SubEntity
from helpers.models import TrackingModel


ZERO = Decimal("0.00")


class CashFlowForecastAdjustment(TrackingModel):
    class Direction(models.TextChoices):
        INFLOW = "inflow", "Inflow"
        OUTFLOW = "outflow", "Outflow"

    class Scenario(models.TextChoices):
        BASE = "base", "Base"
        CONSERVATIVE = "conservative", "Conservative"
        OPTIMISTIC = "optimistic", "Optimistic"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="cfo_cash_flow_adjustments")
    entityfinid = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    scenario = models.CharField(max_length=20, choices=Scenario.choices, default=Scenario.BASE, db_index=True)
    adjustment_date = models.DateField(db_index=True)
    direction = models.CharField(max_length=10, choices=Direction.choices, db_index=True)
    category = models.CharField(max_length=80, default="manual_adjustment", db_index=True)
    description = models.CharField(max_length=255, blank=True, default="")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    createdby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ("adjustment_date", "id")
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "scenario", "adjustment_date"], name="ix_cfo_cf_adj_scope_dt"),
            models.Index(fields=["entity", "scenario", "isactive"], name="ix_cfo_cf_adj_active"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.adjustment_date}:{self.direction}:{self.amount}"


class MonthClosePeriod(TrackingModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        LOCKED = "locked", "Locked"
        REOPENED = "reopened", "Reopened"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="cfo_month_close_periods")
    entityfinid = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    notes = models.TextField(blank=True, default="")
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-period_end", "-id")
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "period_start", "period_end"], name="ix_cfo_close_scope_period"),
            models.Index(fields=["entity", "status", "period_end"], name="ix_cfo_close_status"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.period_start}:{self.period_end}:{self.status}"


class MonthCloseTask(TrackingModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        REOPENED = "reopened", "Reopened"
        BLOCKED = "blocked", "Blocked"

    close_period = models.ForeignKey(MonthClosePeriod, on_delete=models.CASCADE, related_name="tasks")
    task_code = models.CharField(max_length=80, db_index=True)
    task_label = models.CharField(max_length=160)
    sort_order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    blocker_reason = models.CharField(max_length=255, blank=True, default="")
    evidence_route = models.CharField(max_length=160, blank=True, default="")
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    completed_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reopened_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=["close_period", "task_code"], name="uq_cfo_close_task_code"),
        ]
        indexes = [
            models.Index(fields=["close_period", "status"], name="ix_cfo_close_task_status"),
        ]

    def __str__(self) -> str:
        return f"{self.close_period_id}:{self.task_code}:{self.status}"


class BudgetLine(TrackingModel):
    class Category(models.TextChoices):
        REVENUE = "revenue", "Revenue"
        PURCHASE_EXPENSE = "purchase_expense", "Purchase Expense"
        GROSS_SNAPSHOT = "gross_snapshot", "Gross Snapshot"
        STATUTORY_PAYABLE = "statutory_payable", "Statutory Payable"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="cfo_budget_lines")
    entityfinid = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)
    category = models.CharField(max_length=40, choices=Category.choices, db_index=True)
    budget_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    notes = models.CharField(max_length=255, blank=True, default="")
    createdby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ("period_start", "category", "id")
        constraints = [
            models.UniqueConstraint(fields=["entity", "entityfinid", "subentity", "period_start", "period_end", "category"], name="uq_cfo_budget_scope_cat"),
        ]
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "period_start", "period_end"], name="ix_cfo_budget_scope_period"),
            models.Index(fields=["entity", "category", "isactive"], name="ix_cfo_budget_category"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.period_start}:{self.category}:{self.budget_amount}"


class BudgetVarianceReview(TrackingModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        EXPLAINED = "explained", "Explained"
        ACCEPTED = "accepted", "Accepted"
        ACTION_REQUIRED = "action_required", "Action Required"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="cfo_budget_variance_reviews")
    entityfinid = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)
    category = models.CharField(max_length=40, choices=BudgetLine.Category.choices, db_index=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OPEN, db_index=True)
    explanation = models.TextField(blank=True, default="")
    action_owner = models.CharField(max_length=120, blank=True, default="")
    due_date = models.DateField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("period_start", "category", "id")
        constraints = [
            models.UniqueConstraint(fields=["entity", "entityfinid", "subentity", "period_start", "period_end", "category"], name="uq_cfo_budget_review_scope_cat"),
        ]
        indexes = [
            models.Index(fields=["entity", "status", "period_end"], name="ix_cfo_budget_review_status"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.period_start}:{self.category}:{self.status}"


class CfoRiskReview(TrackingModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="cfo_risk_reviews")
    entityfinid = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    item_key = models.CharField(max_length=180, unique=True, db_index=True)
    risk_type = models.CharField(max_length=60, db_index=True)
    source_type = models.CharField(max_length=60, db_index=True)
    source_id = models.CharField(max_length=80, blank=True, default="")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OPEN, db_index=True)
    note = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        indexes = [
            models.Index(fields=["entity", "status", "risk_type"], name="ix_cfo_risk_status_type"),
            models.Index(fields=["entity", "entityfinid", "subentity", "status"], name="ix_cfo_risk_scope_status"),
        ]

    def __str__(self) -> str:
        return f"{self.item_key}:{self.status}"


class CfoManagementPackSnapshot(TrackingModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="cfo_management_pack_snapshots")
    entityfinid = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)
    title = models.CharField(max_length=180)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")
    createdby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-period_end", "-id")
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "period_start", "period_end"], name="ix_cfo_pack_scope_period"),
            models.Index(fields=["entity", "status", "period_end"], name="ix_cfo_pack_status"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.period_start}:{self.title}:{self.status}"


class CfoEvidenceItem(TrackingModel):
    class EvidenceType(models.TextChoices):
        MANAGEMENT_PACK = "management_pack", "Management Pack"
        RECONCILIATION = "reconciliation", "Reconciliation"
        VARIANCE_REVIEW = "variance_review", "Variance Review"
        RISK_REVIEW = "risk_review", "Risk Review"
        CLOSE_EVIDENCE = "close_evidence", "Close Evidence"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEWED = "reviewed", "Reviewed"
        REJECTED = "rejected", "Rejected"
        ARCHIVED = "archived", "Archived"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="cfo_evidence_items")
    entityfinid = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)
    evidence_type = models.CharField(max_length=40, choices=EvidenceType.choices, default=EvidenceType.OTHER, db_index=True)
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True, default="")
    source_type = models.CharField(max_length=60, blank=True, default="", db_index=True)
    source_id = models.CharField(max_length=80, blank=True, default="")
    source_route = models.CharField(max_length=180, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    owner = models.CharField(max_length=120, blank=True, default="")
    due_date = models.DateField(null=True, blank=True)
    createdby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "period_start", "period_end"], name="ix_cfo_evid_scope_period"),
            models.Index(fields=["entity", "status", "evidence_type"], name="ix_cfo_evid_status_type"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.title}:{self.status}"


class CfoInsightSignal(TrackingModel):
    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="cfo_insight_signals")
    entityfinid = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)
    signal_key = models.CharField(max_length=180, unique=True, db_index=True)
    signal_type = models.CharField(max_length=60, db_index=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM, db_index=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OPEN, db_index=True)
    note = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "period_start", "period_end"], name="ix_cfo_signal_scope_period"),
            models.Index(fields=["entity", "status", "severity"], name="ix_cfo_signal_status_sev"),
        ]

    def __str__(self) -> str:
        return f"{self.signal_key}:{self.status}"


class CfoScenarioPlan(TrackingModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        ARCHIVED = "archived", "Archived"

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="cfo_scenario_plans")
    entityfinid = models.ForeignKey(EntityFinancialYear, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subentity = models.ForeignKey(SubEntity, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)
    title = models.CharField(max_length=180)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    assumptions = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")
    createdby = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        indexes = [
            models.Index(fields=["entity", "entityfinid", "subentity", "period_start", "period_end"], name="ix_cfo_scenario_scope"),
            models.Index(fields=["entity", "status", "period_end"], name="ix_cfo_scenario_status"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_id}:{self.title}:{self.status}"
