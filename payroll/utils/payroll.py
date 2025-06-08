from payroll.models import EntityPayrollComponentConfig, PayrollComponent

def calculate_salary_components(basic_salary, entity_id):
    salary_components = []

    print(f"--- Calculating Salary Components for entity_id={entity_id}, basic_salary={basic_salary} ---")

    # Fetch Basic Component
    basic_component = PayrollComponent.objects.filter(
        entity_id=entity_id,
        is_basic=True
    ).first()

    if not basic_component:
        print("⚠️ No basic component found for this entity.")

    salary_components.append({
        "component_id": basic_component.id if basic_component else None,
        "component_name": "Basic Salary",
        "code": "basic_salary",
        "type": "Earning",
        "amount": round(basic_salary, 2)
    })

    total_salary = basic_salary

    # Fetch Component Configs
    configs = EntityPayrollComponentConfig.objects.select_related(
        'component__calculation_type',
        'component__component_type'
    ).filter(entity_id=entity_id)

    print(f"✅ Found {configs.count()} component configs for entity {entity_id}.")

    if configs.count() == 0:
        print("⚠️ No configs found. Nothing to calculate.")
        return {
            "basic_salary": round(basic_salary, 2),
            "total_salary": round(total_salary, 2),
            "components": salary_components
        }

    for config in configs:
        component = config.component

        if not component:
            print("⚠️ Skipping config with no component.")
            continue

        if basic_component and component.id == basic_component.id:
            print(f"ℹ️ Skipping basic component '{component.name}' (already added).")
            continue

        print(f"🔧 Processing Component: {component.name} ({component.code})")

        calc_type = component.calculation_type.name.lower() if component.calculation_type else "fixed"
        amount = 0

        if calc_type == 'fixed':
            amount = config.selected_amount or 0
            print(f"    ➤ Fixed Amount: {amount}")
        elif calc_type == 'percentage':
            amount = (basic_salary * (config.selected_amount or 0)) / 100
            print(f"    ➤ Percentage Amount: {amount}")
        elif calc_type == 'formula' and component.formula_expression:
            try:
                context = {"basic_salary": basic_salary}
                for sc in salary_components:
                    context[sc['code']] = sc['amount']
                amount = eval(component.formula_expression, {}, context)
                print(f"    ➤ Formula Amount: {amount}")
            except Exception as e:
                print(f"❌ Error evaluating formula for {component.name}: {e}")
                amount = 0
        else:
            print(f"⚠️ Unknown calculation type: {calc_type}")

        salary_components.append({
            "component_id": component.id,
            "component_name": component.name,
            "code": component.code,
            "min_value": config.min_value,
            "max_value": config.max_value,
            "type": component.component_type.name if component.component_type else "",
            "amount": round(amount, 2)
        })

        if component.component_type and component.component_type.code == 'earning':
            total_salary += amount

    return {
        "basic_salary": round(basic_salary, 2),
        "total_salary": round(total_salary, 2),
        "components": salary_components
    }
