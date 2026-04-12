from __future__ import annotations

from rest_framework import serializers


def _parse_int_list(value):
    if value in (None, '', []):
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = str(value).split(',')

    parsed = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        parsed.append(int(text))
    return parsed


class InventoryReportScopeSerializer(serializers.Serializer):
    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    financial_year = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)

    scope_mode = serializers.ChoiceField(
        choices=('financial_year', 'month', 'quarter', 'year', 'custom', 'as_of'),
        required=False,
        allow_null=True,
    )
    as_on_date = serializers.DateField(required=False, allow_null=True)
    date_from = serializers.DateField(required=False, allow_null=True, write_only=True)
    date_to = serializers.DateField(required=False, allow_null=True, write_only=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    as_of_date = serializers.DateField(required=False, allow_null=True)

    product = serializers.IntegerField(required=False, allow_null=True)
    product_ids = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    category = serializers.IntegerField(required=False, allow_null=True)
    category_ids = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    hsn = serializers.IntegerField(required=False, allow_null=True)
    hsn_ids = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    location = serializers.IntegerField(required=False, allow_null=True)
    location_ids = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    group_by_location = serializers.BooleanField(required=False)
    bucket_ends = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    non_moving_days = serializers.IntegerField(required=False, min_value=1, allow_null=True)

    valuation_method = serializers.ChoiceField(
        choices=('fifo', 'lifo', 'mwa', 'wac', 'latest'),
        required=False,
        allow_null=True,
    )
    include_zero = serializers.BooleanField(required=False)
    include_negative = serializers.BooleanField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sort_by = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sort_order = serializers.ChoiceField(choices=('asc', 'desc'), required=False, allow_null=True)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=500)
    export = serializers.ChoiceField(choices=('excel', 'pdf', 'csv'), required=False, allow_null=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if attrs.get('financial_year') and not attrs.get('entityfinid'):
            attrs['entityfinid'] = attrs['financial_year']
        if attrs.get('entityfinid') and not attrs.get('financial_year'):
            attrs['financial_year'] = attrs['entityfinid']

        if attrs.get('as_on_date') and not attrs.get('as_of_date'):
            attrs['as_of_date'] = attrs['as_on_date']
        if attrs.get('as_of_date') and not attrs.get('as_on_date'):
            attrs['as_on_date'] = attrs['as_of_date']

        date_from = attrs.get('date_from')
        date_to = attrs.get('date_to')
        from_date = attrs.get('from_date')
        to_date = attrs.get('to_date')
        errors = {}
        if date_from and from_date and date_from != from_date:
            errors['date_from'] = ['date_from must match from_date when both are provided.']
        if date_to and to_date and date_to != to_date:
            errors['date_to'] = ['date_to must match to_date when both are provided.']
        if errors:
            raise serializers.ValidationError(errors)
        if date_from and not from_date:
            attrs['from_date'] = date_from
        if date_to and not to_date:
            attrs['to_date'] = date_to

        if 'include_zero' not in attrs:
            attrs['include_zero'] = False
        if 'include_negative' not in attrs:
            attrs['include_negative'] = True
        if 'valuation_method' not in attrs or attrs.get('valuation_method') is None:
            attrs['valuation_method'] = 'fifo'
        if 'scope_mode' not in attrs or attrs.get('scope_mode') is None:
            attrs['scope_mode'] = 'as_of'
        if 'sort_order' not in attrs or attrs.get('sort_order') is None:
            attrs['sort_order'] = 'desc'
        if 'group_by_location' not in attrs:
            attrs['group_by_location'] = True
        if 'bucket_ends' not in attrs or attrs.get('bucket_ends') in (None, ''):
            attrs['bucket_ends'] = [30, 60, 90, 120, 150]
        if 'non_moving_days' not in attrs or attrs.get('non_moving_days') in (None, ''):
            attrs['non_moving_days'] = 90

        attrs['product_ids'] = _parse_int_list(attrs.get('product_ids'))
        attrs['category_ids'] = _parse_int_list(attrs.get('category_ids'))
        attrs['hsn_ids'] = _parse_int_list(attrs.get('hsn_ids'))
        attrs['location_ids'] = _parse_int_list(attrs.get('location_ids'))
        attrs['bucket_ends'] = _parse_int_list(attrs.get('bucket_ends'))

        single_filters = {
            'product': 'product_ids',
            'category': 'category_ids',
            'hsn': 'hsn_ids',
            'location': 'location_ids',
        }
        for singular, plural in single_filters.items():
            if attrs.get(singular) is not None:
                attrs[plural] = [attrs[singular]]

        return attrs
