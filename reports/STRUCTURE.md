# Reports Structure

This scaffold is additive. Existing report files remain active.

Use this layout for new report work:

- `reports/api/financial/`
  Financial report endpoints like trial balance, ledger book, balance sheet, P&L.
- `reports/api/statutory/`
  GST, TDS, TCS and other compliance reports.
- `reports/serializers/financial/`
  Financial report serializers.
- `reports/serializers/statutory/`
  Statutory report serializers.
- `reports/services/financial/`
  Business/reporting logic for financial reports.
- `reports/services/statutory/`
  Business/reporting logic for compliance/statutory reports.
- `reports/selectors/`
  Shared queryset builders that should read from ledger/posting-first sources.
- `reports/mixins/`
  Shared scope parsing, export helpers, and response mixins.
- `reports/schemas/`
  Response and request schema helpers for new report APIs.

Recommended rule for new financial reports:

- Use `posting.JournalLine.ledger` as the accounting source.
- Use `financial.Ledger` and `financial.accountHead` for master joins.

Recommended migration approach:

1. Keep old report modules unchanged.
2. Add all new work under the new folders.
3. Move one report family at a time when the replacement is stable.
