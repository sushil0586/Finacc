from datetime import date

from django.db import migrations, models


def backfill_holiday_calendar_periods(apps, schema_editor):
    HrHolidayCalendar = apps.get_model("hrms", "HrHolidayCalendar")
    for calendar in HrHolidayCalendar.objects.all().iterator():
        year = int(calendar.calendar_year)
        calendar.period_start = date(year, 1, 1)
        calendar.period_end = date(year, 12, 31)
        calendar.save(update_fields=["period_start", "period_end"])


class Migration(migrations.Migration):
    dependencies = [
        ("hrms", "0006_leavepolicy_leave_year_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="hrholidaycalendar",
            name="period_end",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="hrholidaycalendar",
            name="period_start",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_holiday_calendar_periods, migrations.RunPython.noop),
    ]
