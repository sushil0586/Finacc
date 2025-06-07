from payroll.models import EntityPayrollComponentConfig, PayrollComponent

def calculate_salary_components(basic_salary, entity_id):
    salary_components = []

    # Fetch the component marked as is_basic=True (if any)
    basic_component = PayrollComponent.objects.filter(
        entity_id=entity_id,
        is_basic=True
      
    ).first()

    # Include Basic Salary explicitly
    salary_components.append({
        "component_id": basic_component.id if basic_component else None,
        "component_name": "Basic Salary",
        "code": "basic_salary",
        "type": "Earning",
        "amount": round(basic_salary, 2)
    })

    total_salary = basic_salary

    configs = EntityPayrollComponentConfig.objects.select_related(
        'component__calculation_type',
        'component__component_type'
    ).filter(
        entity_id=entity_id
     
        
    )

    for config in configs:
        component = config.component

        # Skip if it's the basic component (already included above)
        if basic_component and component.id == basic_component.id:
            continue

        calc_type = component.calculation_type.name.lower() if component.calculation_type else "fixed"
        amount = 0

        if calc_type == 'fixed':
            amount = config.selected_amount
        elif calc_type == 'percentage':
            amount = (basic_salary * config.selected_amount) / 100
        elif calc_type == 'formula' and component.formula_expression:
            try:
                context = {"basic_salary": basic_salary}
                for sc in salary_components:
                    context[sc['code']] = sc['amount']
                amount = eval(component.formula_expression, {}, context)
            except Exception:
                amount = 0

        salary_components.append({
            "component_id": component.id,
            "component_name": component.name,
            "code": component.code,
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