from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from entity.models import Entity, SubEntity
from helpers.models import TrackingModel


class Permission(TrackingModel):
    SCOPE_PLATFORM = "platform"
    SCOPE_ENTITY = "entity"
    SCOPE_SUBENTITY = "subentity"
    SCOPE_CUSTOM = "custom"
    SCOPE_CHOICES = (
        (SCOPE_PLATFORM, "Platform"),
        (SCOPE_ENTITY, "Entity"),
        (SCOPE_SUBENTITY, "Sub Entity"),
        (SCOPE_CUSTOM, "Custom"),
    )

    code = models.CharField(max_length=150, unique=True)
    name = models.CharField(max_length=150)
    module = models.CharField(max_length=100)
    resource = models.CharField(max_length=100)
    action = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    scope_type = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_ENTITY)
    is_system_defined = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("module", "resource", "action", "code")
        indexes = [
            models.Index(fields=("module", "resource", "action")),
        ]

    def __str__(self):
        return f"{self.code}"


class Role(TrackingModel):
    LEVEL_PLATFORM = "platform"
    LEVEL_ENTITY = "entity"
    LEVEL_CHOICES = (
        (LEVEL_PLATFORM, "Platform"),
        (LEVEL_ENTITY, "Entity"),
    )

    entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rbac_roles",
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    role_level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default=LEVEL_ENTITY)
    is_system_role = models.BooleanField(default=False)
    is_assignable = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)
    metadata = models.JSONField(default=dict, blank=True)
    createdby = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rbac_roles_created",
    )

    class Meta:
        ordering = ("role_level", "priority", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "code"),
                name="rbac_role_entity_code_unique",
            ),
            models.UniqueConstraint(
                fields=("code",),
                condition=Q(entity__isnull=True),
                name="rbac_role_global_code_unique",
            ),
        ]
        indexes = [
            models.Index(fields=("entity", "isactive")),
            models.Index(fields=("role_level", "code")),
        ]

    def clean(self):
        if self.role_level == self.LEVEL_PLATFORM and self.entity_id is not None:
            raise ValidationError("Platform role cannot be tied to an entity.")
        if self.role_level == self.LEVEL_ENTITY and self.entity_id is None:
            raise ValidationError("Entity role must be tied to an entity.")

    def __str__(self):
        if self.entity_id:
            try:
                return f"{self.entity} | {self.name}"
            except Entity.DoesNotExist:
                return f"Missing Entity ({self.entity_id}) | {self.name}"
        return self.name


class RolePermission(TrackingModel):
    EFFECT_ALLOW = "allow"
    EFFECT_DENY = "deny"
    EFFECT_CHOICES = (
        (EFFECT_ALLOW, "Allow"),
        (EFFECT_DENY, "Deny"),
    )

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    effect = models.CharField(max_length=10, choices=EFFECT_CHOICES, default=EFFECT_ALLOW)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("role", "permission__code")
        constraints = [
            models.UniqueConstraint(
                fields=("role", "permission"),
                name="rbac_role_permission_unique",
            ),
        ]

    def __str__(self):
        return f"{self.role} -> {self.permission}"


class DataAccessPolicy(TrackingModel):
    TYPE_BRANCH = "branch"
    TYPE_DEPARTMENT = "department"
    TYPE_WAREHOUSE = "warehouse"
    TYPE_FINANCIAL_YEAR = "financial_year"
    TYPE_CUSTOM = "custom"
    TYPE_CHOICES = (
        (TYPE_BRANCH, "Branch"),
        (TYPE_DEPARTMENT, "Department"),
        (TYPE_WAREHOUSE, "Warehouse"),
        (TYPE_FINANCIAL_YEAR, "Financial Year"),
        (TYPE_CUSTOM, "Custom"),
    )

    MODE_ALLOW_ALL = "allow_all"
    MODE_INCLUDE = "include"
    MODE_EXCLUDE = "exclude"
    MODE_CUSTOM = "custom"
    MODE_CHOICES = (
        (MODE_ALLOW_ALL, "Allow All"),
        (MODE_INCLUDE, "Include"),
        (MODE_EXCLUDE, "Exclude"),
        (MODE_CUSTOM, "Custom"),
    )

    entity = models.ForeignKey(
        Entity,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="data_access_policies",
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=100)
    policy_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    scope_mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_ALLOW_ALL)
    configuration = models.JSONField(default=dict, blank=True)
    is_system_defined = models.BooleanField(default=False)

    class Meta:
        ordering = ("policy_type", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("entity", "code"),
                name="rbac_policy_entity_code_unique",
            ),
            models.UniqueConstraint(
                fields=("code",),
                condition=Q(entity__isnull=True),
                name="rbac_policy_global_code_unique",
            ),
        ]

    def __str__(self):
        return self.name


class RoleDataAccessPolicy(TrackingModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="data_policies")
    policy = models.ForeignKey(
        DataAccessPolicy,
        on_delete=models.CASCADE,
        related_name="role_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("role", "policy"),
                name="rbac_role_data_policy_unique",
            ),
        ]

    def clean(self):
        if self.policy.entity_id and self.role.entity_id != self.policy.entity_id:
            raise ValidationError("Role and policy must belong to the same entity.")

    def __str__(self):
        role_label = f"Missing Role ({self.role_id})"
        policy_label = f"Missing Policy ({self.policy_id})"
        try:
            role_label = str(self.role)
        except Role.DoesNotExist:
            pass
        try:
            policy_label = str(self.policy)
        except DataAccessPolicy.DoesNotExist:
            pass
        return f"{role_label} -> {policy_label}"


class UserRoleAssignment(TrackingModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rbac_role_assignments",
    )
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="user_role_assignments")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_assignments")
    subentity = models.ForeignKey(
        SubEntity,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rbac_role_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rbac_assignments_created",
    )
    effective_from = models.DateTimeField(null=True, blank=True)
    effective_to = models.DateTimeField(null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    scope_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("entity", "user", "role")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "entity", "role", "subentity"),
                name="rbac_user_entity_role_subentity_unique",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "entity", "isactive")),
            models.Index(fields=("entity", "role", "isactive")),
        ]

    def clean(self):
        if self.role.role_level == Role.LEVEL_ENTITY and self.role.entity_id != self.entity_id:
            raise ValidationError("Assignment entity must match entity-level role entity.")
        if self.subentity_id and self.subentity.entity_id != self.entity_id:
            raise ValidationError("Sub entity must belong to the same entity.")

    def __str__(self):
        labels = [
            f"Missing User ({self.user_id})",
            f"Missing Entity ({self.entity_id})",
            f"Missing Role ({self.role_id})",
        ]
        try:
            labels[0] = str(self.user)
        except Exception:
            pass
        try:
            labels[1] = str(self.entity)
        except Entity.DoesNotExist:
            pass
        try:
            labels[2] = str(self.role)
        except Role.DoesNotExist:
            pass
        return " | ".join(labels)


class Menu(TrackingModel):
    TYPE_GROUP = "group"
    TYPE_SCREEN = "screen"
    TYPE_EXTERNAL = "external"
    TYPE_ACTION = "action"
    TYPE_CHOICES = (
        (TYPE_GROUP, "Group"),
        (TYPE_SCREEN, "Screen"),
        (TYPE_EXTERNAL, "External"),
        (TYPE_ACTION, "Action"),
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=150, unique=True)
    menu_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_SCREEN)
    route_path = models.CharField(max_length=255, blank=True)
    route_name = models.CharField(max_length=150, blank=True)
    icon = models.CharField(max_length=100, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    depth = models.PositiveSmallIntegerField(default=0, editable=False)
    is_system_menu = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("parent_id", "sort_order", "name")
        constraints = [
            models.CheckConstraint(
                check=Q(sort_order__gte=0),
                name="rbac_menu_sort_order_check",
            ),
        ]
        indexes = [
            models.Index(fields=("parent", "sort_order")),
        ]

    def clean(self):
        if self.parent_id == self.id and self.id is not None:
            raise ValidationError("Menu cannot be parent of itself.")

        ancestor = self.parent
        visited = {self.id} if self.id else set()
        while ancestor is not None:
            if ancestor.id in visited:
                raise ValidationError("Menu hierarchy cannot contain cycles.")
            visited.add(ancestor.id)
            ancestor = ancestor.parent

    def save(self, *args, **kwargs):
        self.depth = self.parent.depth + 1 if self.parent_id else 0
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class MenuPermission(TrackingModel):
    RELATION_VISIBILITY = "visibility"
    RELATION_ACTION = "action"
    RELATION_CHOICES = (
        (RELATION_VISIBILITY, "Visibility"),
        (RELATION_ACTION, "Action"),
    )

    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name="menu_permissions")
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="menu_permissions",
    )
    relation_type = models.CharField(
        max_length=20,
        choices=RELATION_CHOICES,
        default=RELATION_VISIBILITY,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("menu", "permission", "relation_type"),
                name="rbac_menu_permission_unique",
            ),
        ]

    def __str__(self):
        return f"{self.menu} -> {self.permission}"
