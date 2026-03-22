from typing import Dict, List, Optional, Tuple

from app.constants import DATE_KEYS, PRICE_KEYS, QTY_KEYS, TICKER_KEYS


def extract_price(row: Dict) -> Optional[float]:
    for key in PRICE_KEYS:
        value = row.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def extract_date(row: Dict) -> Optional[str]:
    for key in DATE_KEYS:
        value = row.get(key)
        if value:
            return str(value)
    return None


def extract_ticker(row: Dict) -> Optional[str]:
    for key in TICKER_KEYS:
        value = row.get(key)
        if value:
            return str(value).strip()
    return None


def extract_qty(row: Dict) -> int:
    for key in QTY_KEYS:
        value = row.get(key)
        if value is None or value == "":
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return 0


def parse_history(raw: List[Dict]) -> List[float]:
    rows: List[Tuple[Optional[str], float]] = []
    for row in raw:
        price = extract_price(row)
        if price is None:
            continue
        date = extract_date(row)
        rows.append((date, price))

    if not rows:
        return []

    if any(date is not None for date, _ in rows):
        rows.sort(key=lambda x: (x[0] is None, x[0]))
    else:
        rows = list(reversed(rows))

    return [price for _, price in rows]
