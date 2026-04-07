# classicQuant NAV 분리 설계안

> 작성일: 2026-04-08
> 목적: 이 저장소 기준 파일명, 함수명, 마이그레이션 계획까지 포함해 NAV 관리 구조를 명확히 분리한다.

---

## 1. 설계 목표

이 저장소의 NAV는 역할이 세 가지다.

1. 개별 전략 선택 입력
2. 메타 설정 검증
3. 실제 운용 성과 및 리스크 관리

현재는 개념적으로는 분리되기 시작했지만, 파일명과 함수명이 아직 완전히 분리되어 있지 않다.  
목표는 아래 세 가지를 명시 구조로 만드는 것이다.

- `strategy_nav`
- `portfolio_nav_model`
- `portfolio_nav_actual`

---

## 2. 권장 파일 구조

### 현재

- `data/strategy_nav.csv`
- `data/portfolio_nav.csv`
- `data/portfolio_state.csv`

### 목표

- `data/strategy_nav.csv`
- `data/portfolio_nav_model.csv`
- `data/portfolio_nav_actual.csv`
- `data/portfolio_state.csv`

### 역할

| 파일 | 역할 |
|------|------|
| `strategy_nav.csv` | 개별 전략 NAV |
| `portfolio_nav_model.csv` | 모델 포트폴리오 NAV |
| `portfolio_nav_actual.csv` | 실제 총자산 기반 포트폴리오 NAV |
| `portfolio_state.csv` | 실제 총자산/현금 스냅샷 원장 |

---

## 3. 현재 저장소 기준 영향 파일

### 전략 NAV

- [app/analytics/csv_logger.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/csv_logger.py)
- [run_collect.py](/Users/parkh/Dev/git/Project/classicQuant/run_collect.py)
- [app/strategy_selector.py](/Users/parkh/Dev/git/Project/classicQuant/app/strategy_selector.py)
- [run_selection_backtest.py](/Users/parkh/Dev/git/Project/classicQuant/run_selection_backtest.py)

### 모델 포트폴리오 NAV

- [run_selection_backtest.py](/Users/parkh/Dev/git/Project/classicQuant/run_selection_backtest.py)
- [app/analytics/csv_logger.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/csv_logger.py)

### 실제 포트폴리오 NAV

- [run_rebalance.py](/Users/parkh/Dev/git/Project/classicQuant/run_rebalance.py)
- [app/analytics/csv_logger.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/csv_logger.py)
- [app/analytics/report.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/report.py)

---

## 4. 함수명 분리 제안

### 현재 상태

현재는 `save_portfolio_nav()`, `load_portfolio_nav()` 같은 이름이 일반화되어 있다.  
이 이름은 model/actual 구분이 없다.

### 목표 함수명

#### 전략 NAV

- `save_strategy_nav()`
- `load_strategy_nav()`

유지:

- 현재 이름 유지 가능

#### 모델 포트폴리오 NAV

- `save_portfolio_nav_model()`
- `load_portfolio_nav_model()`

사용처:

- `run_selection_backtest.py`

#### 실제 포트폴리오 NAV

- `save_portfolio_nav_actual()`
- `load_portfolio_nav_actual()`

사용처:

- `run_rebalance.py`
- 실제 MDD 서킷브레이커

#### 실제 총자산 스냅샷

- `save_portfolio_state()`
- `load_portfolio_state()`

유지:

- 현재 이름 유지 가능

---

## 5. 리팩토링 단계

### 단계 1. CSV 경로 상수 분리

대상 파일:

- [app/analytics/csv_logger.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/csv_logger.py)

작업:

- `PORTFOLIO_NAV_CSV`를 폐기
- 아래 두 상수로 분리
  - `PORTFOLIO_NAV_MODEL_CSV`
  - `PORTFOLIO_NAV_ACTUAL_CSV`

효과:

- model/actual 파일이 코드 레벨에서 분리됨

### 단계 2. I/O 함수 분리

대상 파일:

- [app/analytics/csv_logger.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/csv_logger.py)

작업:

- `save_portfolio_nav()` → `save_portfolio_nav_actual()`
- `load_portfolio_nav()` → `load_portfolio_nav_actual()`
- model 전용 함수 추가
  - `save_portfolio_nav_model()`
  - `load_portfolio_nav_model()`

효과:

- 함수명만 보고도 의도가 드러남

### 단계 3. 사용처 분리

#### `run_rebalance.py`

해야 할 일:

- 서킷브레이커 입력을 `load_portfolio_nav_actual()`로 고정
- 업데이트도 `save_portfolio_nav_actual()`만 사용

#### `run_selection_backtest.py`

해야 할 일:

- 모델 포트폴리오 NAV 생성/저장 경로를 `portfolio_nav_model`로 명시
- 실제 NAV와 같은 이름을 쓰지 않게 정리

효과:

- 실전 리스크 관리와 리서치 출력이 섞이지 않음

### 단계 4. 문서/리포트 용어 통일

대상:

- [docs/policy/NAV_POLICY.md](/Users/parkh/Dev/git/Project/classicQuant/docs/policy/NAV_POLICY.md)
- [docs/expert-report/2026-04-07/QUANT_REVIEW.md](/Users/parkh/Dev/git/Project/classicQuant/docs/expert-report/2026-04-07/QUANT_REVIEW.md)
- [docs/expert-report/2026-04-07/WALK_FORWARD_AND_OVERLAP.md](/Users/parkh/Dev/git/Project/classicQuant/docs/expert-report/2026-04-07/WALK_FORWARD_AND_OVERLAP.md)

작업:

- `portfolio_nav` 단독 표현 제거
- 항상 `model` / `actual` 표기

---

## 6. 마이그레이션 계획

### 목표

기존 `data/portfolio_nav.csv`를 안전하게 분리한다.

### 권장 순서

1. 기존 `data/portfolio_nav.csv`를 읽는다.
2. 행의 생성 규칙에 따라 분류한다.
3. 과거 synthetic/model 구간은 `portfolio_nav_model.csv`로 이동한다.
4. actual-equity 기반으로 쌓기 시작한 시점 이후는 `portfolio_nav_actual.csv`로 이동한다.
5. 현재 `portfolio_state.csv`와 날짜를 매칭해 actual 구간의 정합성을 확인한다.
6. 전환 완료 후 `portfolio_nav.csv`는 더 이상 쓰지 않는다.

### 현실적 구분 규칙

이 저장소 기준으로는 아래처럼 처리하는 것이 실무적이다.

- `portfolio_state.csv`가 존재하지 않는 과거 구간:
  - `portfolio_nav_model.csv`
- `portfolio_state.csv`와 매칭되는 시점 이후:
  - `portfolio_nav_actual.csv`

### 안전장치

- 자동 마이그레이션 시 원본 백업:
  - `portfolio_nav.legacy.csv`
- 분리 후 첫 실행에서는:
  - 행 수 비교
  - 날짜 범위 비교
  - actual 구간의 `total_equity` handoff 확인

---

## 7. 코드 레벨 변경 포인트

### `app/analytics/csv_logger.py`

추가/변경 후보:

- `PORTFOLIO_NAV_MODEL_CSV`
- `PORTFOLIO_NAV_ACTUAL_CSV`
- `save_portfolio_nav_model()`
- `load_portfolio_nav_model()`
- `save_portfolio_nav_actual()`
- `load_portfolio_nav_actual()`
- `migrate_portfolio_nav_legacy()`

### `run_rebalance.py`

변경 후보:

- `_check_portfolio_mdd()`가 `load_portfolio_nav_actual()` 사용
- `_update_portfolio_nav()`를 `_update_portfolio_nav_actual()`로 명시 변경

### `run_selection_backtest.py`

변경 후보:

- `--generate-portfolio-nav`의 출력 파일을 `portfolio_nav_model.csv`로 명시
- 관련 안내문과 도움말 갱신

---

## 8. 운영 규칙 제안

### selector 규칙

- 입력: `strategy_nav.csv`
- 출력: active 전략 목록

### research 규칙

- 입력: `strategy_nav.csv`
- 출력: `portfolio_nav_model.csv`

### live trading 규칙

- 입력: 실제 계좌 총자산, `portfolio_state.csv`
- 출력: `portfolio_nav_actual.csv`

### risk rule

- 서킷브레이커는 무조건 `portfolio_nav_actual.csv`만 사용

---

## 9. 권장 구현 우선순위

1. 파일명 분리
2. 함수명 분리
3. 서킷브레이커 actual 고정
4. 리서치 출력 model 고정
5. 레거시 `portfolio_nav.csv` 분리 마이그레이션
6. 문서와 리포트 표기 일괄 수정

---

## 10. 결론

이 저장소는 이미 NAV를 세 가지 의미로 사용하고 있다.  
이제 필요한 것은 개념적 구분이 아니라, 파일/함수/운영 규칙까지 포함한 구조적 구분이다.

한 줄 권고:

> `strategy_nav`, `portfolio_nav_model`, `portfolio_nav_actual`을 코드와 데이터 파일 수준에서 완전히 분리하는 것이 다음 리팩토링의 정답이다.
