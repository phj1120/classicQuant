from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional


class BaseStrategy(ABC):
    """퀀트 전략의 추상 베이스 클래스."""

    def __init__(self, assets_file: Path | None = None):
        self._assets_file = assets_file

    @property
    def assets_file(self) -> Path:
        """전략이 사용할 assets.json 경로. 지정하지 않으면 기본 경로."""
        if self._assets_file:
            return self._assets_file
        return Path(__file__).resolve().parent / "strategies" / "daa" / "assets.json"

    @abstractmethod
    def get_universe(self) -> List[str]:
        """전략에 필요한 전체 자산 그룹 목록을 반환한다."""

    @abstractmethod
    def select_targets(
        self, scores: Dict[str, Optional[float]]
    ) -> Dict[str, float]:
        """모멘텀 점수를 기반으로 목표 포트폴리오(그룹→비중)를 반환한다."""

    def is_offensive(self, scores: Dict[str, Optional[float]]) -> bool:
        """offensive_mode 기준용: 현재 공격자산에 투자 중인지 여부.

        기본 구현은 select_targets() 결과가 offensive 그룹에 속하는지 확인.
        정적 전략(Permanent, All Weather)은 True를 반환하도록 오버라이드.
        """
        from app.assets import asset_groups
        targets = self.select_targets(scores)
        offensive = set(asset_groups("offensive"))
        return any(t in offensive for t in targets)
