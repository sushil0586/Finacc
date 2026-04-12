from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal, ROUND_HALF_UP
from math import ceil

from django.db.models import Prefetch, Q
from django.utils import timezone

from catalog.models import Product, ProductGstRate, ProductPlanning
from posting.models import InventoryMove


ZERO = Decimal('0')
Q2 = Decimal('0.01')
Q4 = Decimal('0.0001')


def _q2(value) -> Decimal:
    quantized = Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)
    return quantized if quantized != Decimal('-0.00') else Decimal('0.00')


def _q4(value) -> Decimal:
    quantized = Decimal(value or 0).quantize(Q4, rounding=ROUND_HALF_UP)
    return quantized if quantized != Decimal('-0.0000') else Decimal('0.0000')


def _signed_move_qty(move: dict) -> Decimal:
    qty = Decimal(str(move.get('base_qty') if move.get('base_qty') is not None else move.get('qty') or 0))
    move_type = str(move.get('move_type') or '').upper()
    if move_type == 'OUT':
        return -abs(qty)
    if move_type == 'IN':
        return abs(qty)
    return qty


def _rate_from_move(qty: Decimal, unit_cost, ext_cost) -> Decimal:
    if unit_cost is not None:
        return Decimal(str(unit_cost))
    if ext_cost is not None and qty:
        return Decimal(str(ext_cost)) / abs(Decimal(str(qty)))
    return ZERO


def _resolve_end_date(*, from_date=None, to_date=None, as_of_date=None):
    if as_of_date:
        return as_of_date
    if to_date:
        return to_date
    if from_date:
        return from_date
    return timezone.localdate()


def _product_hsn(product: Product) -> dict:
    gst_rows = list(getattr(product, 'prefetched_gst_rates', []) or [])
    if not gst_rows:
        gst_rows = list(
            ProductGstRate.objects.select_related('hsn')
            .filter(product_id=product.id)
            .order_by('-isdefault', '-valid_from', '-id')
        )
    current = gst_rows[0] if gst_rows else None
    if current is None:
        return {'hsn_id': None, 'hsn_code': None, 'hsn_description': None}
    return {
        'hsn_id': current.hsn_id,
        'hsn_code': getattr(current.hsn, 'code', None),
        'hsn_description': getattr(current.hsn, 'description', None),
    }


def _planning_for_product(product: Product) -> dict:
    planning_rows = list(getattr(product, 'planning_rows', []) or [])
    if not planning_rows:
        return {
            'min_stock': None,
            'max_stock': None,
            'reorder_level': None,
            'reorder_qty': None,
            'lead_time_days': None,
            'abc_class': '',
            'fsn_class': '',
        }
    planning = planning_rows[0]
    return {
        'min_stock': str(planning.min_stock) if planning.min_stock is not None else None,
        'max_stock': str(planning.max_stock) if planning.max_stock is not None else None,
        'reorder_level': str(planning.reorder_level) if planning.reorder_level is not None else None,
        'reorder_qty': str(planning.reorder_qty) if planning.reorder_qty is not None else None,
        'lead_time_days': planning.lead_time_days,
        'abc_class': planning.abc_class or '',
        'fsn_class': planning.fsn_class or '',
    }


def _status_for_row(*, qty: Decimal, planning: dict) -> str:
    reorder_level = planning.get('reorder_level')
    min_stock = planning.get('min_stock')
    if qty < 0:
        return 'negative'
    if qty == 0:
        return 'out_of_stock'
    if reorder_level is not None and qty <= Decimal(str(reorder_level)):
        return 'low'
    if min_stock is not None and qty <= Decimal(str(min_stock)):
        return 'low'
    return 'ok'


def _build_product_map(entity_id: int, product_ids: list[int]):
    qs = (
        Product.objects.filter(entity_id=entity_id, is_service=False, id__in=product_ids)
        .select_related('productcategory', 'base_uom')
        .prefetch_related(
            Prefetch(
                'planning',
                queryset=ProductPlanning.objects.all().order_by('id'),
                to_attr='planning_rows',
            ),
            Prefetch(
                'gst_rates',
                queryset=ProductGstRate.objects.select_related('hsn').order_by('-isdefault', '-valid_from', '-id'),
                to_attr='prefetched_gst_rates',
            ),
        )
    )
    return {product.id: product for product in qs}


def _apply_filters(qs, *, entity_id, entityfin_id=None, subentity_id=None, end_date=None, product_ids=None,
                   category_ids=None, hsn_ids=None, location_ids=None, search=None):
    qs = qs.filter(entity_id=entity_id, posting_date__lte=end_date, product__is_service=False)
    if entityfin_id:
        qs = qs.filter(entityfin_id=entityfin_id)
    if subentity_id is not None:
        qs = qs.filter(subentity_id=subentity_id)
    if product_ids:
        qs = qs.filter(product_id__in=product_ids)
    if category_ids:
        qs = qs.filter(product__productcategory_id__in=category_ids)
    if location_ids:
        qs = qs.filter(location_id__in=location_ids)
    if hsn_ids:
        hsn_product_ids = ProductGstRate.objects.filter(
            product__entity_id=entity_id,
            hsn_id__in=hsn_ids,
        ).values_list('product_id', flat=True).distinct()
        qs = qs.filter(product_id__in=hsn_product_ids)
    if search:
        token = str(search).strip()
        if token:
            qs = qs.filter(
                Q(product__productname__icontains=token)
                | Q(product__sku__icontains=token)
                | Q(product__productdesc__icontains=token)
                | Q(product__productcategory__pcategoryname__icontains=token)
                | Q(location__name__icontains=token)
            )
    return qs


def _aggregate_product_rows(moves_qs, *, entity_id, valuation_method, include_zero, include_negative):
    move_rows = list(
        moves_qs.values(
            'product_id',
            'posting_date',
            'id',
            'qty',
            'base_qty',
            'move_type',
            'unit_cost',
            'ext_cost',
        ).order_by('product_id', 'posting_date', 'id')
    )
    product_ids = sorted({row['product_id'] for row in move_rows})
    product_map = _build_product_map(entity_id, product_ids) if product_ids else {}

    rows = []
    totals_qty = ZERO
    totals_value = ZERO

    cur_pid = None
    layers: list[dict[str, Decimal]] = []
    q = ZERO
    v = ZERO
    latest = ZERO
    sum_in_qty = ZERO
    sum_in_val = ZERO
    issues_qty = ZERO
    movement_count = 0
    last_movement_date = None

    def reset_state():
        nonlocal layers, q, v, latest, sum_in_qty, sum_in_val, issues_qty, movement_count, last_movement_date
        layers = []
        q = ZERO
        v = ZERO
        latest = ZERO
        sum_in_qty = ZERO
        sum_in_val = ZERO
        issues_qty = ZERO
        movement_count = 0
        last_movement_date = None

    def flush_product(pid):
        nonlocal layers, q, v, latest, sum_in_qty, sum_in_val, issues_qty
        nonlocal totals_qty, totals_value, movement_count, last_movement_date
        if pid is None:
            return

        if valuation_method in ('fifo', 'lifo'):
            qty = sum((layer['qty'] for layer in layers), ZERO)
            val = sum((layer['qty'] * layer['rate'] for layer in layers), ZERO)
        elif valuation_method in ('mwa', 'latest'):
            qty, val = q, v
        elif valuation_method == 'wac':
            avg = (sum_in_val / sum_in_qty) if sum_in_qty > 0 else ZERO
            qty = max(sum_in_qty - issues_qty, ZERO)
            val = qty * avg
        else:
            qty, val = ZERO, ZERO

        qty = _q4(qty)
        val = _q2(val)
        if not include_negative and qty < 0:
            reset_state()
            return
        if include_zero or qty != 0:
            product = product_map.get(pid)
            if product is None:
                reset_state()
                return
            planning = _planning_for_product(product)
            hsn = _product_hsn(product)
            rate = _q4((val / qty) if qty else ZERO)
            stock_status = _status_for_row(qty=qty, planning=planning)
            stock_gap = ZERO
            if planning.get('reorder_level') is not None:
                stock_gap = qty - Decimal(str(planning['reorder_level']))

            rows.append(
                {
                    'product_id': pid,
                    'sku': getattr(product, 'sku', None),
                    'product_name': getattr(product, 'productname', None),
                    'product_description': getattr(product, 'productdesc', None),
                    'category_id': getattr(product, 'productcategory_id', None),
                    'category_name': getattr(getattr(product, 'productcategory', None), 'pcategoryname', None),
                    'uom_id': getattr(product, 'base_uom_id', None),
                    'uom_name': getattr(getattr(product, 'base_uom', None), 'code', None),
                    **hsn,
                    **planning,
                    'closing_qty': str(qty),
                    'closing_value': str(val),
                    'rate': str(rate),
                    'movement_count': movement_count,
                    'last_movement_date': last_movement_date.isoformat() if last_movement_date else None,
                    'stock_status': stock_status,
                    'stock_gap': str(_q4(stock_gap)),
                }
            )
            totals_qty += qty
            totals_value += val

        reset_state()

    for move in move_rows:
        pid = move['product_id']
        if pid != cur_pid:
            flush_product(cur_pid)
            cur_pid = pid

        movement_count += 1
        last_movement_date = move['posting_date']
        qty = _signed_move_qty(move)
        rate = _rate_from_move(qty, move['unit_cost'], move['ext_cost'])

        if valuation_method == 'fifo':
            if qty > 0:
                layers.append({'qty': qty, 'rate': rate})
            elif qty < 0:
                need = -qty
                i = 0
                while need > 0 and i < len(layers):
                    take = min(layers[i]['qty'], need)
                    layers[i]['qty'] -= take
                    need -= take
                    if layers[i]['qty'] == 0:
                        i += 1
                layers = [layer for layer in layers if layer['qty'] > 0]
        elif valuation_method == 'lifo':
            if qty > 0:
                layers.append({'qty': qty, 'rate': rate})
            elif qty < 0:
                need = -qty
                i = len(layers) - 1
                while need > 0 and i >= 0:
                    take = min(layers[i]['qty'], need)
                    layers[i]['qty'] -= take
                    need -= take
                    if layers[i]['qty'] == 0:
                        layers.pop(i)
                    i -= 1
        elif valuation_method == 'mwa':
            if qty > 0:
                q += qty
                v += qty * rate
            elif qty < 0 and q > 0:
                avg = v / q if q else ZERO
                take = min(q, -qty)
                v -= take * avg
                q -= take
        elif valuation_method == 'latest':
            if qty > 0:
                latest = rate
                q += qty
                v += qty * latest
            elif qty < 0:
                take = min(q, -qty)
                v -= take * latest
                q -= take
                if q == 0:
                    latest = ZERO
        elif valuation_method == 'wac':
            if qty > 0:
                sum_in_qty += qty
                sum_in_val += qty * rate
            elif qty < 0:
                issues_qty += -qty

    flush_product(cur_pid)
    rows.sort(key=lambda row: (Decimal(row['closing_value']), row['product_name'] or ''), reverse=True)
    return rows, _q4(totals_qty), _q2(totals_value)


def _sort_rows(rows: list[dict], *, sort_by: str, sort_order: str):
    reverse = (sort_order or 'desc').lower() == 'desc'

    def key(row):
        if sort_by == 'qty':
            return Decimal(row['closing_qty'])
        if sort_by == 'name':
            return str(row.get('product_name') or '').lower()
        if sort_by == 'sku':
            return str(row.get('sku') or '').lower()
        if sort_by == 'last_movement_date':
            return row.get('last_movement_date') or ''
        if sort_by == 'reorder_gap':
            return Decimal(row.get('stock_gap') or '0')
        return Decimal(row['closing_value'])

    return sorted(rows, key=key, reverse=reverse)


def build_inventory_stock_summary(
    *,
    entity_id: int,
    entityfin_id: int | None = None,
    subentity_id: int | None = None,
    from_date=None,
    to_date=None,
    as_of_date=None,
    valuation_method: str = 'fifo',
    product_ids: list[int] | None = None,
    category_ids: list[int] | None = None,
    hsn_ids: list[int] | None = None,
    location_ids: list[int] | None = None,
    include_zero: bool = False,
    include_negative: bool = True,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = 'desc',
    page: int = 1,
    page_size: int = 100,
    paginate: bool = True,
):
    end_date = _resolve_end_date(from_date=from_date, to_date=to_date, as_of_date=as_of_date)
    base_qs = InventoryMove.objects.filter(entity_id=entity_id, posting_date__lte=end_date, product__is_service=False)
    base_qs = _apply_filters(
        base_qs,
        entity_id=entity_id,
        entityfin_id=entityfin_id,
        subentity_id=subentity_id,
        end_date=end_date,
        product_ids=product_ids,
        category_ids=category_ids,
        hsn_ids=hsn_ids,
        location_ids=location_ids,
        search=search,
    )

    rows, total_qty, total_value = _aggregate_product_rows(
        base_qs,
        entity_id=entity_id,
        valuation_method=(valuation_method or 'fifo').lower(),
        include_zero=include_zero,
        include_negative=include_negative,
    )
    rows = _sort_rows(rows, sort_by=(sort_by or 'value').lower(), sort_order=sort_order)

    if not include_negative:
        rows = [row for row in rows if Decimal(row['closing_qty']) >= 0]
    if not include_zero:
        rows = [row for row in rows if Decimal(row['closing_qty']) != 0]

    count = len(rows)
    if paginate:
        pages = ceil(count / page_size) if count else 0
        page = max(1, page)
        start = (page - 1) * page_size
        end = start + page_size
        page_rows = rows[start:end]
    else:
        page = 1
        pages = 1 if count else 0
        page_size = count or page_size
        page_rows = rows

    summary = {
        'product_count': count,
        'total_qty': str(total_qty),
        'total_value': str(total_value),
        'zero_stock_count': sum(1 for row in rows if Decimal(row['closing_qty']) == 0),
        'negative_stock_count': sum(1 for row in rows if Decimal(row['closing_qty']) < 0),
        'low_stock_count': sum(1 for row in rows if row.get('stock_status') == 'low'),
    }
    totals = {
        'closing_qty': str(total_qty),
        'closing_value': str(total_value),
    }
    pagination = {
        'count': count,
        'page': page,
        'pages': pages,
        'page_size': page_size,
    }
    return {
        'summary': summary,
        'totals': totals,
        'rows': page_rows,
        'pagination': pagination,
        '_meta': {
            'report_kind': 'inventory_stock_summary',
            'available_exports': [],
            'available_drilldowns': [],
            'end_date': end_date.isoformat() if isinstance(end_date, date_cls) else str(end_date),
        },
    }
