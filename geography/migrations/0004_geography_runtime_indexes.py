from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("geography", "0003_city_uq_city_active_district_code_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="country",
            index=models.Index(fields=["isactive", "countryname"], name="ix_country_act_name"),
        ),
        migrations.AddIndex(
            model_name="state",
            index=models.Index(fields=["country", "isactive", "statename"], name="ix_state_country_act_name"),
        ),
        migrations.AddIndex(
            model_name="district",
            index=models.Index(fields=["state", "isactive", "districtname"], name="ix_dist_state_act_name"),
        ),
        migrations.AddIndex(
            model_name="city",
            index=models.Index(fields=["distt", "isactive", "cityname"], name="ix_city_dist_act_name"),
        ),
        migrations.AddIndex(
            model_name="city",
            index=models.Index(fields=["isactive", "pincode"], name="ix_city_act_pincode"),
        ),
    ]
