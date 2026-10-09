"""Czech calendar: public holidays and the 'same day last year' mapping.

A normal date maps to the same weekday 364 days earlier, so a Saturday is
never compared with a Monday. A public holiday maps to the same holiday
last year (spec: "Daily email / Rules").
"""
from datetime import date, timedelta

FIXED = {
    (1, 1): "Nový rok",
    (5, 1): "Svátek práce",
    (5, 8): "Den vítězství",
    (7, 5): "Cyril a Metoděj",
    (7, 6): "Jan Hus",
    (9, 28): "Den české státnosti",
    (10, 28): "Vznik Československa",
    (11, 17): "Den boje za svobodu a demokracii",
    (12, 24): "Štědrý den",
    (12, 25): "1. svátek vánoční",
    (12, 26): "2. svátek vánoční",
}


def easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def holidays(year: int) -> dict[date, str]:
    out = {date(year, m, d): name for (m, d), name in FIXED.items()}
    e = easter(year)
    out[e - timedelta(days=2)] = "Velký pátek"
    out[e + timedelta(days=1)] = "Velikonoční pondělí"
    return out


def holiday_name(d: date) -> str | None:
    return holidays(d.year).get(d)


def same_day_last_year(d: date) -> date:
    name = holiday_name(d)
    if name:
        for hd, n in holidays(d.year - 1).items():
            if n == name:
                return hd
    return d - timedelta(days=364)


def season(d: date) -> str:
    """Spring/summer Jan-Jun, autumn/winter Jul-Dec."""
    return f"{d.year}{'SS' if d.month <= 6 else 'FW'}"
