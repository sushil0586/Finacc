from django.core.exceptions import ValidationError


def validate_geography_hierarchy(*, country=None, state=None, district=None, city=None, field_prefix=""):
    errors = {}

    def add(field, message):
        key = f"{field_prefix}{field}" if field_prefix else field
        errors[key] = message

    if state and country and getattr(state, "country_id", None) != getattr(country, "id", None):
        add("state", "Selected state does not belong to the selected country.")

    if district and state and getattr(district, "state_id", None) != getattr(state, "id", None):
        add("district", "Selected district does not belong to the selected state.")

    if city and district and getattr(city, "distt_id", None) != getattr(district, "id", None):
        add("city", "Selected city does not belong to the selected district.")

    if city and state:
        city_district = getattr(city, "distt", None)
        city_state_id = getattr(city_district, "state_id", None)
        if city_state_id and city_state_id != getattr(state, "id", None):
            add("city", "Selected city does not belong to the selected state.")

    if district and country:
        district_state = getattr(district, "state", None)
        district_country_id = getattr(district_state, "country_id", None)
        if district_country_id and district_country_id != getattr(country, "id", None):
            add("district", "Selected district does not belong to the selected country.")

    if city and country:
        city_district = getattr(city, "distt", None)
        city_state = getattr(city_district, "state", None) if city_district else None
        city_country_id = getattr(city_state, "country_id", None)
        if city_country_id and city_country_id != getattr(country, "id", None):
            add("city", "Selected city does not belong to the selected country.")

    if errors:
        raise ValidationError(errors)
