from __future__ import annotations

from rest_framework import serializers

from posting.models import EntryStatus, TxnType


def _parse_csv_tokens(value):
    """Normalize comma-delimited or repeated query values into trimmed tokens."""
    if value in (None, "", [], ()):
        return []
    if isinstance(value, (list, tuple)):
        raw = value
    else:
        raw = str(value).split(",")
    return [str(token).strip() for token in raw if str(token).strip()]


def _parse_csv_ints(value):
    """Parse CSV query params into integer ids with field-safe validation errors."""
    tokens = _parse_csv_tokens(value)
    results = []
    for token in tokens:
        try:
            results.append(int(token))
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError(f"Invalid integer value '{token}'.") from exc
    return results


class DaybookScopeSerializer(serializers.Serializer):
    """Validate Daybook query parameters for report-safe filtering."""

    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    voucher_type = serializers.CharField(required=False, allow_blank=True)
    transaction_type = serializers.CharField(required=False, allow_blank=True)
    account = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True)
    posted = serializers.BooleanField(required=False, allow_null=True, default=None)
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=500)

    def validate(self, attrs):
        from_date = attrs.get("from_date")
        to_date = attrs.get("to_date")
        if from_date and to_date and from_date > to_date:
            raise serializers.ValidationError({"to_date": "to_date must be on or after from_date."})

        txn_types = _parse_csv_tokens(attrs.get("voucher_type") or attrs.get("transaction_type"))
        valid_txn_types = {choice for choice, _ in TxnType.choices}
        invalid_txn_types = sorted(set(txn_types) - valid_txn_types)
        if invalid_txn_types:
            raise serializers.ValidationError(
                {"voucher_type": f"Unsupported voucher/transaction type(s): {', '.join(invalid_txn_types)}."}
            )

        statuses = []
        for token in _parse_csv_tokens(attrs.get("status")):
            lookup = token.strip().lower()
            if lookup.isdigit():
                statuses.append(int(lookup))
                continue
            mapping = {
                "draft": int(EntryStatus.DRAFT),
                "posted": int(EntryStatus.POSTED),
                "reversed": int(EntryStatus.REVERSED),
            }
            if lookup not in mapping:
                raise serializers.ValidationError({"status": f"Unsupported status '{token}'."})
            statuses.append(mapping[lookup])

        attrs["voucher_types"] = txn_types
        attrs["account_ids"] = _parse_csv_ints(attrs.get("account"))
        attrs["statuses"] = statuses
        return attrs


class CashbookScopeSerializer(serializers.Serializer):
    """Validate Cashbook query parameters and reject unsafe filter combinations."""

    entity = serializers.IntegerField()
    entityfinid = serializers.IntegerField(required=False, allow_null=True)
    subentity = serializers.IntegerField(required=False, allow_null=True)
    from_date = serializers.DateField(required=False, allow_null=True)
    to_date = serializers.DateField(required=False, allow_null=True)
    mode = serializers.ChoiceField(choices=("cash", "bank", "both"), required=False, default="both")
    cash_account = serializers.CharField(required=False, allow_blank=True)
    bank_account = serializers.CharField(required=False, allow_blank=True)
    account = serializers.CharField(required=False, allow_blank=True)
    voucher_type = serializers.CharField(required=False, allow_blank=True)
    search = serializers.CharField(required=False, allow_blank=True, max_length=200)
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=500)

    def validate(self, attrs):
        from_date = attrs.get("from_date")
        to_date = attrs.get("to_date")
        if from_date and to_date and from_date > to_date:
            raise serializers.ValidationError({"to_date": "to_date must be on or after from_date."})

        txn_types = _parse_csv_tokens(attrs.get("voucher_type"))
        valid_txn_types = {choice for choice, _ in TxnType.choices}
        invalid_txn_types = sorted(set(txn_types) - valid_txn_types)
        if invalid_txn_types:
            raise serializers.ValidationError(
                {"voucher_type": f"Unsupported voucher/transaction type(s): {', '.join(invalid_txn_types)}."}
            )

        attrs["voucher_types"] = txn_types
        attrs["cash_account_ids"] = _parse_csv_ints(attrs.get("cash_account"))
        attrs["bank_account_ids"] = _parse_csv_ints(attrs.get("bank_account"))
        attrs["counter_account_ids"] = _parse_csv_ints(attrs.get("account"))
        mode = attrs.get("mode", "both")
        if mode == "cash" and attrs["bank_account_ids"]:
            raise serializers.ValidationError({"bank_account": "bank_account cannot be used when mode='cash'."})
        if mode == "bank" and attrs["cash_account_ids"]:
            raise serializers.ValidationError({"cash_account": "cash_account cannot be used when mode='bank'."})
        overlap = set(attrs["cash_account_ids"]).intersection(attrs["bank_account_ids"])
        if overlap:
            raise serializers.ValidationError(
                {"cash_account": f"Accounts cannot be classified as both cash and bank: {', '.join(map(str, sorted(overlap)))}."}
            )
        return attrs
