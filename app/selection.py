"""하위 호환을 위한 래퍼. 새 코드에서는 app.strategies를 직접 사용하세요."""
from app.strategies.daa import DAAStrategy

_strategy = DAAStrategy()


def select_targets(scores):
    return _strategy.select_targets(scores)
