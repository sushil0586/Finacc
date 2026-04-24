from financial.models import Credit, Debit


# Ledger/account head/account code values below intentionally preserve the key
# legacy financial identifiers already used in invoice/reporting code today.
# This keeps onboarding compatible while the rest of the system gradually moves
# toward Ledger-first accounting.
STANDARD_TRADING_TEMPLATE = {
    "account_types": [
        {"code": "1001", "name": "Receivable", "normal_balance": Debit},
        {"code": "1002", "name": "Current Assets", "normal_balance": Debit},
        {"code": "1003", "name": "Bank and Cash", "normal_balance": Debit},
        {"code": "1008", "name": "Payable", "normal_balance": Credit},
        # Party is the business-facing type used for accounts that may behave
        # as either customer, vendor, or both. Real debit/credit behavior must
        # come from Account Head / Ledger, not from accounttype.balanceType.
        {"code": "1009", "name": "Party", "normal_balance": Debit},
        {"code": "1010", "name": "Tax", "normal_balance": Debit},
        {"code": "1012", "name": "Equity", "normal_balance": Credit},
        {"code": "1014", "name": "Income", "normal_balance": Credit},
        {"code": "1015", "name": "Other Income", "normal_balance": Credit},
        {"code": "1016", "name": "Expenses", "normal_balance": Debit},
    ],
    "account_heads": [
        {
            "code": 200,
            "name": "Closing Stock",
            "type_code": "1002",
            "detailsingroup": 1,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 1000,
            "name": "Purchase",
            "type_code": "1016",
            "detailsingroup": 1,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 2000,
            "name": "Bank",
            "type_code": "1003",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 3000,
            "name": "Sale",
            "type_code": "1014",
            "detailsingroup": 1,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 4000,
            "name": "Cash",
            "type_code": "1003",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 6000,
            "name": "Advance Payable",
            "type_code": "1009",
            "detailsingroup": 3,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 6100,
            "name": "Advance Recoverable",
            "type_code": "1009",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 6500,
            "name": "GST Input",
            "type_code": "1010",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 6600,
            "name": "GST Output",
            "type_code": "1010",
            "detailsingroup": 3,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 6200,
            "name": "Proprietor Capital",
            "type_code": "1012",
            "detailsingroup": 3,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 6300,
            "name": "Partner Capital",
            "type_code": "1012",
            "detailsingroup": 3,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 7000,
            "name": "Sundry Creditors",
            "type_code": "1009",
            "detailsingroup": 3,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 7088,
            "name": "Indirect Income",
            "type_code": "1015",
            "detailsingroup": 2,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 8000,
            "name": "Sundry Debtors",
            "type_code": "1009",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 8300,
            "name": "Direct Expenses",
            "type_code": "1016",
            "detailsingroup": 2,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 8350,
            "name": "Indirect Expenses",
            "type_code": "1016",
            "detailsingroup": 2,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 9000,
            "name": "Opening Stock",
            "type_code": "1002",
            "detailsingroup": 1,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
    ],
    "default_accounts": [
        {"code": 200, "name": "Closing Stock", "head_code": 200, "party_type": "Other"},
        {"code": 1000, "name": "Purchase", "head_code": 1000, "credit_head_code": 3000, "party_type": "Other"},
        {"code": 2000, "name": "Bank", "head_code": 2000, "party_type": "Bank"},
        {"code": 3000, "name": "Sale", "head_code": 3000, "party_type": "Other"},
        {"code": 4000, "name": "Cash", "head_code": 4000, "party_type": "Other"},
        {"code": 6000, "name": "Advance Payable", "head_code": 6000, "credit_head_code": 6000, "party_type": "Other"},
        {"code": 6100, "name": "Advance Recoverable", "head_code": 6100, "party_type": "Other"},
        {"code": 6501, "name": "Input CGST", "head_code": 6500, "party_type": "Government"},
        {"code": 6502, "name": "Input SGST", "head_code": 6500, "party_type": "Government"},
        {"code": 6503, "name": "Input IGST", "head_code": 6500, "party_type": "Government"},
        {"code": 6504, "name": "Input CESS", "head_code": 6500, "party_type": "Government"},
        {"code": 6601, "name": "Output CGST", "head_code": 6600, "party_type": "Government"},
        {"code": 6602, "name": "Output SGST", "head_code": 6600, "party_type": "Government"},
        {"code": 6603, "name": "Output IGST", "head_code": 6600, "party_type": "Government"},
        {"code": 6604, "name": "Output CESS", "head_code": 6600, "party_type": "Government"},
        {"code": 6605, "name": "RCM Output GST", "head_code": 6600, "party_type": "Government"},
        {"code": 6505, "name": "RCM Input GST", "head_code": 6500, "party_type": "Government"},
        {"code": 7000, "name": "Sundry Creditors Control", "head_code": 7000, "party_type": "Both"},
        {"code": 8000, "name": "Sundry Debtors Control", "head_code": 8000, "credit_head_code": 7000, "party_type": "Both"},
        {"code": 8050, "name": "TCS206C1H", "head_code": 6100, "credit_head_code": 6600, "party_type": "Government"},
        {"code": 8051, "name": "TCS206C", "head_code": 6100, "credit_head_code": 6600, "party_type": "Government"},
        {"code": 8100, "name": "TDS194Q", "head_code": 6100, "credit_head_code": 6600, "party_type": "Government"},
        {"code": 8400, "name": "Discounts", "head_code": 8350, "party_type": "Other"},
        {"code": 8500, "name": "Bank Charges", "head_code": 8350, "party_type": "Other"},
        {"code": 8504, "name": "Round Off", "head_code": 8350, "party_type": "Other"},
        {"code": 9000, "name": "Opening Stock", "head_code": 9000, "party_type": "Other"},
    ],
}


STANDARD_BUSINESS_FULL_TEMPLATE = {
    "account_types": [
        *STANDARD_TRADING_TEMPLATE["account_types"],
        {"code": "1004", "name": "Fixed Assets", "normal_balance": Debit},
        {"code": "1005", "name": "Current Liabilities", "normal_balance": Credit},
        {"code": "1006", "name": "Borrowings", "normal_balance": Credit},
        {"code": "1007", "name": "Loans and Advances", "normal_balance": Debit},
    ],
    "account_heads": [
        *STANDARD_TRADING_TEMPLATE["account_heads"],
        {
            "code": 2200,
            "name": "Fixed Assets",
            "type_code": "1004",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 2210,
            "name": "Land",
            "type_code": "1004",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 2220,
            "name": "Building",
            "type_code": "1004",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 2230,
            "name": "Plant & Machinery",
            "type_code": "1004",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 2240,
            "name": "Furniture & Fixtures",
            "type_code": "1004",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 2250,
            "name": "Computers & Peripherals",
            "type_code": "1004",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 2260,
            "name": "Office Equipment",
            "type_code": "1004",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 2270,
            "name": "Vehicles",
            "type_code": "1004",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 2280,
            "name": "Intangible Assets",
            "type_code": "1004",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 2290,
            "name": "Capital Work In Progress",
            "type_code": "1004",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 5200,
            "name": "Statutory Payables",
            "type_code": "1005",
            "detailsingroup": 3,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 5300,
            "name": "Duties & Taxes",
            "type_code": "1005",
            "detailsingroup": 3,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 5400,
            "name": "Secured Loans",
            "type_code": "1006",
            "detailsingroup": 3,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 5500,
            "name": "Unsecured Loans",
            "type_code": "1006",
            "detailsingroup": 3,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 5600,
            "name": "Deposits & Advances",
            "type_code": "1007",
            "detailsingroup": 3,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 7090,
            "name": "Interest Income",
            "type_code": "1015",
            "detailsingroup": 2,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 7095,
            "name": "Commission Income",
            "type_code": "1015",
            "detailsingroup": 2,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 7098,
            "name": "Exchange Gain",
            "type_code": "1015",
            "detailsingroup": 2,
            "balance_type": Credit,
            "drcreffect": Credit,
        },
        {
            "code": 8360,
            "name": "Employee Benefit Expenses",
            "type_code": "1016",
            "detailsingroup": 2,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 8370,
            "name": "Administrative Expenses",
            "type_code": "1016",
            "detailsingroup": 2,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 8380,
            "name": "Selling & Distribution Expenses",
            "type_code": "1016",
            "detailsingroup": 2,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 8390,
            "name": "Finance Costs",
            "type_code": "1016",
            "detailsingroup": 2,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 8395,
            "name": "Depreciation & Amortization",
            "type_code": "1016",
            "detailsingroup": 2,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
        {
            "code": 8398,
            "name": "Exchange Loss",
            "type_code": "1016",
            "detailsingroup": 2,
            "balance_type": Debit,
            "drcreffect": Debit,
        },
    ],
    "default_accounts": [
        *STANDARD_TRADING_TEMPLATE["default_accounts"],
        {"code": 2201, "name": "Land", "head_code": 2210, "party_type": "Other"},
        {"code": 2202, "name": "Building", "head_code": 2220, "party_type": "Other"},
        {"code": 2203, "name": "Plant & Machinery", "head_code": 2230, "party_type": "Other"},
        {"code": 2204, "name": "Furniture & Fixtures", "head_code": 2240, "party_type": "Other"},
        {"code": 2205, "name": "Computers & Peripherals", "head_code": 2250, "party_type": "Other"},
        {"code": 2206, "name": "Office Equipment", "head_code": 2260, "party_type": "Other"},
        {"code": 2207, "name": "Vehicles", "head_code": 2270, "party_type": "Other"},
        {"code": 2208, "name": "Intangible Assets", "head_code": 2280, "party_type": "Other"},
        {"code": 2209, "name": "Capital Work In Progress", "head_code": 2290, "party_type": "Other"},
        {"code": 5201, "name": "Provident Fund Payable", "head_code": 5200, "party_type": "Other"},
        {"code": 5202, "name": "ESI Payable", "head_code": 5200, "party_type": "Other"},
        {"code": 5203, "name": "Professional Tax Payable", "head_code": 5200, "party_type": "Government"},
        {"code": 5204, "name": "Salary Payable", "head_code": 5200, "party_type": "Other"},
        {"code": 5205, "name": "Bonus Payable", "head_code": 5200, "party_type": "Other"},
        {"code": 5301, "name": "GST Payable", "head_code": 5300, "party_type": "Government"},
        {"code": 5302, "name": "TDS Payable", "head_code": 5300, "party_type": "Government"},
        {"code": 5303, "name": "TCS Payable", "head_code": 5300, "party_type": "Government"},
        {"code": 5401, "name": "Term Loan", "head_code": 5400, "party_type": "Other"},
        {"code": 5402, "name": "Vehicle Loan", "head_code": 5400, "party_type": "Other"},
        {"code": 5501, "name": "Director Loan", "head_code": 5500, "party_type": "Other"},
        {"code": 5502, "name": "Inter Corporate Loan", "head_code": 5500, "party_type": "Other"},
        {"code": 5601, "name": "Security Deposit", "head_code": 5600, "party_type": "Other"},
        {"code": 5602, "name": "Prepaid Expenses", "head_code": 5600, "party_type": "Other"},
        {"code": 5603, "name": "Staff Advance", "head_code": 5600, "party_type": "Employee"},
        {"code": 7091, "name": "Interest Received", "head_code": 7090, "party_type": "Other"},
        {"code": 7092, "name": "Commission Received", "head_code": 7095, "party_type": "Other"},
        {"code": 7093, "name": "Foreign Exchange Gain", "head_code": 7098, "party_type": "Other"},
        {"code": 8361, "name": "Salary", "head_code": 8360, "party_type": "Other"},
        {"code": 8362, "name": "Wages", "head_code": 8360, "party_type": "Other"},
        {"code": 8363, "name": "Staff Welfare", "head_code": 8360, "party_type": "Other"},
        {"code": 8364, "name": "EPF Employer Contribution", "head_code": 8360, "party_type": "Other"},
        {"code": 8365, "name": "ESI Employer Contribution", "head_code": 8360, "party_type": "Other"},
        {"code": 8371, "name": "Rent", "head_code": 8370, "party_type": "Other"},
        {"code": 8372, "name": "Electricity Charges", "head_code": 8370, "party_type": "Other"},
        {"code": 8373, "name": "Telephone & Internet", "head_code": 8370, "party_type": "Other"},
        {"code": 8374, "name": "Printing & Stationery", "head_code": 8370, "party_type": "Other"},
        {"code": 8375, "name": "Office Expenses", "head_code": 8370, "party_type": "Other"},
        {"code": 8376, "name": "Repair & Maintenance", "head_code": 8370, "party_type": "Other"},
        {"code": 8377, "name": "Insurance", "head_code": 8370, "party_type": "Other"},
        {"code": 8378, "name": "Professional Fees", "head_code": 8370, "party_type": "Other"},
        {"code": 8379, "name": "Audit Fees", "head_code": 8370, "party_type": "Other"},
        {"code": 8381, "name": "Freight Outward", "head_code": 8380, "party_type": "Other"},
        {"code": 8382, "name": "Advertisement & Marketing", "head_code": 8380, "party_type": "Other"},
        {"code": 8383, "name": "Sales Promotion", "head_code": 8380, "party_type": "Other"},
        {"code": 8384, "name": "Packing & Forwarding", "head_code": 8380, "party_type": "Other"},
        {"code": 8391, "name": "Interest Paid", "head_code": 8390, "party_type": "Other"},
        {"code": 8392, "name": "Bank Interest", "head_code": 8390, "party_type": "Other"},
        {"code": 8393, "name": "Processing Charges", "head_code": 8390, "party_type": "Other"},
        {"code": 8396, "name": "Depreciation Expense", "head_code": 8395, "party_type": "Other"},
        {"code": 8397, "name": "Amortization Expense", "head_code": 8395, "party_type": "Other"},
        {"code": 8399, "name": "Foreign Exchange Loss", "head_code": 8398, "party_type": "Other"},
    ],
}


def _override_head_types(rows, overrides):
    normalized = []
    for row in rows:
        current = dict(row)
        if current["code"] in overrides:
            current["type_code"] = overrides[current["code"]]
        normalized.append(current)
    return normalized


def _append_unique_accounts(rows, additions):
    merged = {row["code"]: dict(row) for row in rows}
    for row in additions:
        merged[row["code"]] = dict(row)
    return [merged[key] for key in sorted(merged)]


INDIAN_ACCOUNTING_FINAL_TEMPLATE = {
    "account_types": [
        {"code": "1100", "name": "Current Assets", "normal_balance": Debit},
        {"code": "1200", "name": "Bank and Cash", "normal_balance": Debit},
        {"code": "1300", "name": "Non Current Assets", "normal_balance": Debit},
        {"code": "2100", "name": "Current Liabilities", "normal_balance": Credit},
        {"code": "2200", "name": "Non Current Liabilities", "normal_balance": Credit},
        {"code": "3100", "name": "Capital and Equity", "normal_balance": Credit},
        {"code": "4100", "name": "Direct Income", "normal_balance": Credit},
        {"code": "4200", "name": "Indirect Income", "normal_balance": Credit},
        {"code": "5100", "name": "Direct Expenses", "normal_balance": Debit},
        {"code": "5200", "name": "Indirect Expenses", "normal_balance": Debit},
        {"code": "1009", "name": "Party", "normal_balance": Debit},
    ],
    "account_heads": _override_head_types(
        STANDARD_BUSINESS_FULL_TEMPLATE["account_heads"],
        {
            200: "1100",    # Closing Stock
            1000: "5100",   # Purchase
            2000: "1200",   # Bank
            3000: "4100",   # Sale
            4000: "1200",   # Cash
            6000: "2100",   # Advance Payable
            6100: "1100",   # Advance Recoverable
            6200: "3100",   # Proprietor Capital
            6300: "3100",   # Partner Capital
            6500: "1100",   # GST Input / ITC
            6600: "2100",   # GST Output / liability
            7000: "2100",   # Sundry Creditors
            7088: "4200",   # Indirect Income
            7090: "4200",
            7095: "4200",
            7098: "4200",
            8000: "1100",   # Sundry Debtors
            8300: "5100",   # Direct Expenses
            8350: "5200",   # Indirect Expenses
            8360: "5200",
            8370: "5200",
            8380: "5200",
            8390: "5200",
            8395: "5200",
            8398: "5200",
            9000: "1100",   # Opening Stock
            2200: "1300",   # Fixed Assets
            2210: "1300",
            2220: "1300",
            2230: "1300",
            2240: "1300",
            2250: "1300",
            2260: "1300",
            2270: "1300",
            2280: "1300",
            2290: "1300",
            5200: "2100",   # Statutory Payables
            5300: "2100",   # Duties & Taxes
            5400: "2200",   # Secured Loans
            5500: "2200",   # Unsecured Loans
            5600: "1100",   # Deposits & Advances
        },
    ),
    "default_accounts": _append_unique_accounts(
        STANDARD_BUSINESS_FULL_TEMPLATE["default_accounts"],
        [
            {"code": 5304, "name": "GST TDS Payable", "head_code": 5300, "party_type": "Government"},
            {"code": 5305, "name": "RCM CGST Payable", "head_code": 5300, "party_type": "Government"},
            {"code": 5306, "name": "RCM SGST Payable", "head_code": 5300, "party_type": "Government"},
            {"code": 5307, "name": "RCM IGST Payable", "head_code": 5300, "party_type": "Government"},
            {"code": 5308, "name": "RCM CESS Payable", "head_code": 5300, "party_type": "Government"},
            {"code": 7081, "name": "Round Off Income", "head_code": 7088, "party_type": "Other"},
            {"code": 7082, "name": "Discount Received", "head_code": 7088, "party_type": "Other"},
            {"code": 7083, "name": "Sales Other Charges Income", "head_code": 7088, "party_type": "Other"},
            {"code": 1001, "name": "Purchase Default", "head_code": 1000, "party_type": "Other"},
            {"code": 3001, "name": "Sales Default", "head_code": 3000, "party_type": "Other"},
            {"code": 3002, "name": "Sales Revenue", "head_code": 3000, "party_type": "Other"},
            {"code": 8351, "name": "Purchase Misc Expense", "head_code": 8350, "party_type": "Other"},
            {"code": 8352, "name": "Sales Misc Expense", "head_code": 8350, "party_type": "Other"},
            {"code": 8353, "name": "Blocked ITC Expense", "head_code": 8350, "party_type": "Other"},
            {"code": 8401, "name": "TDS Payable", "head_code": 5300, "party_type": "Government"},
            {"code": 8402, "name": "TCS Payable", "head_code": 5300, "party_type": "Government"},
            {"code": 8403, "name": "Round Off Expense", "head_code": 8350, "party_type": "Other"},
        ],
    ),
}


FINANCIAL_TEMPLATES = {
    "standard_trading": STANDARD_TRADING_TEMPLATE,
    "standard_business_full": STANDARD_BUSINESS_FULL_TEMPLATE,
    "indian_accounting_final": INDIAN_ACCOUNTING_FINAL_TEMPLATE,
}
