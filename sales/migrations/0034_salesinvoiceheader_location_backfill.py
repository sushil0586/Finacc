from django.db import migrations


def _pick_location(Godown, entity_id, subentity_id):
    qs = Godown.objects.filter(entity_id=entity_id, is_active=True)
    if subentity_id:
        location = qs.filter(subentity_id=subentity_id, is_default=True).order_by("id").first()
        if location:
            return location.id
        location = qs.filter(subentity_id=subentity_id).order_by("id").first()
        if location:
            return location.id
    location = qs.filter(subentity__isnull=True, is_default=True).order_by("id").first()
    if location:
        return location.id
    location = qs.filter(subentity__isnull=True).order_by("id").first()
    if location:
        return location.id
    location = qs.order_by("id").first()
    return location.id if location else None


def forwards(apps, schema_editor):
    SalesInvoiceHeader = apps.get_model("sales", "SalesInvoiceHeader")
    Godown = apps.get_model("entity", "Godown")
    for header in SalesInvoiceHeader.objects.filter(location__isnull=True).only("id", "entity_id", "subentity_id"):
        location_id = _pick_location(Godown, header.entity_id, header.subentity_id)
        if location_id:
            SalesInvoiceHeader.objects.filter(pk=header.pk).update(location_id=location_id)


def backwards(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0033_salesinvoiceheader_location"),
        ("entity", "0017_godown_is_default"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
