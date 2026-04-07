# classicQuant 개선 체크리스트

> 기준일: 2026-04-07
> 목적: 전문 퀀트 운용 관점의 개선 과제를 추적하고, 완료 여부를 코드/검증 기준으로 체크한다.

---

## 사용 규칙

- `[ ]` 미착수: 코드 수정 전
- `[~]` 진행중: 설계 또는 구현 중
- `[x]` 완료: 코드 수정 + 최소 검증 + 문서 반영 완료
- 상태를 바꿀 때는 아래 `진행 메모`와 `검증`도 함께 업데이트한다.

---

## 1. 최우선 과제

### Q-01. 실제 보유 기준 `portfolio_nav` 재구성

- 상태: `[x]`
- 우선순위: Critical
- 목표:
  - `portfolio_nav_actual.csv`가 실제 보유 포트폴리오 기준 NAV를 반영하도록 수정
  - 서킷브레이커가 내부 추정치가 아니라 운용 계정 상태를 기준으로 작동하도록 변경
- 관련 파일:
  - [run_rebalance.py](/Users/parkh/Dev/git/Project/classicQuant/run_rebalance.py)
  - [app/analytics/csv_logger.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/csv_logger.py)
- 완료 조건:
  - 실제 보유/현금 기준 NAV 계산 로직 존재
  - `portfolio_nav_actual.csv` 갱신이 일관된 거래일 기준으로 수행
  - 서킷브레이커 입력과 리포트 숫자가 동일한 기준을 사용
- 검증:
  - 임시 CSV에서 구형 3컬럼 `portfolio_nav.csv` 자동 승격 확인
  - 임시 상태에서 `1000.00 -> 1100.00` 총자산 변동이 NAV `+10%`로 반영되는지 확인
- 진행 메모:
  - 2026-04-07 `portfolio_state.csv`를 추가해 실제 총자산 스냅샷을 보관
  - 2026-04-07 `portfolio_nav_actual.csv`가 이전 일자 `total_equity` 대비 수익률로 갱신되도록 변경
  - 2026-04-07 기존 `portfolio_nav.csv`는 actual NAV 저장 시 자동 마이그레이션되도록 처리

### Q-02. 선택 전략 수 부족 시 비중 재정규화

- 상태: `[x]`
- 우선순위: Critical
- 목표:
  - `top_n=2`인데 1개 전략만 선택되면 100% 재배분 또는 명시적 현금 슬롯 처리
- 관련 파일:
  - [app/strategy_selector.py](/Users/parkh/Dev/git/Project/classicQuant/app/strategy_selector.py)
- 완료 조건:
  - 선택 결과 개수 기준으로 최종 weight 합계가 항상 100% 또는 설정된 cash 슬롯을 포함해 명시적으로 설명됨
  - 보고서 출력과 실제 주문 생성 결과가 동일한 weight를 사용
- 검증:
  - 후보 1개만 남는 시나리오 테스트
  - `python3 -m py_compile app/strategy_selector.py`
- 진행 메모:
  - 2026-04-07 실제 선택된 전략 수 기준으로 `slot_weight` 재정규화 적용
  - 2026-04-07 fallback 단독 선택 시 weight 100% 확인

### Q-03. 결측 가격 처리 규칙 통일

- 상태: `[x]`
- 우선순위: High
- 목표:
  - 백테스트, 일별 NAV, 실거래 리포트에서 가격 결측 시 동일한 정책을 사용
- 관련 파일:
  - [app/analytics/backtest.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/backtest.py)
  - [run_collect.py](/Users/parkh/Dev/git/Project/classicQuant/run_collect.py)
- 완료 조건:
  - 정책이 문서화됨
  - 관련 함수가 동일 규칙으로 계산됨
- 검증:
  - 공용 함수 스모크에서 절반 비중 자산이 결측일 때 총 수익률 `0.050000` 확인
- 진행 메모:
  - 2026-04-07 `app/analytics/returns.py`의 공용 `compute_weighted_return()`을 `run_collect.py`와 `app/analytics/backtest.py`가 공통 사용
  - 2026-04-07 가격 누락 그룹은 0% 수익률로 동일 처리

---

## 2. 운영 안정성 과제

### Q-04. 주요 CSV 로거 idempotent 저장

- 상태: `[x]`
- 우선순위: High
- 목표:
  - `holdings.csv`, `momentum.csv`, `portfolio.csv`, `strategy_signals.csv` 중복 기록 방지
- 관련 파일:
  - [app/analytics/csv_logger.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/csv_logger.py)
  - [classicQuant.yml](/Users/parkh/Dev/git/Project/classicQuant/.github/workflows/classicQuant.yml)
- 완료 조건:
  - 재실행 시 동일 키 중복 행이 생기지 않음
  - 어떤 키를 dedupe 기준으로 삼는지 코드에 드러남
- 검증:
  - temp CSV로 동일 날짜 2회 저장 시 중복 행이 생성되지 않음
  - `load_strategy_signals()`가 동일 날짜 중복을 접어서 소비함
- 진행 메모:
  - 2026-04-07 저장 키 기준 중복 방지 적용 완료

### Q-05. 백테스트 스크립트 비대화형 실행 지원

- 상태: `[x]`
- 우선순위: High
- 목표:
  - `run_selection_backtest.py`가 `input()` 없이 종료 가능
- 관련 파일:
  - [run_selection_backtest.py](/Users/parkh/Dev/git/Project/classicQuant/run_selection_backtest.py)
- 완료 조건:
  - 기본 실행이 비대화형으로 정상 종료
  - 설정 반영이 필요하면 `--apply-config` 또는 `--auto-apply` 같은 명시 옵션 사용
- 검증:
  - `python run_selection_backtest.py --top-n 2`
- 진행 메모:
  - 2026-04-07 실행 시 마지막 `input()`에서 `EOFError` 확인
  - 2026-04-07 `python3 -m py_compile run_selection_backtest.py`
  - 2026-04-07 `python3 run_selection_backtest.py --top-n 2` 정상 종료

### Q-06. 날짜 기준 단일화

- 상태: `[x]`
- 우선순위: Medium
- 목표:
  - 저장소 전반에서 "미국 거래일" 또는 "UTC 기준일" 중 하나로 통일
- 관련 파일:
  - [run_rebalance.py](/Users/parkh/Dev/git/Project/classicQuant/run_rebalance.py)
  - [run_collect.py](/Users/parkh/Dev/git/Project/classicQuant/run_collect.py)
  - [app/analytics/report.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/report.py)
- 완료 조건:
  - CSV, 리포트, 휴장 판단이 모두 동일 날짜 함수를 사용
- 검증:
  - `python3 -m py_compile run_collect.py run_rebalance.py app/analytics/report.py app/time_utils.py`
- 진행 메모:
  - 2026-04-07 `app/time_utils.py`에 미국 시장 기준 거래일 함수 추가
  - 2026-04-07 `run_collect.py`, `run_rebalance.py`, `app/analytics/report.py`가 동일 함수를 사용하도록 통일

---

## 3. 실거래 품질 과제

### Q-07. 주문 후 체결/잔고 재확인

- 상태: `[x]`
- 우선순위: Medium
- 목표:
  - 매도/매수 후 잔고 재조회 또는 체결 확인으로 주문 실패를 탐지
- 관련 파일:
  - [app/execution/portfolio.py](/Users/parkh/Dev/git/Project/classicQuant/app/execution/portfolio.py)
  - [app/data/kis_api.py](/Users/parkh/Dev/git/Project/classicQuant/app/data/kis_api.py)
- 완료 조건:
  - 주문 결과가 로그에 남고 실패 시 후속 처리 경로가 존재
- 검증:
  - fake API 기반 `execute_orders()` 스모크에서 성공 1건 / 실패 1건 요약 확인
- 진행 메모:
  - 2026-04-07 `execute_orders()`가 성공/실패 요약을 반환
  - 2026-04-07 주문 후 `get_holdings_all_exchanges()`와 `get_account_cash()`로 사후 스냅샷 로그 추가

### Q-08. KIS API timeout / 예외 처리 강화

- 상태: `[x]`
- 우선순위: Medium
- 목표:
  - 주요 API 호출에 timeout 부여
  - 네트워크 실패 시 재시도 또는 명확한 실패 처리
- 관련 파일:
  - [app/data/kis_api.py](/Users/parkh/Dev/git/Project/classicQuant/app/data/kis_api.py)
- 완료 조건:
  - `requests.get/post(..., timeout=...)` 적용
  - 토큰 발급, 시세 조회, 잔고 조회, 주문 API에 공통 정책 반영
- 검증:
  - `python3 -m py_compile app/data/kis_api.py`
  - `requests.request` 더미로 `timeout=7` 전달 확인
- 진행 메모:
  - 2026-04-07 `KoreaInvestmentAPI._request_json()`에 공통 timeout/예외 처리 추가
  - 2026-04-07 주문/가격/잔고/과거데이터 조회가 동일 래퍼를 사용

---

## 4. 리서치 품질 과제

### Q-09. 메타 선택 walk-forward 검증

- 상태: `[x]`
- 우선순위: Medium
- 목표:
  - `corr_constrained`, `sharpe_12m`, `strategy_momentum`의 out-of-sample 일관성 확인
- 관련 파일:
  - [run_selection_backtest.py](/Users/parkh/Dev/git/Project/classicQuant/run_selection_backtest.py)
- 완료 조건:
  - in-sample / out-of-sample 분리 결과 문서화
- 검증:
  - `python3 run_selection_backtest.py --walk-forward --top-n 2 --train-years 5 --test-years 1`
  - `docs/expert-report/2026-04-07/WALK_FORWARD_AND_OVERLAP.md` 작성
- 진행 메모:
  - 2026-04-07 `corr_constrained`, `sharpe_12m`, `strategy_momentum` 비교 결과 문서화

### Q-10. 전략군 중복도 축소 검토

- 상태: `[x]`
- 우선순위: Low
- 목표:
  - 유사 전략 다수를 그대로 유지할지, 대표 전략만 남길지 판단 근거 확보
- 관련 파일:
  - [docs/STRATEGY.md](/Users/parkh/Dev/git/Project/classicQuant/docs/STRATEGY.md)
  - [run_selection_backtest.py](/Users/parkh/Dev/git/Project/classicQuant/run_selection_backtest.py)
- 완료 조건:
  - 전략 간 상관관계, 동시 선택 빈도, 기여도 비교표 작성
- 검증:
  - `python3 run_selection_backtest.py --duplication --years 10`
  - `docs/expert-report/2026-04-07/WALK_FORWARD_AND_OVERLAP.md` 작성
- 진행 메모:
  - 2026-04-07 `laa`, `permanent`, `daa`, `gem` 중심으로 선택이 집중됨

---

## 5. 현재 상태 요약

| ID | 상태 | 우선순위 | 한 줄 요약 |
|----|------|----------|------------|
| Q-01 | [x] | Critical | `portfolio_nav`를 실제 운용 포트폴리오 기준으로 재구성 |
| Q-02 | [x] | Critical | 선택 전략 수 부족 시 weight 재정규화 |
| Q-03 | [x] | High | 결측 가격 처리 규칙 통일 |
| Q-04 | [x] | High | 주요 CSV idempotent 저장 |
| Q-05 | [x] | High | 백테스트 스크립트 비대화형 실행 지원 |
| Q-06 | [x] | Medium | 날짜 기준 단일화 |
| Q-07 | [x] | Medium | 주문 후 체결/잔고 재확인 |
| Q-08 | [x] | Medium | KIS API timeout/예외 처리 강화 |
| Q-09 | [x] | Medium | 메타 선택 walk-forward 검증 |
| Q-10 | [x] | Low | 전략군 중복도 축소 검토 |
