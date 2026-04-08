# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

classicQuant는 15개의 클래식 퀀트 전략을 매일 추적하고, 상관관계 기반 분산 선택으로 최적 전략 조합에 자동 리밸런싱하는 시스템입니다. KIS API(한국투자증권)를 통해 실거래를 수행하며, GitHub Actions로 운용됩니다.

## Commands

### 로컬 실행
```bash
pip install requests
cp key.json.example key.json   # API 키 입력

# 최초 1회: 과거 NAV 데이터 생성
python run_backfill.py

# 최초 1회: 모델 포트폴리오 NAV 백필 (설정 검증용)
python run_selection_backtest.py --generate-portfolio-nav

# 매일: 신호 + NAV 수집 (매매 없음)
python run_collect.py

# 리포트만 생성 (매매 없음, 키가 없으면 offline 캐시 모드)
python run_rebalance.py --report-only

# 리밸런싱 실행 (실제 매매 발생)
python run_rebalance.py
```

### 백테스트
```bash
python run_selection_backtest.py --top-n 4     # 기준별 성과 비교
python run_selection_backtest.py --robust-n    # 다기준 합의 기반 top_n 분석
python run_selection_backtest.py --sweep       # top_n 1~15 Sharpe 히트맵
python run_selection_backtest.py --full        # 전체 조합 파레토 분석
```

## Architecture

### 실행 흐름
```
run_backfill.py       → 과거 가격 수집 → NAV 히스토리 생성
run_collect.py        → 전략 신호 계산 + NAV 업데이트 (잔고 조회 없음)
run_rebalance.py      → 전략 선택 → 포트폴리오 주문 생성 → KIS API 실행
```

### 패키지 구조

`app/` 내부는 서브패키지로 구성됩니다:

| 서브패키지 | 주요 모듈 | 역할 |
|---|---|---|
| `app/assets/` | `assets.py`, `groups.py`, `ticker.py` | 자산 캐시, 그룹 조회, ETF 티커 정의 |
| `app/data/` | `kis_api.py`, `data_utils.py`, `fred_api.py`, `yfinance_loader.py` | 외부 데이터 소스 |
| `app/indicators/` | `momentum.py`, `sma.py`, `factor.py` | 기술 지표 계산 |
| `app/execution/` | `portfolio.py`, `exchange.py`, `market.py` | 주문 생성·실행 |
| `app/analytics/` | `csv_logger.py`, `report.py`, `backtest.py` | 로깅·리포트·백테스트 |
| `app/strategies/` | 15개 전략 서브패키지 | 각 전략 구현체 |

루트에 남는 모듈: `app/strategy.py`, `app/strategy_selector.py`, `app/config.py`, `app/constants.py`, `app/selection.py`

### 핵심 추상화 계층

**전략 레이어** (`app/strategies/`)
- `BaseStrategy` (`app/strategy.py`): 추상 클래스. 모든 전략이 상속
  - `get_universe()`: 전략에 필요한 자산 목록 반환
  - `select_targets(scores, histories)`: 모멘텀 점수 → 목표 포트폴리오(그룹→비중) 반환
  - `score_from_returns(returns)`: 기본 Keller 복합 공식 `(r1m×12 + r3m×4 + r6m×2 + r12m)`. 전략별 오버라이드 가능
- 전략 등록: `@register("name")` 데코레이터로 `_REGISTRY`에 자동 등록
- `app/strategies/__init__.py` 하단에 import를 추가해야 등록됨

**자산 관리** (`app/assets/`)
- `Ticker` (str Enum, `app/assets/ticker.py`): 모든 ETF 티커 정의. 각 티커는 거래소, 설명, 대체 티커(alternative chain) 보유
  - 예: `TLT → EDV → SPTL` (주자산 → 저가 대체자산 체인)
- `app/assets/assets.py`: 전략의 `ASSETS` 딕셔너리를 파싱하여 캐시 구축
  - `reload_assets(data)` / `merge_assets(asset_dicts)`: 캐시 초기화
  - `app/assets/groups.py`: `asset_groups(type)` 타입별 그룹 반환 (`"offensive"`, `"defensive"`, `"canary"`, `"fixed"` 등)
- 각 전략의 `ASSETS`는 `Ticker` enum 값 리스트로 정의. 실행 시 `reload_assets()`로 캐시에 로드됨

**전략 선택** (`app/strategy_selector.py`)
- `corr_constrained` (권장): sharpe_12m 랭킹 후 상관관계 0.7 이상 전략 제외하여 top_n 선택
- 포트폴리오 MDD 서킷 브레이커: `data/portfolio_nav_actual.csv` 기준, 한계 초과 시 fallback_strategy로 강제 전환

**포트폴리오 실행** (`app/execution/portfolio.py`)
- `build_group_orders()`: 목표 비중 → 매수/매도 주문 생성 (priority 1 티커 → 예산 부족 시 alternative chain으로 폴백)
- `execute_orders()`: KIS API로 주문 실행
- 예비자산 승격: 예비자산 합산가치 ≥ 주자산 1주 가격이면 매도 후 주자산 매수

### 설정

**`config.json`** (또는 GitHub Secret `CONFIG_JSON`):
- `strategies`: 추적할 전략 목록
- `selection`: 전략 선택 기준(`criteria`, `top_n`, `mdd_filter_threshold`, `portfolio_mdd_limit`, `fallback_strategy`)
- `strategy`: 리밸런싱 임계값(`rebalance_threshold_pct`), 현금 버퍼(`cash_buffer_pct`), 최소 매매금액(`min_trade_value_usd`)

**`key.json`** (또는 GitHub Secret `KIS_KEY_JSON`):
- `app_key`, `app_secret`, `account_number`, `account_code`

### 데이터 파일 (`data/`)
- `ohlc_history.csv`: 자산 가격 히스토리 (백필/수집 결과)
- `strategy_nav.csv`: 전략별 NAV 누적 (전략 선택 기준 계산에 사용)
- `portfolio_nav_model.csv`: 모델 포트폴리오 NAV (설정 검증/리서치용)
- `portfolio_nav_actual.csv`: 실제 포트폴리오 NAV (실전 MDD 서킷 브레이커용)
- `portfolio_state.csv`: 실제 총자산/현금 스냅샷
- `portfolio_nav.csv`: 레거시 포맷, actual NAV 이관 호환용
- `strategy_signals.csv`: 일별 전략 신호

### GitHub Actions 브랜치 전략
- `main`: 소스 코드
- `trading`: `main` 리베이스 + 일별 reports/, data/ 커밋
- 스케줄/main 실행 → 실제 매매 → trading 브랜치에 커밋
- 그 외 브랜치(예: dev) 수동 실행 → `--report-only` (매매 없음)

## 새 전략 추가

1. `app/strategies/{name}/` 디렉터리 생성
2. `__init__.py`에 `BaseStrategy` 상속 + `@register("{name}")` 데코레이터
3. `ASSETS` 클래스 변수에 `Ticker` enum 값 리스트로 자산 정의
4. `app/strategies/__init__.py` 하단에 `from app.strategies import {name} as _{name}` 추가
5. `config.json`의 `strategies` 배열에 추가

시그널 유형별 구현 패턴:
- 모멘텀 점수: `scores` 딕셔너리 사용 (VAA, DAA, GEM 등)
- SMA 추세: `app/indicators/sma.py` + `histories` (GTAA, Ivy, LAA)
- 변동성/상관관계: `app/indicators/factor.py` + `histories` (FAA, EAA)
- 거시경제 지표: `app/data/fred_api.py` (LAA)
- 정적 배분: 고정 비중 딕셔너리 반환 (Permanent, All Weather)

## 코딩 스타일

- 들여쓰기: 4칸, 모듈·함수·변수명: `snake_case`
- 복잡한 함수에만 짧은 docstring 추가
- 저장소 내부 가이드, 운영 메모, 리뷰 요약 등 내부 문서는 한국어로 작성하고 최신화 유지

## 테스트

전용 `tests/` 디렉터리 없음. 변경한 기능은 관련 스크립트를 직접 실행해 검증:
- 전략 선택 로직 변경 → `python run_selection_backtest.py --full` 또는 `--top-n`
- 실거래 경로에 닿는 수정 → `python run_rebalance.py --report-only`로 먼저 점검
- 결과 CSV와 리포트가 `data/`, `reports/`에 의도대로 반영되는지 확인

## 커밋 및 PR

- 한 커밋에 하나의 논리적 변경, 메시지는 명령형으로 간결하게 (예: `리밸런싱 임계값 계산 오류 수정`)
- PR에는 운영 영향, 변경된 설정값·Secret 여부, 수동 검증 내용 포함
- 출력 형식이 바뀐 경우 리포트 경로나 스크린샷 첨부

## 보안 및 데이터 주의사항

- `key.json`은 커밋 금지. 소스에는 `key.json.example`만 유지
- `data/`, `reports/`는 운영 기록으로 취급 — 과거 산출물 복구 작업이 아닌 한 수동 편집 지양

## 작업 원칙

모호한 요구사항이나 설계 결정이 있다면 임의로 판단하지 말고, 작업 전에 사용자에게 확인한다.
