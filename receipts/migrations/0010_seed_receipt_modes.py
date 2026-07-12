from django.conf import settings
from django.db import migrations


DEFAULT_RECEIPT_MODES = [
    {"paymentmodecode": "CASH", "paymentmode": "Cash", "iscash": True},
    {"paymentmodecode": "BANK_TRANSFER", "paymentmode": "Bank Transfer", "iscash": False},
    {"paymentmodecode": "CHEQUE", "paymentmode": "Cheque", "iscash": False},
    {"paymentmodecode": "UPI", "paymentmode": "UPI", "iscash": False},
    {"paymentmodecode": "NEFT", "paymentmode": "NEFT", "iscash": False},
]


def seed_receipt_modes(apps, schema_editor):
    ReceiptMode = apps.get_model("receipts", "ReceiptMode")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    actor = (
        ReceiptMode.objects.order_by("id").values_list("createdby_id", flat=True).first()
        or User.objects.order_by("id").values_list("id", flat=True).first()
    )
    if not actor:
        return

    for row in DEFAULT_RECEIPT_MODES:
        existing = (
            ReceiptMode.objects.filter(paymentmodecode__iexact=row["paymentmodecode"]).first()
            or ReceiptMode.objects.filter(paymentmode__iexact=row["paymentmode"]).first()
        )
        if existing:
            changed = False
            if str(existing.paymentmodecode or "").strip() != row["paymentmodecode"]:
                existing.paymentmodecode = row["paymentmodecode"]
                changed = True
            if not str(existing.paymentmode or "").strip():
                existing.paymentmode = row["paymentmode"]
                changed = True
            if bool(existing.iscash) != bool(row["iscash"]):
                existing.iscash = row["iscash"]
                changed = True
            if changed:
                existing.save(update_fields=["paymentmodecode", "paymentmode", "iscash"])
            continue

        ReceiptMode.objects.create(createdby_id=actor, **row)


class Migration(migrations.Migration):

    dependencies = [
        ("receipts", "0009_receiptvoucherattachment"),
    ]

    operations = [
        migrations.RunPython(seed_receipt_modes, migrations.RunPython.noop),
    ]
