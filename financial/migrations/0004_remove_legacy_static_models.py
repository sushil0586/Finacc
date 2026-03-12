from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("financial", "0003_financialsettings"),
    ]

    operations = [
        migrations.DeleteModel(name="staticacountsmapping"),
        migrations.DeleteModel(name="staticacounts"),
    ]
