# Repository Guidelines

## 프로젝트 구조 및 모듈 구성
핵심 소스는 `app/` 아래에 있다. `app/strategies/`는 개별 전략 패키지, `app/data/`는 KIS/FRED/Yahoo 데이터 로더, `app/execution/`은 주문 계산과 시장 실행, `app/analytics/`는 CSV 로깅·리포트·백테스트를 담당한다. 루트 스크립트인 `run_backfill.py`, `run_collect.py`, `run_rebalance.py`, `run_selection_backtest.py`가 실제 운영 진입점이다. 생성 산출물은 `data/`, `reports/`에 커밋되며, 전략 설명과 분석 문서는 `docs/`에 둔다.

## 빌드, 테스트, 개발 명령
로컬 최소 의존성은 `pip install requests`로 설치하고, 인증 정보는 `cp key.json.example key.json`으로 준비한다.

- `python run_backfill.py`: 과거 가격을 적재하고 `data/strategy_nav.csv`를 다시 생성한다.
- `python run_selection_backtest.py --top-n 4`: 선택 기준을 고정된 전략 수로 비교한다.
- `python run_selection_backtest.py --generate-portfolio-nav`: `data/portfolio_nav.csv`를 재생성한다.
- `python run_collect.py`: 실거래 없이 일별 신호와 NAV를 갱신한다.
- `python run_rebalance.py --report-only`: 주문 없이 리포트와 선택 결과만 검증한다.
- `python run_rebalance.py`: 설정된 KIS 계좌 기준으로 실제 리밸런싱 로직을 수행한다.

## 코딩 스타일 및 네이밍 규칙
기존 Python 스타일을 따른다. 들여쓰기는 4칸, 모듈·함수·변수명은 `snake_case`를 사용한다. 복잡한 함수에만 짧은 docstring을 추가하고, 새 전략 패키지는 `app/strategies/my_strategy/`처럼 소문자 이름으로 만든다. 전략 추가 시 `app/strategies/__init__.py`의 등록 패턴을 그대로 따른다. 저장소 내부 가이드, 운영 메모, 리뷰 요약은 외부 공개 문서가 아니라면 한글로 작성한다.

## 테스트 가이드
현재 전용 `tests/` 디렉터리는 없다. 변경한 기능은 관련 스크립트를 직접 실행해 검증하고, 결과 CSV와 리포트가 `data/`, `reports/`에 의도대로 반영되는지 확인한다. 전략 선택 로직을 바꿨다면 `python run_selection_backtest.py --full` 또는 `--top-n`으로 확인하고, 실거래 경로에 닿는 수정은 가능하면 `python run_rebalance.py --report-only`로 먼저 점검한다. PR에는 수동 검증 범위를 짧게 남긴다.

## 커밋 및 PR 규칙
최근 커밋은 `리팩토링 및 분석으로 찾은 버그 수정`처럼 짧고 직접적인 요약 형태가 많다. 한 커밋에는 한 가지 논리적 변경만 담고, 메시지는 명령형으로 간결하게 쓴다. PR에는 운영 영향, 변경된 설정값이나 Secret 여부, 수동 검증 내용, 출력 형식이 바뀐 경우 리포트 경로나 스크린샷을 포함한다. 관련 이슈가 있으면 링크한다.

## 보안 및 설정 주의사항
`key.json`은 커밋하지 않는다. 소스에는 `key.json.example`만 유지한다. 운영 자동화는 `KIS_KEY_JSON`과 선택적 `CONFIG_JSON` GitHub Secret에 의존하므로, 문서 작성 시에도 이를 기준으로 설명한다. `data/`와 `reports/`는 운영 기록으로 취급하고, 과거 산출물 복구 작업이 아닌 한 수동 편집을 피한다.
