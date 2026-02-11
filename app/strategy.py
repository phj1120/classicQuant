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
