"""전략 공통 패턴을 추출한 Mixin 클래스 모음.

각 Mixin은 단독으로 사용할 수 없으며, BaseStrategy와 함께 다중 상속으로 사용한다.
"""
from typing import ClassVar, Dict, List, Optional

from app.assets.assets import asset_groups, group_tickers
from app.indicators.sma import SMA_10M, is_above_sma


def _rank_by_score(
    assets: List[str],
    scores: Dict[str, Optional[float]],
    n: Optional[int] = None,
) -> List[str]:
    """자산 목록을 모멘텀 점수 내림차순으로 정렬, 점수 없는 자산 제외."""
    ranked = sorted(
        [t for t in assets if scores.get(t) is not None],
        key=lambda t: scores[t],  # type: ignore[index]
        reverse=True,
    )
    return ranked[:n] if n is not None else ranked


class FixedWeightMixin:
    """고정 비중 전략 공통 패턴.

    클래스 변수 WEIGHTS: Dict[str, float] 를 선언해야 한다.
    대상: Permanent, All Weather, Golden Butterfly
    """

    WEIGHTS: ClassVar[Dict[str, float]]

    def get_universe(self) -> List[str]:
        return sorted(asset_groups("fixed"))

    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        return dict(self.WEIGHTS)

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        return True


class SmaTrendMixin:
    """10개월 SMA 추세 필터 기반 균등 투자 패턴.

    offensive 그룹 자산 중 SMA 위에 있는 자산만 균등 투자하고,
    없으면 defensive[0](현금)에 100% 투자한다.
    대상: GTAA, Ivy
    """

    def get_universe(self) -> List[str]:
        return sorted(set(asset_groups("offensive") + asset_groups("defensive")))

    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        offensive = asset_groups("offensive")
        defensive = asset_groups("defensive")

        if histories:
            above = []
            for group in offensive:
                prices = None
                for ticker in group_tickers(group):
                    if ticker in histories and histories[ticker]:
                        prices = histories[ticker]
                        break
                if prices and is_above_sma(prices, SMA_10M) is True:
                    above.append(group)
        else:
            above = [g for g in offensive if scores.get(g) is not None and scores[g] > 0]

        if not above:
            return {defensive[0]: 1.0}

        weight = 1.0 / len(above)
        return {g: weight for g in above}

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        offensive = asset_groups("offensive")
        return any(scores.get(g) is not None and scores[g] > 0 for g in offensive)


class CanaryMixin:
    """카나리아 자산 기반 공격/수비 전환 패턴.

    카나리아 조건 충족 시 offensive 상위 N개에 균등 투자,
    미충족 시 defensive 1위에 100% 투자한다.
    대상: VAA, DAA, BAA-G12, BAA-G4, HAA

    클래스 변수:
        CANARY_GROUP: 카나리아로 사용할 asset_groups 키.
                      None이면 offensive 자산 전체를 카나리아로 사용 (VAA 방식).
        OFFENSIVE_SLOTS: 공격 모드에서 선택할 자산 수 (기본값 1).
    """

    CANARY_GROUP: ClassVar[Optional[str]] = None
    OFFENSIVE_SLOTS: ClassVar[int] = 1

    def _canary_ok(self, scores: Dict[str, Optional[float]]) -> bool:
        if self.CANARY_GROUP is None:
            canary = asset_groups("offensive")
        else:
            canary = asset_groups(self.CANARY_GROUP)
        return all(scores.get(t) is not None and scores[t] >= 0 for t in canary)

    def get_universe(self) -> List[str]:
        groups = asset_groups("offensive") + asset_groups("defensive")
        if self.CANARY_GROUP:
            groups += asset_groups(self.CANARY_GROUP)
        return sorted(set(groups))

    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        if self._canary_ok(scores):
            ranked = _rank_by_score(asset_groups("offensive"), scores)
            if len(ranked) < self.OFFENSIVE_SLOTS:
                raise RuntimeError(
                    f"{self.__class__.__name__}: 공격자산 모멘텀 데이터 부족"
                )
            top = ranked[: self.OFFENSIVE_SLOTS]
            w = 1.0 / len(top)
            return {t: w for t in top}

        ranked = _rank_by_score(asset_groups("defensive"), scores)
        if not ranked:
            raise RuntimeError(
                f"{self.__class__.__name__}: 수비자산 모멘텀 데이터 부족"
            )
        return {ranked[0]: 1.0}

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        return self._canary_ok(scores)


class AnnualizedReturnScoreMixin:
    """연율화 수익률 평균 모멘텀 점수 패턴.

    1·3·6·12개월 수익률을 연율화한 뒤 단순 평균을 모멘텀 점수로 사용한다.
    대상: FAA, EAA
    """

    def score_from_returns(self, returns: Dict[str, Optional[float]]) -> Optional[float]:
        """1·3·6·12개월 연율화 수익률 단순 평균."""
        annualized = [
            v * mult
            for key, mult in [("r1m", 12), ("r3m", 4), ("r6m", 2), ("r12m", 1)]
            if (v := returns.get(key)) is not None
        ]
        return sum(annualized) / len(annualized) if annualized else None

    @staticmethod
    def _load_group_prices(
        groups: List[str],
        histories: Dict[str, List[float]],
        min_len: int = 20,
    ) -> Dict[str, List[float]]:
        """그룹 목록에서 유효한 가격 시계열을 로딩한다."""
        result: Dict[str, List[float]] = {}
        for group in groups:
            for ticker in group_tickers(group):
                if ticker in histories and len(histories[ticker]) > min_len:
                    result[group] = histories[ticker]
                    break
        return result
