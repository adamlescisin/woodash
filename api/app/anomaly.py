from statistics import mean, pstdev


def is_anomaly(value: float, history: list[float], min_abs: float = 2000.0, k: float = 2.0) -> bool:
    """Spec: deviation beyond ±2 std devs of the last 8 same weekdays AND above a minimum amount."""
    if len(history) < 4:
        return False
    mu, sd = mean(history), pstdev(history)
    dev = value - mu
    return abs(dev) > k * sd and abs(dev) >= min_abs
