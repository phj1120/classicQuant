from pathlib import Path
from typing import Dict, Type

from app.strategy import BaseStrategy

_REGISTRY: Dict[str, Type[BaseStrategy]] = {}


def register(name: str):
    """전략 클래스를 레지스트리에 등록하는 데코레이터."""
    def decorator(cls: Type[BaseStrategy]):
        _REGISTRY[name] = cls
        return cls
    return decorator


def get_strategy(name: str, assets_file: Path | None = None) -> BaseStrategy:
    """이름으로 전략 인스턴스를 생성하여 반환한다."""
    if name not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys()) or "(없음)"
        raise ValueError(f"알 수 없는 전략: '{name}'. 사용 가능: {available}")
    return _REGISTRY[name](assets_file=assets_file)


# 전략 모듈을 임포트하여 @register 데코레이터가 실행되도록 한다.
from app.strategies import daa as _daa  # noqa: F401, E402
from app.strategies import vaa as _vaa  # noqa: F401, E402
