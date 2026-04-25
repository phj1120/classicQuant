"""전략 선택 알고리즘 회귀 테스트.

_apply_corr_filter, _corr 함수의 순수 로직을 검증한다.
외부 API 없이 인메모리 데이터만 사용한다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import pytest
from app.strategy_selector import _apply_corr_filter, _corr


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _make_nav_series(returns):
    """일별 수익률 리스트로 all_nav 포맷의 딕셔너리 생성.

    _apply_corr_filter 내부에서 row["daily_return"] 키로 접근한다.
    """
    return [{"daily_return": str(r)} for r in returns]


def _make_all_nav(name_returns: dict):
    """전략별 수익률 딕셔너리 → all_nav 포맷 딕셔너리 생성."""
    return {name: _make_nav_series(rets) for name, rets in name_returns.items()}


# ── _apply_corr_filter 테스트 ─────────────────────────────────────────────────

def test_corr_filter_high_corr_selects_one(monkeypatch):
    """상관도 0.9(높음) 전략 쌍 → top_n=2일 때 1개만 선택."""
    # 63일치 동일한 방향의 수익률 생성 → 상관도 ≈ 1.0
    n = 63
    base = [0.01 * (i % 2 == 0) - 0.005 for i in range(n)]
    # strategy_b는 base와 거의 동일 (노이즈 없음)
    all_nav = _make_all_nav({
        "strategy_a": base,
        "strategy_b": base,  # 완전 동일 → corr = 1.0
    })
    ranked = [("strategy_a", 0.9), ("strategy_b", 0.8)]
    result = _apply_corr_filter(ranked, all_nav, top_n=2, corr_threshold=0.7)
    assert len(result) == 1, f"높은 상관도에서 {len(result)}개 선택됨 (기대: 1)"
    assert result[0][0] == "strategy_a"


def test_corr_filter_low_corr_selects_two(monkeypatch):
    """상관도 0.3(낮음) 전략 쌍 → top_n=2일 때 2개 선택."""
    n = 63
    # strategy_a: 교번 수익률
    returns_a = [0.01 if i % 2 == 0 else -0.01 for i in range(n)]
    # strategy_b: 랜덤하게 독립적인 패턴 (a와 무관)
    # 단순히 4단계 주기로 다른 패턴을 만들어 상관도를 낮춤
    returns_b = [0.01 if i % 7 < 3 else -0.008 for i in range(n)]

    all_nav = _make_all_nav({
        "strategy_a": returns_a,
        "strategy_b": returns_b,
    })
    # 실제 상관도가 0.7 미만인지 확인
    actual_corr = _corr(returns_a, returns_b, n)
    assert actual_corr is not None
    assert abs(actual_corr) < 0.7, f"테스트 데이터의 상관도({actual_corr:.3f})가 0.7 이상 — 테스트 데이터를 수정해야 함"

    ranked = [("strategy_a", 0.9), ("strategy_b", 0.8)]
    result = _apply_corr_filter(ranked, all_nav, top_n=2, corr_threshold=0.7)
    assert len(result) == 2, f"낮은 상관도에서 {len(result)}개 선택됨 (기대: 2)"


def test_corr_filter_empty_ranked_returns_empty():
    """ranked가 빈 리스트 → 빈 리스트 반환."""
    all_nav = {}
    result = _apply_corr_filter([], all_nav, top_n=2)
    assert result == []


# ── _corr 테스트 ──────────────────────────────────────────────────────────────

def test_corr_identical_series_is_one():
    """동일한 리스트 두 개 → 상관도 ≈ 1.0."""
    data = [0.01, -0.02, 0.015, -0.005, 0.008] * 15  # 75개 (window=63 초과)
    result = _corr(data, data, window=63)
    assert result is not None
    assert abs(result - 1.0) < 1e-9, f"동일 시리즈 상관도: {result}"


def test_corr_opposite_series_is_minus_one():
    """완전 반대 리스트 → 상관도 ≈ -1.0."""
    base = [0.01, -0.02, 0.015, -0.005, 0.008] * 15  # 75개
    opposite = [-x for x in base]
    result = _corr(base, opposite, window=63)
    assert result is not None
    assert abs(result - (-1.0)) < 1e-9, f"반대 시리즈 상관도: {result}"


def test_corr_returns_none_when_too_short():
    """데이터가 window보다 짧으면 None 반환."""
    short = [0.01, 0.02, 0.03]
    result = _corr(short, short, window=63)
    assert result is None
