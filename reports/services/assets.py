from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q

from assets.models import DepreciationRunLine, FixedAsset
from posting.models import Entry, JournalLine

Q2 = Decimal("0.01")
ZERO = Decimal("0.00")


def q2(value) -> Decimal:
    return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)


def _coerce_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _paginate(rows, page, page_size):
    page = max(int(page or 1), 1)
    page_size = max(int(page_size or 100), 1)
    start = (page - 1) * page_size
    end = start + page_size
    return rows[start:end], len(rows)


def build_fixed_asset_register(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    as_of_date=None,
    category_id=None,
    status=None,
    search=None,
    page=1,
    page_size=100,
):
    as_of = _coerce_date(as_of_date)
    qs = FixedAsset.objects.select_related("category", "ledger", "subentity").filter(entity_id=entity_id)
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    if category_id:
        qs = qs.filter(category_id=category_id)
    if status:
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(Q(asset_code__icontains=search) | Q(asset_name__icontains=search))
    if as_of:
        qs = qs.filter(acquisition_date__lte=as_of).filter(Q(disposal_date__isnull=True) | Q(disposal_date__gte=as_of))

    rows = []
    totals = defaultdict(lambda: ZERO)
    for asset in qs.order_by("asset_name", "id"):
        row = {
            "asset_id": asset.id,
            "asset_code": asset.asset_code,
            "asset_name": asset.asset_name,
            "category_name": asset.category.name,
            "status": asset.status,
            "acquisition_date": asset.acquisition_date,
            "capitalization_date": asset.capitalization_date,
            "put_to_use_date": asset.put_to_use_date,
            "gross_block": f"{q2(asset.gross_block):.2f}",
            "accumulated_depreciation": f"{q2(asset.accumulated_depreciation):.2f}",
            "impairment_amount": f"{q2(asset.impairment_amount):.2f}",
            "net_book_value": f"{q2(asset.net_book_value):.2f}",
            "ledger_name": getattr(asset.ledger, "name", None),
            "location_name": asset.location_name,
            "department_name": asset.department_name,
            "custodian_name": asset.custodian_name,
            "subentity_name": getattr(asset.subentity, "subentityname", None),
            "can_drilldown": True,
            "drilldown_target": "fixed_asset",
            "drilldown_params": {"id": asset.id},
        }
        rows.append(row)
        totals["gross_block"] += q2(asset.gross_block)
        totals["accumulated_depreciation"] += q2(asset.accumulated_depreciation)
        totals["impairment_amount"] += q2(asset.impairment_amount)
        totals["net_book_value"] += q2(asset.net_book_value)

    paged_rows, total_rows = _paginate(rows, page, page_size)
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "as_of_date": as_of,
        "rows": paged_rows,
        "totals": {k: f"{q2(v):.2f}" for k, v in totals.items()},
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows},
        "summary": {"asset_count": total_rows},
    }


def build_depreciation_schedule(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    category_id=None,
    asset_id=None,
    page=1,
    page_size=100,
):
    frm = _coerce_date(from_date)
    to = _coerce_date(to_date)
    qs = DepreciationRunLine.objects.select_related("run", "asset", "asset__category").filter(run__entity_id=entity_id)
    if entityfin_id:
        qs = qs.filter(run__entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(run__subentity_id=subentity_id)
    if frm:
        qs = qs.filter(period_to__gte=frm)
    if to:
        qs = qs.filter(period_from__lte=to)
    if category_id:
        qs = qs.filter(asset__category_id=category_id)
    if asset_id:
        qs = qs.filter(asset_id=asset_id)

    rows = []
    totals = defaultdict(lambda: ZERO)
    for line in qs.order_by("period_to", "asset__asset_name", "id"):
        row = {
            "run_id": line.run_id,
            "run_code": line.run.run_code,
            "asset_id": line.asset_id,
            "asset_code": line.asset.asset_code,
            "asset_name": line.asset.asset_name,
            "category_name": line.asset.category.name,
            "period_from": line.period_from,
            "period_to": line.period_to,
            "posting_date": line.run.posting_date,
            "opening_gross_block": f"{q2(line.opening_gross_block):.2f}",
            "opening_accumulated_depreciation": f"{q2(line.opening_accumulated_depreciation):.2f}",
            "depreciation_amount": f"{q2(line.depreciation_amount):.2f}",
            "closing_accumulated_depreciation": f"{q2(line.closing_accumulated_depreciation):.2f}",
            "closing_net_book_value": f"{q2(line.closing_net_book_value):.2f}",
            "run_status": line.run.status,
            "can_drilldown": True,
            "drilldown_target": "fixed_asset",
            "drilldown_params": {"id": line.asset_id},
        }
        rows.append(row)
        totals["depreciation_amount"] += q2(line.depreciation_amount)
        totals["closing_net_book_value"] += q2(line.closing_net_book_value)

    paged_rows, total_rows = _paginate(rows, page, page_size)
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "from_date": frm,
        "to_date": to,
        "rows": paged_rows,
        "totals": {k: f"{q2(v):.2f}" for k, v in totals.items()},
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows},
        "summary": {"line_count": total_rows},
    }


def build_asset_event_report(
    *,
    entity_id,
    entityfin_id=None,
    subentity_id=None,
    from_date=None,
    to_date=None,
    event_type=None,
    asset_id=None,
    page=1,
    page_size=100,
):
    frm = _coerce_date(from_date)
    to = _coerce_date(to_date)
    qs = FixedAsset.objects.select_related("category", "subentity").filter(entity_id=entity_id)
    if entityfin_id:
        qs = qs.filter(entityfinid_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    if asset_id:
        qs = qs.filter(id=asset_id)

    rows = []
    totals = defaultdict(lambda: ZERO)
    for asset in qs.order_by("asset_name", "id"):
        events = []
        if asset.capitalization_date and asset.capitalization_posting_batch_id:
            events.append(("capitalization", asset.capitalization_date, q2(asset.gross_block), asset.capitalization_posting_batch_id))
        if q2(asset.impairment_amount) > ZERO and asset.impairment_posting_batch_id:
            batch_created = getattr(asset.impairment_posting_batch, "created_at", None)
            events.append(("impairment", (batch_created.date() if batch_created else None), q2(asset.impairment_amount), asset.impairment_posting_batch_id))
        if asset.disposal_date and asset.disposal_posting_batch_id:
            events.append(("disposal", asset.disposal_date, q2(asset.disposal_proceeds), asset.disposal_posting_batch_id))
        for evt_type, evt_date, amount, posting_batch_id in events:
            if event_type and evt_type != event_type:
                continue
            if frm and evt_date and evt_date < frm:
                continue
            if to and evt_date and evt_date > to:
                continue
            row = {
                "asset_id": asset.id,
                "asset_code": asset.asset_code,
                "asset_name": asset.asset_name,
                "category_name": asset.category.name,
                "event_type": evt_type,
                "event_date": evt_date,
                "amount": f"{q2(amount):.2f}",
                "posting_batch_id": posting_batch_id,
                "subentity_name": getattr(asset.subentity, "subentityname", None),
                "can_drilldown": True,
                "drilldown_target": "fixed_asset",
                "drilldown_params": {"id": asset.id},
            }
            rows.append(row)
            totals["amount"] += q2(amount)

    rows.sort(key=lambda x: (x["event_date"] or date.min, x["asset_name"], x["event_type"]))
    paged_rows, total_rows = _paginate(rows, page, page_size)
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "from_date": frm,
        "to_date": to,
        "event_type": event_type,
        "rows": paged_rows,
        "totals": {k: f"{q2(v):.2f}" for k, v in totals.items()},
        "pagination": {"page": page, "page_size": page_size, "total_rows": total_rows},
        "summary": {"event_count": total_rows},
    }


def build_asset_history(
    *,
    entity_id,
    asset_id,
    entityfin_id=None,
    subentity_id=None,
):
    asset = FixedAsset.objects.select_related("category", "subentity", "capitalization_posting_batch", "impairment_posting_batch", "disposal_posting_batch").get(id=asset_id, entity_id=entity_id)
    history = [
        {
            "event_type": "created",
            "event_date": asset.created_at.date() if asset.created_at else None,
            "description": f"Asset created as {asset.status}",
            "amount": f"{q2(asset.gross_block):.2f}",
        }
    ]
    if asset.capitalization_date:
        history.append(
            {
                "event_type": "capitalization",
                "event_date": asset.capitalization_date,
                "description": "Asset capitalized",
                "amount": f"{q2(asset.gross_block):.2f}",
                "posting_batch_id": asset.capitalization_posting_batch_id,
            }
        )
    if q2(asset.impairment_amount) > ZERO:
        dt = asset.impairment_posting_batch.created_at.date() if asset.impairment_posting_batch and asset.impairment_posting_batch.created_at else None
        history.append(
            {
                "event_type": "impairment",
                "event_date": dt,
                "description": "Impairment recognized",
                "amount": f"{q2(asset.impairment_amount):.2f}",
                "posting_batch_id": asset.impairment_posting_batch_id,
            }
        )
    for line in DepreciationRunLine.objects.select_related("run").filter(asset_id=asset.id).order_by("period_to", "id"):
        history.append(
            {
                "event_type": "depreciation",
                "event_date": line.run.posting_date,
                "description": f"Depreciation run {line.run.run_code}",
                "amount": f"{q2(line.depreciation_amount):.2f}",
                "posting_batch_id": line.run.posting_batch_id,
                "meta": line.calculation_meta,
            }
        )
    if asset.disposal_date:
        history.append(
            {
                "event_type": "disposal",
                "event_date": asset.disposal_date,
                "description": "Asset disposed",
                "amount": f"{q2(asset.disposal_proceeds):.2f}",
                "gain_loss": f"{q2(asset.disposal_gain_loss):.2f}",
                "posting_batch_id": asset.disposal_posting_batch_id,
            }
        )

    posting_batch_ids = [x for x in {asset.capitalization_posting_batch_id, asset.impairment_posting_batch_id, asset.disposal_posting_batch_id} if x]
    run_batch_ids = list(DepreciationRunLine.objects.filter(asset_id=asset.id, run__posting_batch_id__isnull=False).values_list("run__posting_batch_id", flat=True))
    batch_ids = posting_batch_ids + run_batch_ids
    journal_lines = []
    if batch_ids:
        for jl in JournalLine.objects.select_related("ledger", "entry").filter(posting_batch_id__in=batch_ids).order_by("posting_date", "id"):
            journal_lines.append(
                {
                    "posting_date": jl.posting_date,
                    "entry_id": jl.entry_id,
                    "txn_type": jl.txn_type,
                    "voucher_no": jl.voucher_no,
                    "ledger_name": getattr(jl.ledger, "name", None),
                    "drcr": "Dr" if jl.drcr else "Cr",
                    "amount": f"{q2(jl.amount):.2f}",
                }
            )

    history.sort(key=lambda x: (x.get("event_date") or date.min, x.get("event_type") or ""))
    return {
        "entity_id": entity_id,
        "entityfin_id": entityfin_id,
        "subentity_id": subentity_id,
        "asset": {
            "asset_id": asset.id,
            "asset_code": asset.asset_code,
            "asset_name": asset.asset_name,
            "category_name": asset.category.name,
            "status": asset.status,
            "gross_block": f"{q2(asset.gross_block):.2f}",
            "accumulated_depreciation": f"{q2(asset.accumulated_depreciation):.2f}",
            "impairment_amount": f"{q2(asset.impairment_amount):.2f}",
            "net_book_value": f"{q2(asset.net_book_value):.2f}",
        },
        "history": history,
        "journal_lines": journal_lines,
    }
