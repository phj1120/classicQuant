from datetime import datetime, timedelta
from typing import Dict, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from app.constants import (
    DEFAULT_CHECK_HOLIDAY,
    DEFAULT_EXECUTION_OFFSET_MINUTES,
    DEFAULT_EXECUTION_WINDOW_MINUTES,
    US_MARKET_COUNTRY_CODES,
    US_MARKET_EXCHANGE_CODES,
    US_MARKET_OPEN_HOUR,
    US_MARKET_OPEN_MINUTE,
    US_MARKET_TZ,
)
from app.kis_api import KoreaInvestmentAPI


def _is_us_row(row: Dict) -> bool:
    natn = str(row.get("natn_eng_abrv_cd", "")).upper()
    natn_cd = str(row.get("tr_natn_cd", "")).upper()
    market = str(row.get("tr_mket_cd", "")).upper()
    return natn in US_MARKET_COUNTRY_CODES or natn_cd == "US" or market in US_MARKET_EXCHANGE_CODES


def is_us_market_holiday(api: KoreaInvestmentAPI, date_et: datetime) -> Optional[bool]:
    """미국 시장 휴장 여부를 판단한다.

    해외결제일자조회(CTOS5011R) API는 해당 날짜에 결제가 이루어지는
    시장 목록을 반환한다. 미국 시장 row가 존재하면 개장일, 없으면 휴장일.
    """
    if date_et.weekday() >= 5:
        print("⏸️  주말 (휴장)")
        return True

    trad_dt = date_et.strftime("%Y%m%d")
    rows = api.get_countries_holiday(trad_dt)
    if rows is None:
        print("⚠️  해외결제일자조회 API 오류 → 개장 간주")
        return False

    if not rows:
        print("⚠️  해외결제일자조회 결과 없음 → 개장 간주")
        return False

    us_rows = [r for r in rows if _is_us_row(r)]

    if us_rows:
        markets = [r.get("tr_mket_name", r.get("tr_mket_cd", "")) for r in us_rows]
        print(f"✅ 미국 시장 개장 확인 ({', '.join(markets)})")
        return False

    # 미국 시장 row가 없으면 휴장
    sample_markets = [r.get("tr_mket_name", r.get("natn_eng_abrv_cd", "")) for r in rows[:3]]
    print(f"⏸️  미국 시장 휴장 (응답에 미국 없음, 예: {', '.join(sample_markets)})")
    return True


def should_execute_now(execution_cfg: Dict, api: Optional[KoreaInvestmentAPI]) -> bool:
    if not execution_cfg.get("market_open_plus", False):
        return True

    if ZoneInfo is None:
        print("⚠️  zoneinfo 미지원: 시간 조건을 건너뜁니다.")
        return True

    offset_minutes = int(execution_cfg.get("offset_minutes", DEFAULT_EXECUTION_OFFSET_MINUTES))
    window_minutes = int(execution_cfg.get("window_minutes", DEFAULT_EXECUTION_WINDOW_MINUTES))
    tz = ZoneInfo(US_MARKET_TZ)
    now = datetime.now(tz)

    if now.weekday() >= 5:
        print("⏸️  주말: 실행 스킵")
        return False

    market_open = now.replace(
        hour=US_MARKET_OPEN_HOUR,
        minute=US_MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0,
    )
    target_time = market_open + timedelta(minutes=offset_minutes)
    window_end = target_time + timedelta(minutes=window_minutes)

    if now < target_time or now >= window_end:
        print(
            "⏸️  실행 시간 아님 "
            f"(now {now.strftime('%H:%M')}, target {target_time.strftime('%H:%M')})"
        )
        return False

    if execution_cfg.get("check_holiday", DEFAULT_CHECK_HOLIDAY) and api is not None:
        holiday = is_us_market_holiday(api, now)
        if holiday is True:
            print("⏸️  미국장 휴장: 실행 스킵")
            return False
        if holiday is None:
            print("⚠️  휴장 여부 불명: 실행 계속")

    return True
