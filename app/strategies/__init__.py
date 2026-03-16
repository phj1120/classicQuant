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
from app.strategies import paa as _paa  # noqa: F401, E402
from app.strategies import baa_g12 as _baa_g12  # noqa: F401, E402
from app.strategies import baa_g4 as _baa_g4  # noqa: F401, E402
from app.strategies import gem as _gem  # noqa: F401, E402
from app.strategies import haa as _haa  # noqa: F401, E402
from app.strategies import permanent as _permanent  # noqa: F401, E402
from app.strategies import all_weather as _all_weather  # noqa: F401, E402
from app.strategies import golden_butterfly as _golden_butterfly  # noqa: F401, E402
from app.strategies import gtaa as _gtaa  # noqa: F401, E402
from app.strategies import ivy as _ivy  # noqa: F401, E402
from app.strategies import faa as _faa  # noqa: F401, E402
from app.strategies import eaa as _eaa  # noqa: F401, E402
from app.strategies import laa as _laa  # noqa: F401, E402
