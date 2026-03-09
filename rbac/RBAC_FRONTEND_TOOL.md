# RBAC Frontend Tool

This document describes the business-facing RBAC management flow and the APIs to use for it.

The goal is to let business users manage:

- roles
- menu hierarchy
- role permissions
- menu visibility permissions
- user role assignments
- effective access preview
- change history

All without needing Django admin.

## Recommended screen flow

Build one RBAC setup screen per entity with these tabs:

1. `Roles`
2. `Menus`
3. `Role Access`
4. `User Assignments`
5. `Access Preview`
6. `Audit Logs`

The screen should always begin with an entity selector.

## One-call bootstrap

Use this first:

```http
GET /api/rbac/admin/bootstrap?entity=<entity_id>
Authorization: Bearer <token>
```

This returns:

- entity info
- roles
- full permission catalog
- grouped permissions
- menu tree
- current user-role assignments
- users already linked to the entity

This is the main page-load API for the RBAC tool.

## APIs

### 1. Bootstrap

```http
GET /api/rbac/admin/bootstrap?entity=32
```

### 2. Entity users

```http
GET /api/rbac/admin/users?entity=32
```

### 3. Effective access preview

```http
GET /api/rbac/admin/access-preview?entity=32&user_id=15
```

Use this to show:

- effective roles
- effective permissions
- grouped permissions
- effective menu tree

### 4. Permissions

List:

```http
GET /api/rbac/admin/permissions
GET /api/rbac/admin/permissions?module=sales
GET /api/rbac/admin/permissions?search=invoice
```

Create:

```http
POST /api/rbac/admin/permissions
Content-Type: application/json

{
  "code": "tds.rates.view",
  "name": "View TDS Rates",
  "module": "tds",
  "resource": "rates",
  "action": "view",
  "description": "Allows viewing TDS rate screen",
  "scope_type": "entity",
  "is_system_defined": false,
  "metadata": {},
  "isactive": true
}
```

Update:

```http
PATCH /api/rbac/admin/permissions/<permission_id>
```

Deactivate:

```http
DELETE /api/rbac/admin/permissions/<permission_id>
```

Delete is soft-delete.

### 5. Roles

List:

```http
GET /api/rbac/admin/roles?entity=32
GET /api/rbac/admin/roles?entity=32&search=sales
```

Create:

```http
POST /api/rbac/admin/roles?entity=32
Content-Type: application/json

{
  "name": "Sales Manager",
  "code": "sales_manager",
  "description": "Sales manager for entity",
  "is_system_role": false,
  "is_assignable": true,
  "priority": 20,
  "metadata": {},
  "isactive": true
}
```

Update:

```http
PATCH /api/rbac/admin/roles/<role_id>
```

Deactivate:

```http
DELETE /api/rbac/admin/roles/<role_id>
```

Delete is soft-delete.
System roles should not be editable/deletable from business UI.

Clone:

```http
POST /api/rbac/admin/roles/<role_id>/clone
Content-Type: application/json

{
  "name": "Sales Manager Copy",
  "code": "sales_manager_copy",
  "description": "Copied role"
}
```

### 6. Role templates

List templates:

```http
GET /api/rbac/admin/templates
```

Apply template:

```http
POST /api/rbac/admin/roles/<role_id>/apply-template
Content-Type: application/json

{
  "template_code": "sales",
  "permission_ids": []
}
```

If `permission_ids` is empty, backend applies all active permissions for that module template.

### 7. Menus

Flat list:

```http
GET /api/rbac/admin/menus
GET /api/rbac/admin/menus?parent=null
GET /api/rbac/admin/menus?parent=<menu_id>
GET /api/rbac/admin/menus?search=tds
```

Recursive tree:

```http
GET /api/rbac/admin/menu-tree
```

Create:

```http
POST /api/rbac/admin/menus
Content-Type: application/json

{
  "parent": 318,
  "name": "TDS",
  "code": "statutory.tds",
  "menu_type": "group",
  "route_path": "",
  "route_name": "tds",
  "icon": "",
  "sort_order": 2,
  "is_system_menu": false,
  "metadata": {},
  "isactive": true
}
```

Create child:

```http
POST /api/rbac/admin/menus
Content-Type: application/json

{
  "parent": 319,
  "name": "Configuration",
  "code": "statutory.tds.config",
  "menu_type": "screen",
  "route_path": "tdsconfig",
  "route_name": "tdsconfig",
  "icon": "",
  "sort_order": 1,
  "is_system_menu": false,
  "metadata": {},
  "isactive": true
}
```

Update:

```http
PATCH /api/rbac/admin/menus/<menu_id>
```

Deactivate:

```http
DELETE /api/rbac/admin/menus/<menu_id>
```

Delete is soft-delete.

### 8. Role permissions

Get current selection:

```http
GET /api/rbac/admin/roles/<role_id>/permissions
```

Replace full set:

```http
PUT /api/rbac/admin/roles/<role_id>/permissions
Content-Type: application/json

{
  "permission_ids": [1, 2, 3, 4]
}
```

This endpoint is intended for a checkbox UI.
Frontend should send the complete selected permission list.

### 9. Menu permissions

Get current selection:

```http
GET /api/rbac/admin/menus/<menu_id>/permissions
GET /api/rbac/admin/menus/<menu_id>/permissions?relation_type=visibility
```

Replace full set:

```http
PUT /api/rbac/admin/menus/<menu_id>/permissions
Content-Type: application/json

{
  "relation_type": "visibility",
  "permission_ids": [21, 22]
}
```

### 10. User role assignments

List:

```http
GET /api/rbac/admin/assignments?entity=32
GET /api/rbac/admin/assignments?entity=32&search=admin
```

Create:

```http
POST /api/rbac/admin/assignments?entity=32
Content-Type: application/json

{
  "user": 15,
  "role": 4,
  "subentity": null,
  "effective_from": null,
  "effective_to": null,
  "is_primary": true,
  "scope_data": {},
  "isactive": true
}
```

Update:

```http
PATCH /api/rbac/admin/assignments/<assignment_id>
```

Deactivate:

```http
DELETE /api/rbac/admin/assignments/<assignment_id>
```

Bulk assign:

```http
POST /api/rbac/admin/assignments/bulk?entity=32
Content-Type: application/json

{
  "user_ids": [15, 16, 17],
  "role": 4,
  "subentity": null,
  "is_primary": false,
  "isactive": true,
  "scope_data": {}
}
```

Delete is soft-delete.

### 11. Audit logs

```http
GET /api/rbac/admin/audit-logs?entity=32
GET /api/rbac/admin/audit-logs?entity=32&object_type=role
GET /api/rbac/admin/audit-logs?entity=32&action=clone
```

## Recommended business-user UX

### Roles tab

Show:

- role name
- description
- priority
- permission count
- user count
- active/inactive

Primary actions:

- add role
- edit role
- open `Role Access`
- deactivate role
- clone role
- apply module template

### Menus tab

Show recursive tree with:

- name
- code
- type
- route
- sort order
- active/inactive

Primary actions:

- add child menu
- edit menu
- map menu permissions
- deactivate menu

### Role Access tab

Show:

- one selected role
- grouped permission checklist by module and resource
- save button

### User Assignments tab

Show:

- user
- role
- subentity
- primary yes/no
- active yes/no
- effective from
- effective to

Primary actions:

- add assignment
- change role
- deactivate assignment
- bulk assign

### Access Preview tab

Show:

- selected user
- effective roles
- effective permissions
- grouped permissions
- effective menu tree

Use this mainly for debugging and support.

### Audit Logs tab

Show:

- timestamp
- object type
- action
- actor
- message

## Recommended frontend order of calls

1. User selects entity
2. Call `/api/rbac/admin/bootstrap?entity=<id>`
3. Render tabs from bootstrap payload
4. On save:
   - role changes -> `/admin/roles`
   - role permission changes -> `/admin/roles/<id>/permissions`
   - role clone -> `/admin/roles/<id>/clone`
   - role template apply -> `/admin/roles/<id>/apply-template`
   - menu changes -> `/admin/menus`
   - menu permission changes -> `/admin/menus/<id>/permissions`
   - assignment changes -> `/admin/assignments`
   - bulk assignment -> `/admin/assignments/bulk`
5. Reload bootstrap after each write

For preview and audit tabs, load on demand.

## Important frontend rules

- Do not rebuild permission logic in frontend.
- Treat delete as deactivate in UI wording.
- Hide destructive actions for system roles.
- Show grouped permissions, not one flat technical list.

Backend remains the source of truth for:

- effective roles
- effective permissions
- deny precedence
- assignment validity windows
- menu visibility

## Business-friendly wording

Avoid showing technical words like:

- `MenuPermission`
- `RolePermission`
- `scope_data`

Prefer labels like:

- `Menu Access Rules`
- `Role Access`
- `Allowed Screens`
- `User Access`
- `Access Preview`
- `Change History`

This makes the tool easier for business users.
