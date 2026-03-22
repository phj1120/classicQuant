from abc import ABC, abstractmethod
from typing import ClassVar, Dict, List, Optional


class BaseStrategy(ABC):
    """퀀트 전략의 추상 베이스 클래스."""

    ASSETS: ClassVar[Dict]

    @property
    def assets(self) -> Dict:
        """전략이 사용하는 자산 그룹 정의."""
        return self.__class__.ASSETS

    def get_universe(self) -> List[str]:
        """전략에 필요한 전체 자산 그룹 목록을 반환한다.

        기본 구현: ASSETS의 모든 그룹을 합쳐 정렬하여 반환한다.
        커스텀 로직이 필요한 전략은 오버라이드한다.
        """
        from app.assets.assets import asset_groups
        all_tickers: List[str] = []
        for asset_type in self.assets:
            all_tickers += asset_groups(asset_type)
        return sorted(set(all_tickers))

    @abstractmethod
    def select_targets(
        self,
        scores: Dict[str, Optional[float]],
        histories: Dict[str, List[float]] | None = None,
    ) -> Dict[str, float]:
        """모멘텀 점수를 기반으로 목표 포트폴리오(그룹→비중)를 반환한다.

        Args:
            scores: 그룹별 모멘텀 점수 (전략별 score_from_returns로 계산)
            histories: 티커별 파싱된 가격 시계열 (SMA·변동성·상관관계 계산용)
        """

    def score_from_returns(self, returns: Dict[str, Optional[float]]) -> Optional[float]:
        """raw returns → 모멘텀 점수 변환. 기본은 Keller 복합 공식.

        전략별로 오버라이드하여 고유 공식을 사용할 수 있다.
        """
        r1 = returns.get("r1m")
        r3 = returns.get("r3m")
        r6 = returns.get("r6m")
        r12 = returns.get("r12m")
        if None in (r1, r3, r6, r12):
            return None
        return (r1 * 12) + (r3 * 4) + (r6 * 2) + r12

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        """offensive_mode 기준용: 현재 공격자산에 투자 중인지 여부.

        기본 구현은 select_targets() 결과가 offensive 그룹에 속하는지 확인.
        정적 전략(Permanent, All Weather)은 True를 반환하도록 오버라이드.
        """
        from app.assets.assets import asset_groups
        targets = self.select_targets(scores)
        offensive = set(asset_groups("offensive"))
        return any(t in offensive for t in targets)

    @staticmethod
    def _rank_by_score(
        assets: List[str],
        scores: Dict[str, Optional[float]],
        n: Optional[int] = None,
    ) -> List[str]:
        """자산 목록을 모멘텀 점수 내림차순으로 정렬, 점수 없는 자산 제외.

        Args:
            assets: 정렬할 자산 그룹 목록
            scores: 그룹별 모멘텀 점수
            n: 상위 N개만 반환 (None이면 전체)
        """
        ranked = sorted(
            [t for t in assets if scores.get(t) is not None],
            key=lambda t: scores[t],  # type: ignore[index]
            reverse=True,
        )
        return ranked[:n] if n is not None else ranked

    @staticmethod
    def _load_group_prices(
        groups: List[str],
        histories: Dict[str, List[float]],
        min_len: int = 20,
    ) -> Dict[str, List[float]]:
        """그룹 목록에서 유효한 가격 시계열을 로딩한다.

        각 그룹의 티커 중 histories에 존재하고 min_len 이상인 첫 번째를 사용한다.
        """
        from app.assets.assets import group_tickers
        result: Dict[str, List[float]] = {}
        for group in groups:
            for ticker in group_tickers(group):
                if ticker in histories and len(histories[ticker]) > min_len:
                    result[group] = histories[ticker]
                    break
        return result
