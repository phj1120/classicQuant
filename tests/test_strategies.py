"""전략 로직 회귀 테스트.

각 테스트는 외부 API 없이 순수 로직만 검증한다.
전략의 select_targets() 호출 전에 반드시 reload_assets()로 해당 전략의
ASSETS 캐시를 초기화해야 한다.
"""
import sys
import os

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.assets.assets import reload_assets
import app.strategies  # noqa: F401 — 등록 트리거


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _make_scores(groups, value):
    """모든 그룹에 동일한 점수를 부여한 딕셔너리 생성."""
    return {g: value for g in groups}


# ── 1. 레지스트리 ─────────────────────────────────────────────────────────────

EXPECTED_STRATEGIES = {
    "daa", "vaa", "paa", "baa_g12", "baa_g4",
    "gem", "haa", "permanent", "all_weather", "golden_butterfly",
    "gtaa", "ivy", "faa", "eaa", "laa",
}


def test_registry_has_15_strategies():
    """레지스트리에 15개 전략이 모두 등록되어 있어야 한다."""
    from app.strategies import _REGISTRY
    assert len(_REGISTRY) == 15, f"등록된 전략 수: {len(_REGISTRY)}, 기대: 15. 현재: {set(_REGISTRY.keys())}"
    assert _REGISTRY.keys() == EXPECTED_STRATEGIES


# ── 2. VAA ────────────────────────────────────────────────────────────────────

def test_vaa_defensive_when_any_offensive_negative():
    """VAA: offensive 자산 중 하나라도 score < 0이면 defensive 100% 반환."""
    from app.strategies import get_strategy
    vaa = get_strategy("vaa")
    reload_assets(vaa.ASSETS)

    # SPY는 양수, 나머지는 모두 양수지만 EEM이 음수
    scores = {
        "SPY": 0.5,
        "EFA": 0.3,
        "EEM": -0.1,  # 음수
        "AGG": 0.2,
        "LQD": 0.4,
        "IEF": 0.3,
        "SHY": 0.1,
    }
    targets = vaa.select_targets(scores)

    # 결과가 수비 자산(LQD/IEF/SHY 중 하나)에 100%여야 한다
    assert len(targets) == 1
    assert abs(sum(targets.values()) - 1.0) < 1e-9
    winning_group = list(targets.keys())[0]
    from app.assets.assets import asset_groups
    defensive_groups = asset_groups("defensive")
    assert winning_group in defensive_groups, f"수비 모드에서 공격 자산 선택됨: {winning_group}"


def test_vaa_offensive_when_all_scores_positive():
    """VAA: offensive 자산 모두 score > 0이면 offensive 1위에 100% 반환."""
    from app.strategies import get_strategy
    vaa = get_strategy("vaa")
    reload_assets(vaa.ASSETS)

    scores = {
        "SPY": 0.5,
        "EFA": 0.3,
        "EEM": 0.2,
        "AGG": 0.4,
        "LQD": 0.1,
        "IEF": 0.15,
        "SHY": 0.05,
    }
    targets = vaa.select_targets(scores)

    assert len(targets) == 1
    assert abs(sum(targets.values()) - 1.0) < 1e-9
    winning_group = list(targets.keys())[0]
    from app.assets.assets import asset_groups
    offensive_groups = asset_groups("offensive")
    assert winning_group in offensive_groups, f"공격 모드에서 수비 자산 선택됨: {winning_group}"
    # SPY가 점수 1위이므로 SPY가 선택되어야 한다
    assert winning_group == "SPY"


# ── 3. Permanent ──────────────────────────────────────────────────────────────

def test_permanent_weights_sum_to_one():
    """Permanent: select_targets() 반환 가중치 합 = 1.0."""
    from app.strategies import get_strategy
    permanent = get_strategy("permanent")
    reload_assets(permanent.ASSETS)

    targets = permanent.select_targets({})
    total = sum(targets.values())
    assert abs(total - 1.0) < 1e-9, f"가중치 합: {total}"


# ── 4. 임의 전략 3개 가중치 합 검증 ───────────────────────────────────────────

def _check_weights_sum_to_one(strategy_name: str, scores: dict):
    """전략의 select_targets() 결과 가중치 합이 1.0(±0.001)인지 검증."""
    from app.strategies import get_strategy
    strategy = get_strategy(strategy_name)
    reload_assets(strategy.ASSETS)
    targets = strategy.select_targets(scores)
    total = sum(targets.values())
    assert abs(total - 1.0) < 0.001, (
        f"{strategy_name}: 가중치 합 = {total:.6f} (기대: 1.0±0.001)"
    )


def test_gem_weights_sum_to_one():
    """GEM: select_targets() 가중치 합 = 1.0."""
    from app.strategies import get_strategy
    gem = get_strategy("gem")
    reload_assets(gem.ASSETS)
    scores = {
        "SPY": 0.4,
        "EFA": 0.2,
        "AGG": 0.1,
    }
    _check_weights_sum_to_one("gem", scores)


def test_paa_weights_sum_to_one():
    """PAA: 일부 공격자산이 음수일 때도 가중치 합 = 1.0."""
    from app.strategies import get_strategy
    paa = get_strategy("paa")
    reload_assets(paa.ASSETS)
    # 12개 공격자산 중 6개 음수, 6개 양수 (균등 분할)
    offensive_groups = ["SPY", "IWM", "QQQ", "VGK", "EWJ", "EEM", "VNQ", "DBC", "GLD", "TLT", "HYG", "LQD"]
    defensive_groups = ["SHY", "IEF"]
    scores = {}
    for i, g in enumerate(offensive_groups):
        scores[g] = 0.1 if i < 6 else -0.1
    for g in defensive_groups:
        scores[g] = 0.05
    _check_weights_sum_to_one("paa", scores)


def test_daa_weights_sum_to_one():
    """DAA: 카나리아 자산 모두 양수 → 공격 모드 가중치 합 = 1.0."""
    from app.strategies import get_strategy
    daa = get_strategy("daa")
    reload_assets(daa.ASSETS)
    # 카나리아(VWO, BND) 양수, 공격자산도 양수
    scores = {
        "SPY": 0.5, "IWM": 0.4, "QQQ": 0.45, "VGK": 0.3, "EWJ": 0.2,
        "EEM": 0.25, "VNQ": 0.35, "DBC": 0.1, "GLD": 0.15, "TLT": 0.2,
        "HYG": 0.3, "LQD": 0.28,
        "SHY": 0.05, "IEF": 0.1,
        "VWO": 0.2, "BND": 0.1,
    }
    _check_weights_sum_to_one("daa", scores)


def test_all_weather_weights_sum_to_one():
    """All Weather: select_targets() 가중치 합 = 1.0."""
    from app.strategies import get_strategy
    all_weather = get_strategy("all_weather")
    reload_assets(all_weather.ASSETS)
    targets = all_weather.select_targets({})
    total = sum(targets.values())
    assert abs(total - 1.0) < 0.001, f"가중치 합: {total}"
