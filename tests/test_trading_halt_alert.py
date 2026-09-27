"""매매 중단 알림(GITHUB_ENV 전달, 리포트 경고) 회귀 테스트.

2026-08~09 NAV 기록 거부가 약 2개월간 조용히 지나간 재발을 막기 위한 장치다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run_rebalance
from app.analytics.report import write_report


def test_flag_trading_halt_writes_github_env(tmp_path, monkeypatch):
    env_file = tmp_path / "github_env"
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    run_rebalance._flag_trading_halt("2026-09-28 NAV sanity gate 거부로 매매 중단 (총자산 $0.00)")
    assert env_file.read_text(encoding="utf-8") == "TRADING_HALTED=2026-09-28 NAV sanity gate 거부로 매매 중단 (총자산 $0.00)\n"


def test_flag_trading_halt_is_noop_outside_actions(monkeypatch):
    monkeypatch.delenv("GITHUB_ENV", raising=False)
    run_rebalance._flag_trading_halt("무시됨")  # 예외 없이 끝나야 한다


def test_report_shows_alert_below_title(tmp_path):
    result = {"name": "permanent", "weight": 1.0, "scores": {}, "targets": {}, "selected_tickers": {}}
    path = write_report([result], tmp_path, alerts=["NAV 기록 거부"])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# PERMANENT(100%) Daily Report")
    assert lines[2] == "> ⛔ **NAV 기록 거부**"
