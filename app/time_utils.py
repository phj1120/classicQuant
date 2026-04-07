from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from app.constants import US_MARKET_TZ


def trading_date_label() -> str:
    """미국 시장 기준 거래일 라벨을 YYYY-MM-DD로 반환한다."""
    if ZoneInfo is None:
        return datetime.now().strftime("%Y-%m-%d")
    return datetime.now(ZoneInfo(US_MARKET_TZ)).strftime("%Y-%m-%d")
