"""csv_logger의 헤더 정합성·날짜 정규화·중복 제거 회귀 테스트.

실제 data/ 디렉터리를 건드리지 않도록 각 테스트에서 모듈 경로 상수를
tmp_path 파일로 monkeypatch 한다.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.analytics import csv_logger


@pytest.fixture
def portfolio_state_csv(tmp_path, monkeypatch):
    path = tmp_path / "portfolio_state.csv"
    monkeypatch.setattr(csv_logger, "PORTFOLIO_STATE_CSV", path)
    return path


@pytest.fixture
def portfolio_nav_actual_csv(tmp_path, monkeypatch):
    path = tmp_path / "portfolio_nav_actual.csv"
    monkeypatch.setattr(csv_logger, "PORTFOLIO_NAV_ACTUAL_CSV", path)
    # 레거시 마이그레이션이 실제 data/portfolio_nav.csv를 끌어오지 않도록 차단
    monkeypatch.setattr(csv_logger, "PORTFOLIO_NAV_LEGACY_CSV", tmp_path / "portfolio_nav_legacy_absent.csv")
    return path


@pytest.fixture
def cash_flows_csv(tmp_path, monkeypatch):
    path = tmp_path / "cash_flows.csv"
    monkeypatch.setattr(csv_logger, "CASH_FLOWS_CSV", path)
    return path


def test_append_rows_rejects_mismatched_header(tmp_path):
    """파일에 이미 다른(구버전) 헤더가 있으면 RuntimeError로 즉시 실패해야 한다."""
    path = tmp_path / "legacy.csv"
    path.write_text("date,nav,daily_return,total_equity\n2026-01-01,1.0,0.0,100.0\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        csv_logger._append_rows(
            path,
            ["date", "nav", "daily_return", "total_equity", "fx_rate", "krw_nav"],
            [["2026-01-02", "1.01", "0.01", "101.0", "1300.0", "131300.0"]],
        )


def test_append_rows_writes_header_for_new_file(tmp_path):
    path = tmp_path / "fresh.csv"
    csv_logger._append_rows(path, ["a", "b"], [["1", "2"]])
    content = path.read_text(encoding="utf-8").splitlines()
    assert content[0] == "a,b"
    assert content[1] == "1,2"


def test_save_portfolio_state_normalizes_date(portfolio_state_csv):
    """YYYYMMDD로 넘어와도 파일에는 YYYY-MM-DD로 기록되어야 한다."""
    csv_logger.save_portfolio_state("20260316", 1000.0, 500.0)
    content = portfolio_state_csv.read_text(encoding="utf-8")
    assert "2026-03-16" in content
    assert "20260316" not in content


def test_save_portfolio_state_dedupes_mixed_date_formats(portfolio_state_csv):
    """같은 날짜를 YYYYMMDD와 YYYY-MM-DD로 각각 저장해도 한 행만 남아야 한다."""
    csv_logger.save_portfolio_state("20260316", 1000.0, 500.0)
    csv_logger.save_portfolio_state("2026-03-16", 2000.0, 900.0)
    rows = csv_logger.load_portfolio_state()
    assert len(rows) == 1
    assert rows[0]["total_equity"] == "1000.00"  # 첫 기록 유지 (재실행 시 덮어쓰지 않음)


def test_save_portfolio_nav_actual_rejects_duplicate_date(portfolio_nav_actual_csv):
    csv_logger.save_portfolio_nav_actual("2026-07-27", 1.5, 0.01, total_equity=1000.0)
    csv_logger.save_portfolio_nav_actual("2026-07-27", 99.0, 9.0, total_equity=99999.0)
    rows = csv_logger.load_portfolio_nav_actual()
    assert len(rows) == 1
    assert rows[0]["nav"] == "1.500000"


def test_load_cash_flows_sums_same_day_entries(cash_flows_csv):
    cash_flows_csv.write_text(
        "date,amount_usd,memo\n"
        "2026-07-01,500,입금1\n"
        "2026-07-01,-100,수수료환급\n"
        "2026-07-02,1000,입금2\n",
        encoding="utf-8",
    )
    flows = csv_logger.load_cash_flows()
    assert flows["2026-07-01"] == 400.0
    assert flows["2026-07-02"] == 1000.0


def test_load_cash_flows_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(csv_logger, "CASH_FLOWS_CSV", tmp_path / "nonexistent.csv")
    assert csv_logger.load_cash_flows() == {}
