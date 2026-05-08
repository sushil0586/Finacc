# Report Roadmap

## Purpose

This document lists the current report sections, the known gaps in each section, and the recommended next reports to build.

The goal is to help product, finance, implementation, and engineering teams decide:
- which reports are already sufficient
- which reports are missing
- which missing reports are highest value
- which ones should be planned first

## Planning Principles

When deciding whether a new report should be built, use these rules:

1. Prefer reports that directly support period close, compliance, collections, inventory control, or manufacturing cost visibility.
2. Prefer reports that reduce Excel dependency for daily operations.
3. Prefer reports that can be reused across multiple customers or industries.
4. De-prioritize reports that are only alternate views of data already visible elsewhere unless there is strong business demand.

## Section Summary

### Financial Hub

Current coverage is strong. This section already contains the core statutory and management accounting reports most customers expect.

Existing strengths:
- Trial Balance
- Ledger Book
- Profit & Loss
- Balance Sheet
- Trading Account
- Daybook
- Cashbook
- Bank Reconciliation

Recommended additions:
- Cash Flow Statement
- Financial Variance Report
  Compare current period vs prior period and budget where available.
- Financial Ratios Dashboard
  Quick view of gross margin, current ratio, debtor days, creditor days, and working capital.
- General Ledger Summary
  Useful if current ledger summary access is still fragmented or indirect.

Priority:
- Medium

Business value:
- Strong for CFO and finance controller users

Implementation difficulty:
- Medium

## Receivables

This section is in good shape, but there is room to improve collection planning and customer communication.

Existing strengths:
- Customer Outstanding
- Receivable Aging
- Receivable Aging Detail
- Customer Ledger Statement
- Overdue Customers
- Credit Exposure
- Receivables Exceptions
- Open Items
- Collections History
- Sales Register

Recommended additions:
- Customer Statement of Account
  A cleaner customer-facing statement format than a raw ledger view.
- Collection Forecast
  Expected incoming collections by date bucket.
- Receivables by Salesperson or Territory
  Useful where collections accountability sits with sales teams.
- Dunning / Follow-up Queue
  Prioritized call list for collection teams.

Priority:
- Medium

Business value:
- High for collection-heavy businesses

Implementation difficulty:
- Low to Medium

## Payables

This section already covers the core operational and close reports, but supplier payment planning can still improve.

Existing strengths:
- Vendor Outstanding
- AP Aging
- Vendor Ledger Statement
- Purchase Register
- Vendor Settlement History
- Vendor Debit/Credit Note Register
- AP to GL Reconciliation
- Vendor Balance Exceptions
- Payables Close Pack

Recommended additions:
- Upcoming Payments Calendar
  Vendors and invoices due in the coming 7, 15, and 30 days.
- Vendor Statement
  Useful for vendor reconciliation discussions.
- Payables by Department or Cost Center
  Helps internal spending review.
- Purchase vs Payment Reconciliation
  Easy business-level payable settlement tracking.

Priority:
- Medium

Business value:
- High for treasury and AP teams

Implementation difficulty:
- Low to Medium

## Compliance

This is one of the strongest areas for future report growth because compliance teams need both filing data and exception-driven dashboards.

Existing strengths:
- GSTR-1
- GSTR-3B
- GSTR-9
- TDS Report
- TCS Ledger
- TCS Filing Pack

Recommended additions:
- GSTR-1 vs GSTR-3B Reconciliation
  Highest-value GST control report.
- GST Exception Dashboard
  Summary of mismatches, incomplete masters, reverse charge, missing tax classification, and filing blockers.
- ITC Mismatch Trend
  Period-over-period view of input mismatches.
- TDS/TCS Compliance Status Summary
  Monthly compliance tracker for pending, filed, and exception items.
- Filing Calendar / Due Date Dashboard
  Upcoming statutory deadlines with readiness indicators.

Priority:
- High

Business value:
- Very high

Implementation difficulty:
- Medium

## Inventory

Inventory reporting is already functionally useful, but the next wave should focus on business analysis instead of only stock movement visibility.

Existing strengths:
- Stock Summary
- Location Stock
- Stock Ledger
- Stock Aging
- Non-Moving Stock
- Reorder Status
- Stock Movement
- Stock Day Book
- Stock Book Summary
- Stock Book Detail

Recommended additions:
- Slow Moving vs Dead Stock Summary
  One of the most useful business-facing inventory reports.
- Inventory Valuation Trend
  Period-based stock value movement.
- Negative Stock Exception Report
  Operational control report.
- Gross Margin by Item / Category
  Valuable where sales and inventory reporting are tightly linked.
- Warehouse Aging Summary
  Useful for multi-location operations.

Priority:
- High

Business value:
- Very high

Implementation difficulty:
- Medium

## Asset Reports

This section is useful, but still smaller than other major reporting sections. It has the clearest opportunity for expansion after manufacturing and compliance.

Existing strengths:
- Fixed Asset Register
- Depreciation Schedule
- Asset Events
- Asset History

Recommended additions:
- Asset Location / Custodian Report
  High operational value and easy for audit follow-up.
- Warranty / Insurance Expiry Report
  Helps admin and compliance teams.
- Disposed Assets Summary
  Good for close and audit.
- Maintenance History Report
  Useful if maintenance data exists or is introduced later.
- Asset Utilization or Profitability Report
  Longer-term value, especially for operations-heavy customers.

Priority:
- High

Business value:
- Medium to High

Implementation difficulty:
- Low to Medium for location/custodian and expiry reports
- Higher for utilization or profitability

## Controls

This section is more of a close-and-control workspace today than a pure reporting area. The next logical additions are audit-style and readiness-style outputs.

Existing strengths:
- Control Center
- Posting Setup
- Year-End Close

Recommended additions:
- Period Close Checklist Report
- Unposted / Partially Posted Transaction Report
- Master Setup Completeness Report
- Audit Exception Summary
- Control Breach Dashboard

Priority:
- Medium

Business value:
- High for internal controls and audit readiness

Implementation difficulty:
- Medium

## Manufacturing

This section has some useful reporting already, but it is still the area with the biggest reporting expansion opportunity.

Existing strengths:
- Manufacturing Summary
- Material Consumption Report
- Output and Yield Report
- Posting Audit Report
- WIP and Cost Summary

Recommended additions:
- Planned vs Actual Consumption
  Highest-value next manufacturing report.
- Planned vs Actual Production
- BOM Variance Report
- Scrap / Rejection Analysis
- Work Order Delay / Cycle Time Report
- Machine or Operation Utilization
- WIP Aging

Priority:
- High

Business value:
- Very high for manufacturing customers

Implementation difficulty:
- Medium to High

## Recommended Priority Roadmap

### Phase 1: Highest Business Value

Build these first:
- GSTR-1 vs GSTR-3B Reconciliation
- Slow Moving vs Dead Stock Summary
- Asset Location / Custodian Report
- Planned vs Actual Consumption
- Scrap / Rejection Analysis
- Upcoming Payments Calendar

### Phase 2: Strong Operational Value

Build these next:
- GST Exception Dashboard
- Inventory Valuation Trend
- Collection Forecast
- Vendor Statement
- Period Close Checklist Report
- Warranty / Insurance Expiry Report

### Phase 3: Management and Analysis Layer

Build these later:
- Cash Flow Statement
- Financial Ratios Dashboard
- Gross Margin by Item / Category
- Asset Utilization Report
- Machine / Operation Utilization
- Receivables by Salesperson / Territory

## Quick Recommendation by Module

If only one new report is picked from each section, the best choices are:

- Financial Hub: Cash Flow Statement
- Receivables: Collection Forecast
- Payables: Upcoming Payments Calendar
- Compliance: GSTR-1 vs GSTR-3B Reconciliation
- Inventory: Slow Moving vs Dead Stock Summary
- Asset Reports: Asset Location / Custodian Report
- Controls: Period Close Checklist Report
- Manufacturing: Planned vs Actual Consumption

## Final Recommendation

If the product roadmap needs only a short and practical next-step list, prioritize these six reports:

1. GSTR-1 vs GSTR-3B Reconciliation
2. Slow Moving vs Dead Stock Summary
3. Asset Location / Custodian Report
4. Planned vs Actual Consumption
5. Scrap / Rejection Analysis
6. Upcoming Payments Calendar

These give the best mix of compliance value, operational control, audit readiness, and customer-visible usefulness.
