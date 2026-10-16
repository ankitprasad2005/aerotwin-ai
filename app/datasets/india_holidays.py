"""Indian public holidays from the offline, deterministic `holidays` package (no download, no snapshot)."""
from datetime import date, timedelta

import holidays

SOURCE = "india_holidays"
COUNTRY = "IN"
WINDOW_WEEKS = 8
PACKAGE_URL = "https://pypi.org/project/holidays/"


def upcoming_holidays(today: date, weeks: int = WINDOW_WEEKS) -> list[dict]:
    """Public holidays from `today` through the next `weeks` weeks (inclusive), ascending: [{date, name}]."""
    end = today + timedelta(weeks=weeks)
    calendar = holidays.country_holidays(COUNTRY, years=sorted({today.year, end.year}))
    return [{"date": d.isoformat(), "name": name} for d, name in sorted(calendar.items()) if today <= d <= end]
