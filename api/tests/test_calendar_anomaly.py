from datetime import date

from app.anomaly import is_anomaly
from app.calendar_cz import easter, holiday_name, same_day_last_year


def test_easter_known_dates():
    assert easter(2024) == date(2024, 3, 31)
    assert easter(2025) == date(2025, 4, 20)
    assert easter(2026) == date(2026, 4, 5)


def test_same_weekday_last_year():
    d = date(2026, 10, 10)  # Saturday
    ly = same_day_last_year(d)
    assert ly.weekday() == d.weekday() == 5


def test_holiday_maps_to_same_holiday():
    assert holiday_name(date(2026, 4, 6)) == "Velikonoční pondělí"
    assert same_day_last_year(date(2026, 4, 6)) == date(2025, 4, 21)
    assert same_day_last_year(date(2026, 12, 25)) == date(2025, 12, 25)


def test_anomaly_needs_sigma_and_min_amount():
    hist = [10000, 10500, 9800, 10200, 10100, 9900, 10300, 10000]
    assert is_anomaly(16000, hist)
    assert not is_anomaly(10400, hist)
    small = [100, 110, 90, 105, 95, 100, 102, 98]
    assert not is_anomaly(400, small)  # >2σ but below 2 000 Kč


def test_anomaly_too_little_history():
    assert not is_anomaly(99999, [1, 2])
