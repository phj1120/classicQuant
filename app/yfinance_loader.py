"""Yahoo Finance 기반 장기 OHLC 데이터 수집 모듈.

KIS API는 최대 ~500거래일(2년)만 지원하므로,
장기 백테스트용 데이터는 Yahoo Finance에서 수집합니다.

- API 키 불필요
- 최대 20년+ 데이터 지원
- 미국 ETF 전종목 지원
"""
import time
from typing import Dict, List

import yfinance as yf


def fetch_all_tickers(
    tickers: List[str],
    period: str = "max",
) -> Dict[str, List[Dict]]:
    """Yahoo Finance로 여러 티커의 OHLC 히스토리를 수집한다.

    Args:
        tickers: 티커 목록
        period: 수집 기간 ("max", "20y", "10y" 등)

    Returns:
        {ticker: [{"date": "YYYY-MM-DD", "close": "123.45"}, ...]} 날짜 오름차순
    """
    if not tickers:
        return {}

    print(f"[DL] Yahoo Finance 수집 시작 | {len(tickers)}개 티커 | period={period}")

    try:
        data = yf.download(
            tickers=tickers,
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        print(f"  [!!]  일괄 다운로드 실패 ({e}), 개별 수집으로 전환...")
        return _fetch_individually(tickers, period)

    if data is None or data.empty:
        print("  [!!]  데이터 없음, 개별 수집으로 전환...")
        return _fetch_individually(tickers, period)

    result: Dict[str, List[Dict]] = {}

    if len(tickers) == 1:
        # 단일 티커: data["Close"] → Series
        ticker = tickers[0]
        try:
            rows = _series_to_rows(data["Close"])
            _log_ticker(ticker, rows)
            if rows:
                result[ticker] = rows
        except Exception as e:
            print(f"  [!!]  {ticker} 파싱 실패: {e}")
    else:
        # 다중 티커: data["Close"] → DataFrame (columns = ticker names)
        try:
            close_df = data["Close"]
            for ticker in tickers:
                if ticker not in close_df.columns:
                    print(f"  [!!]  {ticker}: Yahoo Finance에 없음")
                    continue
                rows = _series_to_rows(close_df[ticker])
                _log_ticker(ticker, rows)
                if rows:
                    result[ticker] = rows
        except Exception as e:
            print(f"  [!!]  다중 파싱 실패 ({e}), 개별 수집으로 전환...")
            return _fetch_individually(tickers, period)

    print(f"\n[ST] 수집 완료: {len(result)}/{len(tickers)}개 성공")
    return result


def _series_to_rows(series) -> List[Dict]:
    """Pandas Series → [{"date": "YYYY-MM-DD", "close": "123.45"}, ...] 오름차순."""
    rows = []
    for date, price in series.dropna().items():
        try:
            date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10]
            p = float(price)
            if p > 0:
                rows.append({"date": date_str, "close": f"{p:.4f}"})
        except (ValueError, TypeError):
            continue
    return sorted(rows, key=lambda r: r["date"])


def _log_ticker(ticker: str, rows: List[Dict]) -> None:
    if rows:
        print(f"  [OK] {ticker:<10}: {len(rows):>5}일  ({rows[0]['date']} ~ {rows[-1]['date']})")
    else:
        print(f"  [!!]  {ticker:<10}: 데이터 없음")


def _fetch_individually(
    tickers: List[str],
    period: str,
) -> Dict[str, List[Dict]]:
    """티커를 하나씩 개별 다운로드한다 (일괄 실패 시 폴백)."""
    result: Dict[str, List[Dict]] = {}
    for ticker in tickers:
        try:
            data = yf.download(
                ticker,
                period=period,
                interval="1d",
                auto_adjust=True,
                progress=False,
            )
            if data is not None and not data.empty:
                rows = _series_to_rows(data["Close"])
                _log_ticker(ticker, rows)
                if rows:
                    result[ticker] = rows
            else:
                print(f"  [!!]  {ticker}: 데이터 없음")
        except Exception as e:
            print(f"  [ER] {ticker}: {e}")
        time.sleep(0.05)
    return result
