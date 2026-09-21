# RBAC Onboarding Browser Certification - 2026-09-21

## Scope

Certified the production-like onboarding and RBAC access flow for a new Enterprise tenant.

Flow covered:

- Platform admin validates onboarding payload.
- Platform admin creates and executes onboarding operation.
- New tenant owner is provisioned as Entity Super Admin.
- Entity Super Admin creates one user under each launch role.
- Each role user logs in and receives tenant-scoped roles, permissions, and menu tree.
- Browser route access is verified for allowed and forbidden routes per role.

## Certified Tenant

- Entity: Ansh-B QA 1789975603499
- Entity ID: 181
- Subscription plan: enterprise
- Active roles: 20
- Active role assignments: 21
  - 1 owner Entity Super Admin assignment
  - 20 role-user assignments

## Roles Certified

- Entity Super Admin
- Admin
- Accounts Manager
- Sales User
- Purchase User
- Financial Report Viewer
- Payables User
- Receivables User
- Asset Manager
- Inventory User
- Manufacturing User
- Treasury User
- Treasury Approver
- Compliance User
- GST Reviewer
- HRMS User
- HRMS Approver
- Payroll User
- Payroll Approver
- Payroll Finance Manager

## Browser Certification Result

Command:

```bash
npx playwright test playwright/tests/platform-onboarding-rbac-cert.live.spec.ts --project=chromium
```

Result:

```text
1 passed
```

Backend checks:

```text
rbac.tests.test_access_catalog: 15 passed
```

Frontend checks:

```text
npx tsc --noEmit --pretty false --project tsconfig.json: passed
```

## Defects Found And Fixed

### RBAC admin mutation permissions missing from canonical catalog

Finding:

- New Entity Super Admin could see RBAC admin screens but could not create role users.
- API returned 403 for `POST /api/rbac/admin/users/create-and-assign`.

Fix:

- Added canonical RBAC admin mutation permissions to the RBAC feature permission set:
  - `admin.user.create`
  - `admin.user.update`
  - `admin.user.delete`
  - `admin.user_access.view`
  - `admin.user_access.update`
  - `admin.role.create`
  - `admin.role.update`
  - `admin.role.delete`
  - `admin.role_access.update`
  - `admin.menu.view`
  - `admin.menu.update`

### Approver and payroll finance roles had incomplete explicit permissions

Finding:

- Treasury/HRMS/Payroll approver roles and Payroll Finance Manager had incomplete explicit role-permission definitions.
- Payroll Finance Manager did not receive Accounts visibility.

Fix:

- Added explicit role permissions for:
  - Treasury Approver
  - HRMS Approver
  - Payroll Approver
  - Payroll Finance Manager

## Certification Decision

Local certification is passed for:

- New Enterprise tenant onboarding.
- Automatic launch role creation.
- Entity owner super-admin assignment.
- One-user-per-role assignment workflow.
- Role-scoped menu payloads.
- Browser route allow/deny behavior for certified launch routes.

Stage deployment should run the same certification after migrations are applied.
