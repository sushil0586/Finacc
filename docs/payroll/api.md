# Payroll API

## Scope

This document covers the payroll run API currently exposed by `payroll/urls.py`.

The examples assume payroll URLs are mounted under `/api/payroll/`.

## Endpoints

### Run list and create

- `GET /api/payroll/runs/`
- `POST /api/payroll/runs/`

Supported list filters:

- `entity`
- `entityfinid`
- `subentity`
- `payroll_period`
- `status`
- `run_type`

### Run detail

- `GET /api/payroll/runs/<pk>/`

### Workflow actions

- `POST /api/payroll/runs/<pk>/calculate/`
- `POST /api/payroll/runs/<pk>/submit/`
- `POST /api/payroll/runs/<pk>/approve/`
- `POST /api/payroll/runs/<pk>/post/`
- `POST /api/payroll/runs/<pk>/reverse/`
- `POST /api/payroll/runs/<pk>/payment-handoff/`
- `POST /api/payroll/runs/<pk>/payment-reconcile/`

### Read endpoints

- `GET /api/payroll/runs/<pk>/summary/`
- `GET /api/payroll/runs/<pk>/payslips/<employee_run_id>/`

## Request Contracts

### Create run

Fields:

- `entity`
- `entityfinid`
- `subentity`
- `payroll_period`
- `run_type`
- `posting_date`
- `payout_date`

### Action payload

Common action serializer fields:

- `force`
- `note`
- `reason_code`
- `payment_batch_ref`
- `payment_status`

Not all fields are used by every action.

## Response Shape

Workflow endpoints return:

```json
{
  "message": "Payroll run approved.",
  "data": {
    "id": 1,
    "status": "APPROVED",
    "payment_status": "NOT_READY"
  }
}
```

Validation failures return DRF validation errors. In service-layer failures, the API translates `ValueError` into a 400 response.

Typical pattern:

```json
{
  "detail": "Only approved payroll runs can be posted."
}
```

or

```json
{
  "payment_status": "This field is required."
}
```

## Status Transition Expectations

- `calculate`: `DRAFT -> CALCULATED`
- `submit`: status remains `CALCULATED`; submission metadata is recorded
- `approve`: `CALCULATED -> APPROVED`
- `post`: `APPROVED -> POSTED`
- `reverse`: original run `POSTED -> REVERSED`; new reversal run is created and posted
- `payment-handoff`: payment status `NOT_READY -> HANDED_OFF`
- `payment-reconcile`: payment status changes independently of payroll workflow status

## Safe Usage Guidance

- do not call `post` before `approve`
- do not rely on `submit` as a distinct status
- do not infer payment completion from `POSTED`
- do not use payroll API responses as accounting truth for GL reporting; use posting-backed reports
