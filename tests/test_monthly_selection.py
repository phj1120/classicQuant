"""월간 전략 선택 게이트(run_rebalance._select_or_reuse_active_strategies) 회귀 테스트.

매일 재선택하면 랭킹 경계의 미세 변동으로도 조합이 바뀌어 회전 비용이
알파를 잠식한다(114거래일 중 33회 교체 관측). 월 1회만 재선택하고,
보유 전략이 MDD 필터에 걸리면 즉시 재선택하는 탈출 조건을 검증한다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import run_rebalance
from app.analytics import selection_state


@pytest.fixture(autouse=True)
def isolate_state_file(tmp_path, monkeypatch):
    monkeypatch.setattr(selection_state, "STATE_FILE", tmp_path / "selection_state.json")


def _stub_select(entries=None, calls=None):
    result = entries or [{"name": "daa", "weight": 0.5}, {"name": "gem", "weight": 0.5}]

    def _select(strategy_entries, strategies, scores_by_strategy, selection_cfg):
        if calls is not None:
            calls.append(1)
        return result
    return _select


def test_daily_mode_always_reselects(monkeypatch):
    calls = []
    monkeypatch.setattr(run_rebalance, "select_active_strategies", _stub_select(calls=calls))
    cfg = {"rebalance_frequency": "daily"}

    for day in ("2026-08-01", "2026-08-02"):
        run_rebalance._select_or_reuse_active_strategies([], {}, {}, cfg, day)

    assert len(calls) == 2


def test_monthly_mode_first_call_selects_and_persists(monkeypatch):
    calls = []
    entries = [{"name": "laa", "weight": 1.0}]
    monkeypatch.setattr(run_rebalance, "select_active_strategies", _stub_select(entries, calls))
    monkeypatch.setattr(run_rebalance, "is_strategy_mdd_excluded", lambda *a, **k: False)
    cfg = {"rebalance_frequency": "monthly"}

    result = run_rebalance._select_or_reuse_active_strategies(
        [], {"laa": object()}, {}, cfg, "2026-08-03",
    )
    assert result == entries
    assert len(calls) == 1

    state = selection_state.load_selection_state()
    assert state["selected_month"] == "2026-08"
    assert state["selected"] == entries


def test_monthly_mode_reuses_within_same_month(monkeypatch):
    calls = []
    entries = [{"name": "laa", "weight": 1.0}]
    monkeypatch.setattr(run_rebalance, "select_active_strategies", _stub_select(entries, calls))
    monkeypatch.setattr(run_rebalance, "is_strategy_mdd_excluded", lambda *a, **k: False)
    cfg = {"rebalance_frequency": "monthly"}

    run_rebalance._select_or_reuse_active_strategies([], {"laa": object()}, {}, cfg, "2026-08-03")
    result = run_rebalance._select_or_reuse_active_strategies(
        [], {"laa": object()}, {}, cfg, "2026-08-15",
    )

    assert result == entries
    assert len(calls) == 1, "같은 달 안에서는 재선택이 호출되지 않아야 한다"


def test_monthly_mode_reselects_on_new_month(monkeypatch):
    calls = []
    entries = [{"name": "laa", "weight": 1.0}]
    monkeypatch.setattr(run_rebalance, "select_active_strategies", _stub_select(entries, calls))
    monkeypatch.setattr(run_rebalance, "is_strategy_mdd_excluded", lambda *a, **k: False)
    cfg = {"rebalance_frequency": "monthly"}

    run_rebalance._select_or_reuse_active_strategies([], {"laa": object()}, {}, cfg, "2026-08-03")
    run_rebalance._select_or_reuse_active_strategies([], {"laa": object()}, {}, cfg, "2026-09-01")

    assert len(calls) == 2, "달이 바뀌면 다시 재선택해야 한다"


def test_monthly_mode_escapes_early_on_mdd_exclusion(monkeypatch):
    """월중이라도 보유 전략이 MDD 필터에 걸리면 즉시 재선택해야 한다."""
    calls = []
    entries = [{"name": "laa", "weight": 1.0}]
    monkeypatch.setattr(run_rebalance, "select_active_strategies", _stub_select(entries, calls))
    cfg = {"rebalance_frequency": "monthly"}

    run_rebalance._select_or_reuse_active_strategies([], {"laa": object()}, {}, cfg, "2026-08-03")
    assert len(calls) == 1

    # 같은 달 안이지만 laa가 이제 MDD 필터에 걸림
    monkeypatch.setattr(run_rebalance, "is_strategy_mdd_excluded", lambda *a, **k: True)
    run_rebalance._select_or_reuse_active_strategies([], {"laa": object()}, {}, cfg, "2026-08-15")

    assert len(calls) == 2, "MDD 탈락 시 정기 재선택을 기다리지 않고 즉시 재선택해야 한다"
