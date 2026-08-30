from django.db import migrations
from django.db.models import Q


LEGACY_MENU_CODES = (
    "admin.payroll",
    "admin.payroll.salarycomponent",
    "admin.payroll.employee",
    "admin.payroll.employeesalary",
    "admin.payroll.payrollstructure",
    "admin.payroll.compensation",
    "admin.payroll.emicalculator",
    "admin.salarycomponent",
    "admin.employee",
    "admin.employeesalary",
    "admin.payrollstructure",
    "admin.compensation",
    "admin.emicalculator",
    "payroll.payroll",
    "payroll.salarycomponent",
    "payroll.employee",
    "payroll.employeesalary",
    "payroll.payrollstructure",
    "payroll.compensation",
    "payroll.emicalculator",
)

LEGACY_ROUTE_PATHS = (
    "salarycomponent",
    "employee",
    "employeesalary",
    "payrollstructure",
    "compensation",
    "emicalculator",
    "/salarycomponent",
    "/employee",
    "/employeesalary",
    "/payrollstructure",
    "/compensation",
    "/emicalculator",
)


def forwards(apps, schema_editor):
    Menu = apps.get_model("rbac", "Menu")
    MenuPermission = apps.get_model("rbac", "MenuPermission")

    legacy_menu_ids = list(
        (
            Menu.objects.filter(code__in=LEGACY_MENU_CODES)
            | Menu.objects.filter(
                Q(code__startswith="admin.") | Q(code__startswith="payroll."),
                route_path__in=LEGACY_ROUTE_PATHS,
            )
        ).values_list("id", flat=True)
    )
    if not legacy_menu_ids:
        return

    MenuPermission.objects.filter(menu_id__in=legacy_menu_ids).update(isactive=False)
    Menu.objects.filter(id__in=legacy_menu_ids).update(isactive=False)


class Migration(migrations.Migration):
    dependencies = [("rbac", "0140_add_admin_self_service_permissions")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
