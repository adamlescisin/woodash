from datetime import date, timedelta

from .calendar_cz import holiday_name, same_day_last_year, season


def ensure_dim_date(conn, first: date, last: date) -> None:
    """Fill dim_date from `first - 400d` (so same_day_last_year resolves) to `last + 1d`."""
    d = first - timedelta(days=400)
    rows = []
    while d <= last + timedelta(days=1):
        iso = d.isocalendar()
        hn = holiday_name(d)
        rows.append((d, iso.weekday, iso.week, d.month, d.year, season(d), hn is not None, hn, same_day_last_year(d)))
        d += timedelta(days=1)
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO dim_date VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", rows)
