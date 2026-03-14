from django.db import migrations


ROLE_PERMISSION_ALLOW = "allow"
PERMISSION_SCOPE_ENTITY = "entity"
CATALOG_VERSION = "frontend_permission_catalog_2026_03"

CANONICAL_PERMISSIONS = [
    ("admin.branch.create", "Create Branch", "admin", "branch", "create"),
    ("admin.branch.delete", "Delete Branch", "admin", "branch", "delete"),
    ("admin.branch.edit", "Edit Branch", "admin", "branch", "edit"),
    ("admin.branch.update", "Update Branch", "admin", "branch", "update"),
    ("admin.branch.view", "View Branch", "admin", "branch", "view"),
    ("admin.configuration.edit", "Edit Configuration", "admin", "configuration", "edit"),
    ("admin.configuration.update", "Update Configuration", "admin", "configuration", "update"),
    ("admin.entityfinyear.create", "Create Financial Year", "admin", "entityfinyear", "create"),
    ("admin.entityfinyear.update", "Update Financial Year", "admin", "entityfinyear", "update"),
    ("admin.role.create", "Create Role", "admin", "role", "create"),
    ("admin.role.delete", "Delete Role", "admin", "role", "delete"),
    ("admin.role.edit", "Edit Role", "admin", "role", "edit"),
    ("admin.role.update", "Update Role", "admin", "role", "update"),
    ("admin.role.view", "View Role", "admin", "role", "view"),
    ("admin.staticaccount.edit", "Edit Static Account", "admin", "staticaccount", "edit"),
    ("admin.staticaccount.update", "Update Static Account", "admin", "staticaccount", "update"),
    ("admin.user.create", "Create User", "admin", "user", "create"),
    ("admin.user.edit", "Edit User", "admin", "user", "edit"),
    ("admin.user.update", "Update User", "admin", "user", "update"),
    ("admin.user.view", "View User", "admin", "user", "view"),

    ("sales.invoice.cancel", "Cancel Sales Invoice", "sales", "invoice", "cancel"),
    ("sales.invoice.confirm", "Confirm Sales Invoice", "sales", "invoice", "confirm"),
    ("sales.invoice.create", "Create Sales Invoice", "sales", "invoice", "create"),
    ("sales.invoice.edit", "Edit Sales Invoice", "sales", "invoice", "edit"),
    ("sales.invoice.post", "Post Sales Invoice", "sales", "invoice", "post"),
    ("sales.invoice.update", "Update Sales Invoice", "sales", "invoice", "update"),
    ("sales.invoice.view", "View Sales Invoice", "sales", "invoice", "view"),

    ("purchase.invoice.cancel", "Cancel Purchase Invoice", "purchase", "invoice", "cancel"),
    ("purchase.invoice.confirm", "Confirm Purchase Invoice", "purchase", "invoice", "confirm"),
    ("purchase.invoice.create", "Create Purchase Invoice", "purchase", "invoice", "create"),
    ("purchase.invoice.edit", "Edit Purchase Invoice", "purchase", "invoice", "edit"),
    ("purchase.invoice.post", "Post Purchase Invoice", "purchase", "invoice", "post"),
    ("purchase.invoice.update", "Update Purchase Invoice", "purchase", "invoice", "update"),
    ("purchase.invoice.view", "View Purchase Invoice", "purchase", "invoice", "view"),

    ("stock.management.create", "Create Stock Management", "stock", "management", "create"),
    ("stock.management.edit", "Edit Stock Management", "stock", "management", "edit"),
    ("stock.management.update", "Update Stock Management", "stock", "management", "update"),
    ("stock.product.barcode", "Generate Product Barcode", "stock", "product", "barcode"),
    ("stock.product.bulk_insert", "Bulk Insert Product", "stock", "product", "bulk_insert"),
    ("stock.product.create", "Create Product", "stock", "product", "create"),
    ("stock.product.delete", "Delete Product", "stock", "product", "delete"),
    ("stock.product.edit", "Edit Product", "stock", "product", "edit"),
    ("stock.product.update", "Update Product", "stock", "product", "update"),
    ("stock.productcategory.create", "Create Product Category", "stock", "productcategory", "create"),
    ("stock.productcategory.delete", "Delete Product Category", "stock", "productcategory", "delete"),
    ("stock.productcategory.edit", "Edit Product Category", "stock", "productcategory", "edit"),
    ("stock.productcategory.update", "Update Product Category", "stock", "productcategory", "update"),
    ("stock.voucher.cancel", "Cancel Stock Voucher", "stock", "voucher", "cancel"),
    ("stock.voucher.create", "Create Stock Voucher", "stock", "voucher", "create"),
    ("stock.voucher.edit", "Edit Stock Voucher", "stock", "voucher", "edit"),
    ("stock.voucher.update", "Update Stock Voucher", "stock", "voucher", "update"),

    ("payment.voucher.approve", "Approve Payment Voucher", "payment", "voucher", "approve"),
    ("payment.voucher.cancel", "Cancel Payment Voucher", "payment", "voucher", "cancel"),
    ("payment.voucher.confirm", "Confirm Payment Voucher", "payment", "voucher", "confirm"),
    ("payment.voucher.create", "Create Payment Voucher", "payment", "voucher", "create"),
    ("payment.voucher.delete", "Delete Payment Voucher", "payment", "voucher", "delete"),
    ("payment.voucher.edit", "Edit Payment Voucher", "payment", "voucher", "edit"),
    ("payment.voucher.post", "Post Payment Voucher", "payment", "voucher", "post"),
    ("payment.voucher.reject", "Reject Payment Voucher", "payment", "voucher", "reject"),
    ("payment.voucher.submit", "Submit Payment Voucher", "payment", "voucher", "submit"),
    ("payment.voucher.submit_approval", "Submit Payment Voucher For Approval", "payment", "voucher", "submit_approval"),
    ("payment.voucher.unpost", "Unpost Payment Voucher", "payment", "voucher", "unpost"),
    ("payment.voucher.update", "Update Payment Voucher", "payment", "voucher", "update"),

    ("receipt.voucher.approve", "Approve Receipt Voucher", "receipt", "voucher", "approve"),
    ("receipt.voucher.cancel", "Cancel Receipt Voucher", "receipt", "voucher", "cancel"),
    ("receipt.voucher.confirm", "Confirm Receipt Voucher", "receipt", "voucher", "confirm"),
    ("receipt.voucher.create", "Create Receipt Voucher", "receipt", "voucher", "create"),
    ("receipt.voucher.delete", "Delete Receipt Voucher", "receipt", "voucher", "delete"),
    ("receipt.voucher.edit", "Edit Receipt Voucher", "receipt", "voucher", "edit"),
    ("receipt.voucher.post", "Post Receipt Voucher", "receipt", "voucher", "post"),
    ("receipt.voucher.reject", "Reject Receipt Voucher", "receipt", "voucher", "reject"),
    ("receipt.voucher.submit", "Submit Receipt Voucher", "receipt", "voucher", "submit"),
    ("receipt.voucher.submit_approval", "Submit Receipt Voucher For Approval", "receipt", "voucher", "submit_approval"),
    ("receipt.voucher.unpost", "Unpost Receipt Voucher", "receipt", "voucher", "unpost"),
    ("receipt.voucher.update", "Update Receipt Voucher", "receipt", "voucher", "update"),

    ("production.voucher.cancel", "Cancel Production Voucher", "production", "voucher", "cancel"),
    ("production.voucher.create", "Create Production Voucher", "production", "voucher", "create"),
    ("production.voucher.edit", "Edit Production Voucher", "production", "voucher", "edit"),
    ("production.voucher.update", "Update Production Voucher", "production", "voucher", "update"),

    ("tds.voucher.cancel", "Cancel TDS Voucher", "tds", "voucher", "cancel"),
    ("tds.voucher.create", "Create TDS Voucher", "tds", "voucher", "create"),
    ("tds.voucher.edit", "Edit TDS Voucher", "tds", "voucher", "edit"),
    ("tds.voucher.update", "Update TDS Voucher", "tds", "voucher", "update"),

    ("credit.note.cancel", "Cancel Credit Note", "credit", "note", "cancel"),
    ("credit.note.create", "Create Credit Note", "credit", "note", "create"),
    ("credit.note.edit", "Edit Credit Note", "credit", "note", "edit"),
    ("credit.note.update", "Update Credit Note", "credit", "note", "update"),
    ("debit.note.cancel", "Cancel Debit Note", "debit", "note", "cancel"),
    ("debit.note.create", "Create Debit Note", "debit", "note", "create"),
    ("debit.note.edit", "Edit Debit Note", "debit", "note", "edit"),
    ("debit.note.update", "Update Debit Note", "debit", "note", "update"),

    ("tcs.config.delete", "Delete TCS Config", "tcs", "config", "delete"),
    ("tcs.config.edit", "Edit TCS Config", "tcs", "config", "edit"),
    ("tcs.config.update", "Update TCS Config", "tcs", "config", "update"),
    ("tcs.partyprofile.delete", "Delete TCS Party Profile", "tcs", "partyprofile", "delete"),
    ("tcs.partyprofile.edit", "Edit TCS Party Profile", "tcs", "partyprofile", "edit"),
    ("tcs.partyprofile.update", "Update TCS Party Profile", "tcs", "partyprofile", "update"),

    ("payroll.compensation.calculate", "Calculate Compensation", "payroll", "compensation", "calculate"),
    ("payroll.compensation.update", "Update Compensation", "payroll", "compensation", "update"),
    ("payroll.employee.create", "Create Employee", "payroll", "employee", "create"),
    ("payroll.employee.delete", "Delete Employee", "payroll", "employee", "delete"),
    ("payroll.employee.edit", "Edit Employee", "payroll", "employee", "edit"),
    ("payroll.employee.update", "Update Employee", "payroll", "employee", "update"),
    ("payroll.salarycomponent.create", "Create Salary Component", "payroll", "salarycomponent", "create"),
    ("payroll.salarycomponent.delete", "Delete Salary Component", "payroll", "salarycomponent", "delete"),
    ("payroll.salarycomponent.edit", "Edit Salary Component", "payroll", "salarycomponent", "edit"),
    ("payroll.salarycomponent.update", "Update Salary Component", "payroll", "salarycomponent", "update"),
]

ALIAS_PERMISSIONS = [
    ("bulkinsertproduct.create", "Alias Bulk Insert Product", "stock.product.bulk_insert"),
    ("compensation.edit", "Alias Edit Compensation", "payroll.compensation.update"),
    ("creditnote.cancel", "Alias Cancel Credit Note", "credit.note.cancel"),
    ("creditnote.create", "Alias Create Credit Note", "credit.note.create"),
    ("creditnote.edit", "Alias Edit Credit Note", "credit.note.edit"),
    ("debitnote.cancel", "Alias Cancel Debit Note", "debit.note.cancel"),
    ("debitnote.create", "Alias Create Debit Note", "debit.note.create"),
    ("debitnote.edit", "Alias Edit Debit Note", "debit.note.edit"),
    ("employee.create", "Alias Create Employee", "payroll.employee.create"),
    ("employee.delete", "Alias Delete Employee", "payroll.employee.delete"),
    ("employee.edit", "Alias Edit Employee", "payroll.employee.edit"),
    ("paymentvoucher.create", "Alias Create Payment Voucher", "payment.voucher.create"),
    ("paymentvoucher.edit", "Alias Edit Payment Voucher", "payment.voucher.edit"),
    ("product.create", "Alias Create Product", "stock.product.create"),
    ("product.delete", "Alias Delete Product", "stock.product.delete"),
    ("product.edit", "Alias Edit Product", "stock.product.edit"),
    ("productcategory.create", "Alias Create Product Category", "stock.productcategory.create"),
    ("productcategory.delete", "Alias Delete Product Category", "stock.productcategory.delete"),
    ("productcategory.edit", "Alias Edit Product Category", "stock.productcategory.edit"),
    ("productionvoucher.cancel", "Alias Cancel Production Voucher", "production.voucher.cancel"),
    ("productionvoucher.create", "Alias Create Production Voucher", "production.voucher.create"),
    ("productionvoucher.edit", "Alias Edit Production Voucher", "production.voucher.edit"),
    ("receiptvoucher.create", "Alias Create Receipt Voucher", "receipt.voucher.create"),
    ("receiptvoucher.edit", "Alias Edit Receipt Voucher", "receipt.voucher.edit"),
    ("salarycomponent.create", "Alias Create Salary Component", "payroll.salarycomponent.create"),
    ("salarycomponent.delete", "Alias Delete Salary Component", "payroll.salarycomponent.delete"),
    ("salarycomponent.edit", "Alias Edit Salary Component", "payroll.salarycomponent.edit"),
    ("stockmanagement.create", "Alias Create Stock Management", "stock.management.create"),
    ("stockmanagement.edit", "Alias Edit Stock Management", "stock.management.edit"),
    ("stockvoucher.cancel", "Alias Cancel Stock Voucher", "stock.voucher.cancel"),
    ("stockvoucher.create", "Alias Create Stock Voucher", "stock.voucher.create"),
    ("stockvoucher.edit", "Alias Edit Stock Voucher", "stock.voucher.edit"),
    ("tdsvoucher.cancel", "Alias Cancel TDS Voucher", "tds.voucher.cancel"),
    ("tdsvoucher.create", "Alias Create TDS Voucher", "tds.voucher.create"),
    ("tdsvoucher.edit", "Alias Edit TDS Voucher", "tds.voucher.edit"),

    ("admin.finyear.view", "Alias View Financial Year", "admin.entityfinyear.view"),
    ("admin.finyear.create", "Alias Create Financial Year", "admin.entityfinyear.create"),
    ("admin.finyear.update", "Alias Update Financial Year", "admin.entityfinyear.update"),
    ("admin.finyear.delete", "Alias Delete Financial Year", "admin.entityfinyear.delete"),
    ("tcs.party_profile.view", "Alias View TCS Party Profile", "tcs.partyprofile.view"),
    ("tcs.party_profile.create", "Alias Create TCS Party Profile", "tcs.partyprofile.create"),
    ("tcs.party_profile.update", "Alias Update TCS Party Profile", "tcs.partyprofile.update"),
    ("tcs.party_profile.delete", "Alias Delete TCS Party Profile", "tcs.partyprofile.delete"),
]


def _canonical_specs():
    specs = list(CANONICAL_PERMISSIONS)
    missing = {
        ("admin.entityfinyear.view", "View Financial Year", "admin", "entityfinyear", "view"),
        ("admin.entityfinyear.delete", "Delete Financial Year", "admin", "entityfinyear", "delete"),
        ("tcs.partyprofile.view", "View TCS Party Profile", "tcs", "partyprofile", "view"),
        ("tcs.partyprofile.create", "Create TCS Party Profile", "tcs", "partyprofile", "create"),
    }
    specs.extend([row for row in missing if row not in specs])
    return specs


def forwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_ids = []
    for code, name, module, resource, action in _canonical_specs():
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": name,
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {"seed": "frontend_permission_catalog", "catalog_version": CATALOG_VERSION, "kind": "canonical"},
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    canonical_map = {code: (module, resource, action) for code, _, module, resource, action in _canonical_specs()}
    for code, name, alias_of in ALIAS_PERMISSIONS:
        target = canonical_map.get(alias_of)
        module, resource, action = target if target else ("alias", "permission", "alias")
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "module": module,
                "resource": resource,
                "action": action,
                "description": f"Temporary alias for {alias_of}",
                "scope_type": PERMISSION_SCOPE_ENTITY,
                "is_system_defined": True,
                "metadata": {"seed": "frontend_permission_catalog", "catalog_version": CATALOG_VERSION, "kind": "alias", "alias_of": alias_of},
                "isactive": True,
            },
        )
        permission_ids.append(permission.id)

    super_admin_role_ids = list(Role.objects.filter(code="entity.super_admin", isactive=True).values_list("id", flat=True))
    existing_pairs = set(
        RolePermission.objects.filter(role_id__in=super_admin_role_ids, permission_id__in=permission_ids).values_list("role_id", "permission_id")
    )
    inserts = []
    for role_id in super_admin_role_ids:
        for permission_id in permission_ids:
            if (role_id, permission_id) in existing_pairs:
                continue
            inserts.append(
                RolePermission(
                    role_id=role_id,
                    permission_id=permission_id,
                    effect=ROLE_PERMISSION_ALLOW,
                    metadata={"seed": "frontend_permission_catalog", "catalog_version": CATALOG_VERSION},
                    isactive=True,
                )
            )
    if inserts:
        RolePermission.objects.bulk_create(inserts)


def backwards(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    RolePermission = apps.get_model("rbac", "RolePermission")

    permission_codes = [row[0] for row in _canonical_specs()] + [row[0] for row in ALIAS_PERMISSIONS]
    permission_ids = list(Permission.objects.filter(code__in=permission_codes).values_list("id", flat=True))
    if permission_ids:
        RolePermission.objects.filter(permission_id__in=permission_ids).delete()
        Permission.objects.filter(id__in=permission_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0016_seed_modern_permission_master"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
