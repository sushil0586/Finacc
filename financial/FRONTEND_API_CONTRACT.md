# Financial API Contract (Canonical)

Use these endpoints for frontend integrations. Legacy aliases still work temporarily, but are deprecated.

## Canonical Endpoints

### 1) Base Account List
- **GET** `/api/financial/base-account-list-v2/?entity=<entity_id>[&accounthead=12,13]`
- **Response**
```json
[
  {
    "accountid": 485,
    "accountname": "ABC Traders",
    "balance": "1250.00"
  }
]
```

### 2) Simple Accounts (Dropdown)
- **GET** `/api/financial/accounts/simple-v2?entity=<entity_id>[&accounthead=12,13]`
- **Response**
```json
[
  {
    "id": 485,
    "accounthead": 12,
    "accountname": "ABC Traders",
    "accountcode": 5001,
    "state": 1,
    "statecode": "27",
    "district": 11,
    "city": 21,
    "pincode": "400001",
    "gstno": "27ABCDE1234F1Z5",
    "pan": "ABCDE1234F",
    "saccode": null
  }
]
```

### 3) Account List Post (Balance Grid)
- **POST** `/api/financial/account-list-post-v2`
- **Body**
```json
{
  "entity": 32,
  "ledger_ids": [162, 163],
  "account_ids": [485],
  "accounthead_ids": [12],
  "sort_by": "account",
  "sort_order": "asc",
  "top_n": 100
}
```
- **Response**
```json
[
  {
    "accountname": "ABC Traders",
    "debit": "1500.00",
    "credit": "250.00",
    "accgst": "27ABCDE1234F1Z5",
    "accpan": "ABCDE1234F",
    "cityname": "Mumbai",
    "accountid": 485,
    "daccountheadname": "Sundry Debtors",
    "caccountheadname": null,
    "accanbedeleted": true,
    "balance": "1250.00",
    "drcr": "DR"
  }
]
```

## Deprecated Aliases (still supported for transition)
- `/api/financial/baseaccountlistv2/`
- `/api/financial/accounts/simplev2`
- `/api/financial/accountListPostV2`

When deprecated aliases are called, response headers include:
- `X-API-Deprecated: true`
- `X-API-Replacement: <canonical-path>`

## Notes
- New backend flow is normalized-profile-first.
- Frontend should not send legacy account profile fields at top level (`gstno`, `partytype`, address legacy columns) in account write APIs.
- Use canonical URLs immediately for all new work.
