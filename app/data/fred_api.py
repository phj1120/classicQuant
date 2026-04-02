"""FRED/BLS 실업률 클라이언트.

실업률(UNRATE) 조회 우선순위:
  1. BLS 공개 API (키 불필요, 최근 ~26개월)
  2. FRED 공개 CSV (키 불필요, 전체 기간 — 간헐적 rate limit 있음)

프로세스 단위 캐시: UNRATE는 월 1회 발표이므로 한 번만 조회한다.
백테스트처럼 수천 번 루프를 돌 때 rate limit을 방지하기 위해 사용한다.
"""
import csv
import io
import json
import urllib.request
from typing import List, Optional, Tuple

_FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
_BLS_UNRATE_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/LNS14000000"
_TIMEOUT = 15  # seconds

_cache: dict = {}


def _fetch_bls_unrate() -> List[Tuple[str, float]]:
    """BLS 공개 API에서 실업률을 가져온다 (키 불필요, 최근 ~26개월).

    BLS series LNS14000000 = 계절조정 실업률(UNRATE와 동일).
    """
    with urllib.request.urlopen(_BLS_UNRATE_URL, timeout=_TIMEOUT) as resp:
        data = json.loads(resp.read())

    rows: List[Tuple[str, float]] = []
    for item in data.get("Results", {}).get("series", [{}])[0].get("data", []):
        period = item.get("period", "")  # "M01" ~ "M12"
        if not period.startswith("M"):
            continue
        month = period[1:]
        date_str = f"{item['year']}-{month}-01"
        try:
            rows.append((date_str, float(item["value"])))
        except (ValueError, KeyError):
            continue
    return sorted(rows, key=lambda x: x[0])


def _fetch_fred_unrate() -> List[Tuple[str, float]]:
    """FRED 공개 CSV에서 실업률을 가져온다 (전체 기간, 간헐적 rate limit 있음)."""
    url = _FRED_CSV.format(series_id="UNRATE")
    with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
        content = resp.read().decode("utf-8")

    rows: List[Tuple[str, float]] = []
    reader = csv.reader(io.StringIO(content))
    next(reader, None)
    for row in reader:
        if len(row) < 2 or row[1].strip() in (".", ""):
            continue
        try:
            rows.append((row[0].strip(), float(row[1].strip())))
        except ValueError:
            continue
    return sorted(rows, key=lambda x: x[0])


def fetch_fred_series(series_id: str) -> List[Tuple[str, float]]:
    """실업률 시계열을 [(date, value), ...] 오름차순으로 반환.

    UNRATE는 BLS → FRED 순으로 시도한다.
    프로세스 내 첫 호출 시 한 번만 HTTP 요청하고 이후는 캐시를 반환한다.
    """
    if series_id in _cache:
        return _cache[series_id]

    result: Optional[List[Tuple[str, float]]] = None

    if series_id == "UNRATE":
        try:
            result = _fetch_bls_unrate()
        except Exception:
            pass

    if not result:
        try:
            result = _fetch_fred_unrate() if series_id == "UNRATE" else []
            if not result:
                raise RuntimeError(f"FRED 데이터 조회 실패 ({series_id})")
        except Exception as e:
            raise RuntimeError(f"FRED 데이터 조회 실패 ({series_id}): {e}") from e

    _cache[series_id] = result
    return result


def get_unemployment_signal(lookback_months: int = 12) -> Optional[bool]:
    """실업률 방어 시그널.

    현재 실업률이 lookback_months 개월 이동평균보다 높으면 True(방어 신호).

    Returns:
        True  : 실업률 상승 추세 → 방어 신호
        False : 정상
        None  : 데이터 부족
    """
    series = fetch_fred_series("UNRATE")
    if len(series) < lookback_months + 1:
        return None
    recent = series[-(lookback_months + 1):]
    current_rate = recent[-1][1]
    ma = sum(v for _, v in recent[:lookback_months]) / lookback_months
    return current_rate > ma
