from datetime import datetime

def reset_counter_if_needed(settings):
    today = datetime.today()
    should_reset = False

    if settings.reset_frequency == 'monthly':
        should_reset = not settings.last_reset_date or (
            settings.last_reset_date.year != today.year or
            settings.last_reset_date.month != today.month
        )
    elif settings.reset_frequency == 'yearly':
        should_reset = not settings.last_reset_date or (
            settings.last_reset_date.year != today.year
        )

    if should_reset:
        settings.current_number = settings.starting_number
        settings.last_reset_date = today
        settings.save()


def build_document_number(settings):
    now = datetime.now()
    padded_number = str(settings.current_number).zfill(settings.number_padding or 0)

    context = {
        "prefix": settings.prefix or '',
        "suffix": settings.suffix or '',
        "year": str(now.year),
        "month": f"{now.month:02d}",
        "number": padded_number
    }

    if settings.custom_format:
        return settings.custom_format.format(**context)

    parts = [settings.prefix]
    if settings.include_year:
        parts.append(str(now.year))
    if settings.include_month:
        parts.append(f"{now.month:02d}")
    parts.append(padded_number)
    if settings.suffix:
        parts.append(settings.suffix)
    return settings.separator.join(parts)