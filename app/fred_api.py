"""FRED(Federal Reserve Economic Data) 클라이언트.

실업률(UNRATE) 등 거시경제 지표 조회.
API 키 불필요 — 공개 CSV 엔드포인트를 사용합니다.
"""
import csv
import io
import urllib.request
from typing import List, Optional, Tuple

_FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
_TIMEOUT = 15  # seconds


def fetch_fred_series(series_id: str) -> List[Tuple[str, float]]:
    """FRED 시계열 데이터를 [(date, value), ...] 오름차순으로 반환.

    결측값(".")은 제외합니다.
    """
    url = _FRED_CSV.format(series_id=series_id)
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
            content = resp.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"FRED 데이터 조회 실패 ({series_id}): {e}") from e

    rows: List[Tuple[str, float]] = []
    reader = csv.reader(io.StringIO(content))
    next(reader, None)  # 헤더 스킵
    for row in reader:
        if len(row) < 2 or row[1].strip() in (".", ""):
            continue
        try:
            rows.append((row[0].strip(), float(row[1].strip())))
        except ValueError:
            continue
    return sorted(rows, key=lambda x: x[0])


def get_unemployment_signal(lookback_months: int = 12) -> Optional[bool]:
    """실업률 방어 시그널.

    현재 실업률이 lookback_months 개월 이동평균보다 높으면 True(방어 신호).

    Returns:
        True  : 실업률 상승 추세 → 방어 신호
        False : 정상
        None  : 데이터 부족
    """
    series = fetch_fred_series("UNRATE")
    # lookback_months + 1개 필요 (MA 계산용)
    if len(series) < lookback_months + 1:
        return None
    recent = series[-(lookback_months + 1):]
    current_rate = recent[-1][1]
    ma = sum(v for _, v in recent[:lookback_months]) / lookback_months
    return current_rate > ma
