# RBAC Menu Setup

This document explains how to create multi-level menus in RBAC from Django admin and why a menu may not appear in `/api/rbac/me/menus`.

## Core rule

Menu visibility is not controlled only by the `Menu` table.

A menu appears for a user only when all of these are true:

1. The `Menu` row exists and is active.
2. A `Permission` row exists for that menu or screen.
3. A `MenuPermission` row links the menu to the permission.
4. A `RolePermission` row grants that permission to the user's role.
5. The user has that role in the selected entity.

Effective flow:

`User -> Role Assignment -> Role Permission -> Menu Permission -> Menu Tree`

## Recommended menu coding style

Use hierarchical `code` values.

Examples:

- `statutory`
- `statutory.tcs`
- `statutory.tcs.config`
- `statutory.tds`
- `statutory.tds.sections`

This keeps menu identity stable and makes admin setup easier to reason about.

## Menu types

Use these values:

- `group`
  For a container node that has children and usually no page of its own.
- `screen`
  For an actual navigable page.

## Example hierarchy

Target structure:

- `Statutory`
  - `TCS`
    - `Configuration`
    - `Sections`
    - `Rules`
  - `TDS`
    - `Configuration`
    - `Sections`
    - `Rates`

## Admin setup order

Create data in this order:

1. `RBAC > Menu`
2. `RBAC > Permission`
3. `RBAC > Menu Permission`
4. `RBAC > Role Permission`
5. `RBAC > User Role Assignment` if role assignment is not already present

If you skip steps 2 to 4, the menu will exist in admin but will not show in `/api/rbac/me/menus`.

## Example: create TDS under Statutory

### 1. Create menus

Assuming `Statutory` already exists.

Create parent group:

- `name`: `TDS`
- `code`: `statutory.tds`
- `parent`: `Statutory`
- `menu_type`: `group`
- `route_path`: blank
- `route_name`: `tds`
- `sort_order`: `2`
- `isactive`: `True`

Create child screen:

- `name`: `Configuration`
- `code`: `statutory.tds.config`
- `parent`: `TDS`
- `menu_type`: `screen`
- `route_path`: `tdsconfig`
- `route_name`: `tdsconfig`
- `sort_order`: `1`
- `isactive`: `True`

Create child screen:

- `name`: `Sections`
- `code`: `statutory.tds.sections`
- `parent`: `TDS`
- `menu_type`: `screen`
- `route_path`: `tdssections`
- `route_name`: `tdssections`
- `sort_order`: `2`
- `isactive`: `True`

Create child screen:

- `name`: `Rates`
- `code`: `statutory.tds.rates`
- `parent`: `TDS`
- `menu_type`: `screen`
- `route_path`: `tdsrates`
- `route_name`: `tdsrates`
- `sort_order`: `3`
- `isactive`: `True`

### 2. Create permissions

Create these permission codes:

- `tds.menu.access`
- `tds.config.view`
- `tds.sections.view`
- `tds.rates.view`

Recommended names:

- `TDS Menu Access`
- `View TDS Configuration`
- `View TDS Sections`
- `View TDS Rates`

### 3. Link menus to permissions

In `RBAC > Menu Permission`, create:

- menu `statutory.tds` -> permission `tds.menu.access`
- menu `statutory.tds.config` -> permission `tds.config.view`
- menu `statutory.tds.sections` -> permission `tds.sections.view`
- menu `statutory.tds.rates` -> permission `tds.rates.view`

### 4. Grant permissions to a role

For the target role, for example `legacy_role_2` or `Admin`, add:

- `tds.menu.access`
- `tds.config.view`
- `tds.sections.view`
- `tds.rates.view`

## API checks

### Check effective permissions

Call:

```http
GET /api/rbac/me/permissions?entity=32
Authorization: Bearer <token>
```

Expected to include:

- `tds.menu.access`
- `tds.config.view`
- `tds.sections.view`
- `tds.rates.view`

If they are missing, the role-permission setup is incomplete.

### Check menu tree

Call:

```http
GET /api/rbac/me/menus?entity=32
Authorization: Bearer <token>
```

Expected output under `Statutory`:

- `TCS`
- `TDS`

And under `TDS`:

- `Configuration`
- `Sections`
- `Rates`

## Troubleshooting

### Menu exists in admin but does not show in API

Most common causes:

1. `Permission` row not created
2. `MenuPermission` row missing
3. `RolePermission` row missing
4. User does not have the role in that entity
5. Menu or permission is inactive

### Parent menu does not show

The parent also needs a permission mapping if visibility is controlled at the parent level.

Example:

- `statutory.tds` should map to `tds.menu.access`

### Child menu does not show

Check both:

- child screen permission exists
- child screen permission is granted to the role

### Duplicate-looking menus

Avoid reusing legacy flat codes like `tcsconfig` as the unique menu identity for new hierarchy work.
Use hierarchical codes instead:

- good: `statutory.tcs.config`
- avoid as primary identity: `tcsconfig`

Route names and route paths can still stay simple if needed.

## Recommended future pattern

For all new menus:

1. Create hierarchical `code`
2. Use `group` for containers and `screen` for pages
3. Create one menu access permission for each group
4. Create action/view permissions for each screen
5. Map screens through `MenuPermission`
6. Grant through `RolePermission`

This keeps menu design scalable for multi-level navigation and entity-specific RBAC.
