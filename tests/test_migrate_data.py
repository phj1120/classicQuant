"""run_migrate_data.py의 핵심 로직(헤더 승격/날짜 정규화/NAV 재구성/이상치 처리)을
합성 데이터로 검증한다. 실제 data/ 디렉터리는 건드리지 않는다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run_migrate_data as migrate


# ── 헤더 승격 ─────────────────────────────────────────────────────────────────

def test_promote_header_pads_short_rows():
    rows = [["2026-01-01", "1.0", "0.0", "100.0"]]  # 구버전 4열
    target = ["date", "nav", "daily_return", "total_equity", "fx_rate", "krw_nav"]
    out = migrate.promote_header(rows, target)
    assert out[0] == ["2026-01-01", "1.0", "0.0", "100.0", "", ""]


def test_promote_header_truncates_long_rows():
    rows = [["a", "b", "c", "d", "e", "f", "g"]]
    out = migrate.promote_header(rows, ["a", "b", "c"])
    assert out[0] == ["a", "b", "c"]


# ── 날짜 정규화 + 중복 제거 ───────────────────────────────────────────────────

def test_normalize_and_dedupe_merges_mixed_date_formats():
    rows = [
        ["20260316", "1.0", "0.0", "100"],
        ["2026-03-16", "2.0", "0.5", "150"],  # 같은 날짜, 뒤에 온 행이 우선
        ["2026-03-17", "2.1", "0.05", "155"],
    ]
    out = migrate.normalize_and_dedupe(rows, date_idx=0)
    assert len(out) == 2
    assert out[0] == ["2026-03-16", "2.0", "0.5", "150"]
    assert out[1][0] == "2026-03-17"


def test_normalize_and_dedupe_with_extra_key():
    rows = [
        ["20260101", "daa", "0.01", "1.01"],
        ["2026-01-01", "vaa", "0.02", "1.02"],
        ["2026-01-01", "daa", "0.03", "1.03"],  # (date, strategy) 중복 → 마지막 우선
    ]
    out = migrate.normalize_and_dedupe(rows, date_idx=0, extra_key_idx=1)
    assert len(out) == 2
    daa_row = [r for r in out if r[1] == "daa"][0]
    assert daa_row[2] == "0.03"


# ── NAV 재구성 ────────────────────────────────────────────────────────────────

def _nav_row(date, nav, dr, equity):
    return [date, f"{nav:.6f}", f"{dr:.6f}", f"{equity:.2f}", "", ""]


def test_reconstruct_replaces_corrupted_window_with_holdings_based_equity():
    """체결 전 잔고 재조회로 오염된 구간(±150%)을 holdings×ohlc+cash로 재계산하면
    정상적인 소폭 수익률로 복원되어야 한다.
    """
    nav_rows = [
        _nav_row("2026-04-08", 2.0, 0.0, 1000.0),   # 마지막 정상 구간
        _nav_row("2026-04-09", 5.0, 1.5, 2500.0),    # 오염: +150%
        _nav_row("2026-04-10", 2.5, -0.5, 1250.0),   # 오염: -50%
    ]
    holdings_by_date = {
        "2026-04-09": [{"date": "2026-04-09", "ticker": "SPY", "qty": "2", "price": "500"}],
        "2026-04-10": [{"date": "2026-04-10", "ticker": "SPY", "qty": "2", "price": "505"}],
    }
    ohlc_prices = {"SPY": {"2026-04-09": 500.0, "2026-04-10": 505.0}}
    state_by_date = {
        "2026-04-09": {"cash": "10.0"},
        "2026-04-10": {"cash": "10.0"},
    }

    reconstructed, unresolved = migrate.reconstruct_portfolio_nav_actual(
        nav_rows, "2026-04-09", holdings_by_date, ohlc_prices, state_by_date,
    )

    assert unresolved == []
    row_0409 = [r for r in reconstructed if r[0] == "2026-04-09"][0]
    row_0410 = [r for r in reconstructed if r[0] == "2026-04-10"][0]

    # 04-09: equity = 2*500 + 10 = 1010, prev(04-08)=1000 → dr ≈ +1%
    assert abs(float(row_0409[2]) - 0.01) < 1e-6
    assert abs(float(row_0409[1]) - 2.02) < 1e-6  # nav = 2.0 * 1.01

    # 04-10: equity = 2*505 + 10 = 1020, prev(04-09 재구성값)=1010 → dr ≈ +0.99%
    assert abs(float(row_0410[3]) - 1020.0) < 1e-6
    assert float(row_0410[2]) < 0.02  # 더 이상 -50%가 아님


def test_reconstruct_leaves_unresolved_rows_when_no_holdings_data():
    nav_rows = [
        _nav_row("2026-04-08", 2.0, 0.0, 1000.0),
        _nav_row("2026-04-09", 5.0, 1.5, 2500.0),
    ]
    reconstructed, unresolved = migrate.reconstruct_portfolio_nav_actual(
        nav_rows, "2026-04-09", holdings_by_date={}, ohlc_prices={}, state_by_date={},
    )
    assert len(unresolved) == 1
    assert unresolved[0][0] == "2026-04-09"
    # 원본 값이 그대로 남아있어야 한다 (재구성 실패 시 손대지 않음)
    assert reconstructed[1][2] == "1.500000"


# ── 이상치 탐지 / 보간 ────────────────────────────────────────────────────────

def test_find_outliers_flags_rows_over_threshold():
    rows = [
        _nav_row("2026-01-01", 1.0, 0.01, 100),
        _nav_row("2026-01-02", 1.5, 0.50, 150),  # 이상치
        _nav_row("2026-01-03", 1.51, 0.007, 151),
    ]
    outliers = migrate.find_outliers(rows, threshold=0.10)
    assert len(outliers) == 1
    assert outliers[0][0] == "2026-01-02"


def test_interpolate_isolated_outlier_uses_geometric_mean_of_neighbors():
    rows = [
        _nav_row("2026-01-01", 1.00, 0.0, 100),
        _nav_row("2026-01-02", 2.00, 1.0, 200),  # 고립 스파이크
        _nav_row("2026-01-03", 1.02, -0.49, 102),
    ]
    fixed = migrate.interpolate_isolated_outliers(rows, threshold=0.10)
    assert fixed == 1
    interpolated_nav = float(rows[1][1])
    assert abs(interpolated_nav - (1.00 * 1.02) ** 0.5) < 1e-6
    assert abs(float(rows[1][2])) < 0.10


def test_interpolate_skips_consecutive_outliers():
    """양옆 모두 정상이 아니면(연속 이상치) 손대지 않아야 한다."""
    rows = [
        _nav_row("2026-01-01", 1.0, 0.0, 100),
        _nav_row("2026-01-02", 2.0, 1.0, 200),
        _nav_row("2026-01-03", 4.0, 1.0, 400),
        _nav_row("2026-01-04", 4.04, 0.01, 404),
    ]
    fixed = migrate.interpolate_isolated_outliers(rows, threshold=0.10)
    assert fixed == 0


# ── circuit_state 리셋 ────────────────────────────────────────────────────────

def test_reset_circuit_state_normal_when_drawdown_small():
    rows = [_nav_row(f"2026-01-{i:02d}", 1.0 + i * 0.01, 0.01, 100) for i in range(1, 10)]
    result = migrate.reset_circuit_state(rows, {"portfolio_mdd_limit": -0.18})
    assert result["state"] == "normal"
    assert result["date"] == rows[-1][0]


def test_reset_circuit_state_defensive_when_drawdown_breaches_limit():
    rows = [
        _nav_row("2026-01-01", 2.0, 0.0, 200),
        _nav_row("2026-01-02", 1.5, -0.25, 150),  # -25% 낙폭
    ]
    result = migrate.reset_circuit_state(rows, {"portfolio_mdd_limit": -0.18})
    assert result["state"] == "defensive"
