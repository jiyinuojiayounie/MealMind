from datetime import date


def parse_calendar_date(value: object) -> date:
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        except ValueError:
            pass
    raise ValueError("Use a valid calendar date in YYYY-MM-DD format.")
