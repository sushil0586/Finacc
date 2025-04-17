from datetime import datetime
from dateutil.relativedelta import relativedelta

def calculate_emi(principal, annual_rate, tenure_months, start_date, interest_type):
    monthly_rate = annual_rate / 12 / 100
    schedule = []
    emi_date = start_date

    if interest_type == 'flat':
        total_interest = (principal * annual_rate * tenure_months) / (12 * 100)
        total_payment = principal + total_interest
        emi = total_payment / tenure_months
        monthly_principal = principal / tenure_months
        monthly_interest = total_interest / tenure_months
        balance = principal

        for month in range(1, tenure_months + 1):
            balance -= monthly_principal
            schedule.append({
                'month': month,
                'emi_date': emi_date.strftime('%Y-%m-%d'),
                'emi': round(emi, 2),
                'interest': round(monthly_interest, 2),
                'principal': round(monthly_principal, 2),
                'balance': round(max(balance, 0), 2)
            })
            emi_date += relativedelta(months=1)

    elif interest_type == 'reducing':
        if monthly_rate == 0:
            emi = principal / tenure_months
        else:
            emi = (principal * monthly_rate * (1 + monthly_rate) ** tenure_months) / \
                  ((1 + monthly_rate) ** tenure_months - 1)

        balance = principal

        for month in range(1, tenure_months + 1):
            interest = balance * monthly_rate
            principal_component = emi - interest
            balance -= principal_component

            schedule.append({
                'month': month,
                'emi_date': emi_date.strftime('%Y-%m-%d'),
                'emi': round(emi, 2),
                'interest': round(interest, 2),
                'principal': round(principal_component, 2),
                'balance': round(max(balance, 0), 2)
            })
            emi_date += relativedelta(months=1)

    else:
        raise ValueError("Invalid interest type")

    return round(emi, 2), schedule