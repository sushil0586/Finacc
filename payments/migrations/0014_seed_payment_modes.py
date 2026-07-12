from django.conf import settings
from django.db import migrations


DEFAULT_PAYMENT_MODES = [
    {"paymentmodecode": "CASH", "paymentmode": "Cash", "iscash": True},
    {"paymentmodecode": "BANK_TRANSFER", "paymentmode": "Bank Transfer", "iscash": False},
    {"paymentmodecode": "CHEQUE", "paymentmode": "Cheque", "iscash": False},
    {"paymentmodecode": "UPI", "paymentmode": "UPI", "iscash": False},
    {"paymentmodecode": "NEFT", "paymentmode": "NEFT", "iscash": False},
]


def seed_payment_modes(apps, schema_editor):
    PaymentMode = apps.get_model("payments", "PaymentMode")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    actor = (
        PaymentMode.objects.order_by("id").values_list("createdby_id", flat=True).first()
        or User.objects.order_by("id").values_list("id", flat=True).first()
    )
    if not actor:
        return

    for row in DEFAULT_PAYMENT_MODES:
        existing = (
            PaymentMode.objects.filter(paymentmodecode__iexact=row["paymentmodecode"]).first()
            or PaymentMode.objects.filter(paymentmode__iexact=row["paymentmode"]).first()
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

        PaymentMode.objects.create(createdby_id=actor, **row)


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0013_paymentvoucherattachment"),
    ]

    operations = [
        migrations.RunPython(seed_payment_modes, migrations.RunPython.noop),
    ]
