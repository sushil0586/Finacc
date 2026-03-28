# Invoice Custom Fields - Phase 2 Frontend Contract

This contract covers dynamic "extra attributes" for Sales Invoice and Purchase Invoice.

Examples: `broker`, `bilty_no`, `transport_notes`, `lr_no`, custom customer-specific fields.

## 1) Definition APIs (admin/config screens)

### List effective definitions

`GET /api/financial/invoice-custom-fields/definitions/?entity=<id>&module=<sales_invoice|purchase_invoice>&subentity=<id|optional>&party=<account_id|optional>`

Response:

```json
{
  "definitions": [
    {
      "id": 11,
      "entity": 32,
      "subentity": null,
      "module": "sales_invoice",
      "key": "broker_name",
      "label": "Broker Name",
      "field_type": "text",
      "is_required": false,
      "order_no": 10,
      "help_text": "For internal logistics",
      "options_json": [],
      "applies_to_account": null,
      "isactive": true
    }
  ]
}
```

### Create definition

`POST /api/financial/invoice-custom-fields/definitions/`

### Update definition

`PATCH /api/financial/invoice-custom-fields/definitions/<pk>/`

---

## 2) Customer/Vendor default APIs

### Get defaults map

`GET /api/financial/invoice-custom-fields/defaults/?entity=<id>&module=<sales_invoice|purchase_invoice>&party=<account_id>&subentity=<id|optional>`

Response:

```json
{
  "defaults": {
    "broker_name": "ABC Brokers",
    "transport_notes": "Handle with care"
  }
}
```

### Save/update default row

`POST /api/financial/invoice-custom-fields/defaults/`

Body:

```json
{
  "definition": 11,
  "party_account": 171,
  "default_value": "ABC Brokers",
  "isactive": true
}
```

---

## 3) Invoice create/update payload

Both Sales and Purchase invoice payloads now support:

```json
{
  "custom_fields": {
    "broker_name": "ABC Brokers",
    "bilty_no": "BL-2026-9001",
    "transport_notes": "Fragile"
  }
}
```

Backend stores into `custom_fields_json` and validates against active definitions:

- Unknown key -> validation error
- Required key missing -> validation error
- Type mismatch -> validation error
- Select/multiselect invalid option -> validation error

---

## 4) Meta endpoints now include custom fields

### Sales

- `GET /api/sales/meta/invoice-form/`
  - includes `custom_field_definitions`
- `GET /api/sales/meta/invoice-detail-form/?...&invoice=<id>`
  - includes `custom_field_definitions`
  - includes `custom_field_defaults` (for selected customer)

### Purchase

- `GET /api/purchase/meta/invoice-form/`
  - includes `custom_field_definitions`
- `GET /api/purchase/meta/invoice-detail-form/?...&invoice=<id>`
  - includes `custom_field_definitions`
  - includes `custom_field_defaults` (for selected vendor)

---

## 5) Frontend implementation guidance

1. Load form meta and render `custom_field_definitions` section (after party selection fields).
2. On customer/vendor change, call defaults API and prefill fields if blank.
3. Persist into `custom_fields` object in invoice payload.
4. On edit, bind from `invoice.custom_fields`.
5. Render in print/PDF as "Additional Attributes" block.

---

## 6) Field types currently supported

- `text`
- `number`
- `date` (YYYY-MM-DD)
- `boolean`
- `select` (single value from options)
- `multiselect` (array of values from options)

---

## 7) Phase-2 backend hardening (implemented)

- Definition `key` is normalized to snake_case and validated.
- For `select`/`multiselect`, `options_json` is mandatory and non-empty.
- Duplicate active definitions in same scope (`entity+subentity+module+applies_to_account+key`) are blocked.
- Default values are validated against the definition field type/options.
- Default API (`POST /defaults/`) now performs upsert (`definition+party_account`) instead of duplicate create.
- Django admin screens are available for:
  - `InvoiceCustomFieldDefinition`
  - `InvoiceCustomFieldDefault`
