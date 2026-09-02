from django.db import migrations
from django.db.models import Q


INDIA_STATES_GST = [
    ("01", "Jammu and Kashmir", ["JK"]),
    ("02", "Himachal Pradesh", ["HP"]),
    ("03", "Punjab", ["PB"]),
    ("04", "Chandigarh", ["CH"]),
    ("05", "Uttarakhand", ["UK", "UT"]),
    ("06", "Haryana", ["HR"]),
    ("07", "Delhi", ["DL"]),
    ("08", "Rajasthan", ["RJ"]),
    ("09", "Uttar Pradesh", ["UP"]),
    ("10", "Bihar", ["BR"]),
    ("11", "Sikkim", ["SK"]),
    ("12", "Arunachal Pradesh", ["AR"]),
    ("13", "Nagaland", ["NL"]),
    ("14", "Manipur", ["MN"]),
    ("15", "Mizoram", ["MZ"]),
    ("16", "Tripura", ["TR"]),
    ("17", "Meghalaya", ["ML"]),
    ("18", "Assam", ["AS"]),
    ("19", "West Bengal", ["WB"]),
    ("20", "Jharkhand", ["JH"]),
    ("21", "Odisha", ["OD", "OR"]),
    ("22", "Chhattisgarh", ["CG"]),
    ("23", "Madhya Pradesh", ["MP"]),
    ("24", "Gujarat", ["GJ"]),
    ("26", "Dadra and Nagar Haveli and Daman and Diu", ["DH"]),
    ("27", "Maharashtra", ["MH"]),
    ("28", "Andhra Pradesh", []),
    ("29", "Karnataka", ["KA"]),
    ("30", "Goa", ["GA"]),
    ("31", "Lakshadweep", ["LD"]),
    ("32", "Kerala", ["KL"]),
    ("33", "Tamil Nadu", ["TN"]),
    ("34", "Puducherry", ["PY"]),
    ("35", "Andaman and Nicobar Islands", []),
    ("36", "Telangana", ["TS"]),
    ("37", "Andhra Pradesh (New)", ["AP"]),
    ("38", "Ladakh", ["LA"]),
    ("97", "Other Territory", []),
]

STATE_NAME_ALIASES = {
    "orissa": "odisha",
    "pondicherry": "puducherry",
    "nct of delhi": "delhi",
    "delhi ncr": "delhi",
    "andaman and nicobar": "andaman and nicobar islands",
    "andaman nicobar islands": "andaman and nicobar islands",
    "dadra and nagar haveli": "dadra and nagar haveli and daman and diu",
    "daman and diu": "dadra and nagar haveli and daman and diu",
}


def norm(value):
    value = str(value or "").strip().lower().replace("&", " and ")
    value = " ".join("".join(ch if ch.isalnum() else " " for ch in value).split())
    return STATE_NAME_ALIASES.get(value, value)


def repoint_state_references(apps, schema_editor, from_state_id, to_state_id):
    State = apps.get_model("geography", "State")
    existing_tables = set(schema_editor.connection.introspection.table_names())
    for model in apps.get_models():
        if model._meta.db_table not in existing_tables:
            continue
        updates = {}
        filters = {}
        for field in model._meta.fields:
            remote_model = getattr(getattr(field, "remote_field", None), "model", None)
            if remote_model == State:
                filters[field.attname] = from_state_id
                updates[field.attname] = to_state_id
        for attname, value in filters.items():
            model.objects.filter(**{attname: value}).update(**{attname: updates[attname]})


def normalize_india_state_codes(apps, schema_editor):
    Country = apps.get_model("geography", "Country")
    State = apps.get_model("geography", "State")

    india_countries = Country.objects.filter(
        Q(countrycode__iexact="IN")
        | Q(countrycode__iexact="IND")
        | Q(countryname__iexact="India")
    )

    for country in india_countries:
        states = list(State.objects.filter(country=country))
        for code, canonical_name, aliases in INDIA_STATES_GST:
            name_keys = {norm(canonical_name)}
            alias_codes = {code, *aliases}
            matches = [
                state
                for state in states
                if norm(state.statename) in name_keys
                or str(state.statecode or "").strip().upper() in alias_codes
                or str(state.statecode or "").strip().zfill(2) == code
            ]
            if not matches:
                continue

            active_code_match = next(
                (
                    state
                    for state in matches
                    if state.isactive and str(state.statecode or "").strip().zfill(2) == code
                ),
                None,
            )
            canonical = active_code_match or sorted(matches, key=lambda state: state.id)[0]

            for duplicate in matches:
                if duplicate.id == canonical.id:
                    continue
                repoint_state_references(apps, schema_editor, duplicate.id, canonical.id)
                duplicate.isactive = False
                duplicate.save(update_fields=["isactive"])

            canonical.statename = canonical_name
            canonical.statecode = code
            canonical.country = country
            canonical.isactive = True
            canonical.save(update_fields=["statename", "statecode", "country", "isactive"])


class Migration(migrations.Migration):

    dependencies = [
        ("geography", "0004_geography_runtime_indexes"),
    ]

    operations = [
        migrations.RunPython(normalize_india_state_codes, migrations.RunPython.noop),
    ]
