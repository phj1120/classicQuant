# classicQuant 추가 개선 보고서

> 작성일: 2026-04-08
> 범위: NAV model/actual 분리 리팩토링, 문서 정합성 보강, 무키 report-only 검증 경로 추가

---

## 1. 이번 라운드 핵심 개선

이번 라운드의 핵심은 설계 문서에 적어둔 NAV 분리 정책을 코드와 데이터 파일 수준으로 한 단계 더 밀어붙인 것이다.

주요 변경:

- `portfolio_nav_model.csv`
- `portfolio_nav_actual.csv`
- `portfolio_state.csv`

를 역할별로 더 명확히 구분했다.

---

## 2. 코드 변경 요약

### 2-1. CSV 경로와 함수 역할 분리

대상:

- [app/analytics/csv_logger.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/csv_logger.py)

변경:

- `PORTFOLIO_NAV_MODEL_CSV`
- `PORTFOLIO_NAV_ACTUAL_CSV`
- `PORTFOLIO_NAV_LEGACY_CSV`

를 도입했다.

- `save_portfolio_nav_model()`
- `load_portfolio_nav_model()`
- `save_portfolio_nav_actual()`
- `load_portfolio_nav_actual()`

로 I/O를 분리했다.

### 2-2. 레거시 `portfolio_nav.csv` 호환

대상:

- [app/analytics/csv_logger.py](/Users/parkh/Dev/git/Project/classicQuant/app/analytics/csv_logger.py)

변경:

- 기존 `data/portfolio_nav.csv`가 남아 있어도, actual NAV 파일이 비어 있으면 자동으로 actual 쪽으로 승격되도록 처리했다.
- 3컬럼 파일은 4컬럼 형식으로 변환된다.

### 2-3. 실전 경로는 actual만 사용

대상:

- [run_rebalance.py](/Users/parkh/Dev/git/Project/classicQuant/run_rebalance.py)

변경:

- 서킷브레이커는 `load_portfolio_nav_actual()`만 사용한다.
- actual NAV 갱신은 `_update_portfolio_nav_actual()`로 명시했다.

### 2-4. 연구 경로는 model만 사용

대상:

- [run_selection_backtest.py](/Users/parkh/Dev/git/Project/classicQuant/run_selection_backtest.py)

변경:

- `--generate-portfolio-nav`는 이제 `data/portfolio_nav_model.csv`를 만든다.
- 리서치 출력 메시지도 model NAV 기준으로 수정했다.

### 2-5. 무키 환경 report-only 지원

대상:

- [run_rebalance.py](/Users/parkh/Dev/git/Project/classicQuant/run_rebalance.py)

변경:

- `--report-only` 실행 시 API 키가 없으면 `data/ohlc_history.csv`를 읽는 offline 캐시 API로 자동 전환한다.
- 이 모드에서는 전략 선택과 리포트 생성은 수행하되, 실제 계좌 스냅샷/actual NAV/portfolio snapshot은 기록하지 않는다.
- legacy NAV를 읽더라도 `portfolio_nav_actual.csv`를 디스크에 자동 생성하지 않도록 부작용을 제거했다.
- 즉, 로컬 개발 환경에서 "선택 로직과 보고서가 깨지지 않는지"를 키 없이 검증할 수 있다.

---

## 3. 운영상 의미

이번 변경으로 다음 구분이 코드 차원에서 더 명확해졌다.

- 전략 선택 입력: `strategy_nav`
- 메타 설정 연구: `portfolio_nav_model`
- 실제 리스크 관리: `portfolio_nav_actual`

전문 운용 관점에서 이건 단순한 파일명 정리가 아니다.  
이제 selector, allocator research, live trading truth가 서로 다른 데이터 경로를 쓰기 시작했기 때문에, 해석 오류와 운용 실수가 줄어든다.

---

## 4. 검증

실행/확인:

- `python3 -m py_compile app/analytics/csv_logger.py run_rebalance.py run_selection_backtest.py`
- 레거시 `portfolio_nav.csv` 3컬럼 파일을 임시 경로에 두고 저장 시 자동 승격 확인
- `python3 run_selection_backtest.py --top-n 2`
- `python3 run_rebalance.py --report-only` (API 키 없는 로컬 환경)

확인 결과:

- 컴파일 정상
- 레거시 3컬럼 NAV 파일이 actual 형식으로 자동 변환됨
- 기본 백테스트 실행 정상
- 키가 없는 환경에서도 report-only가 offline 캐시 경로로 정상 실행됨

### 4-1. 저장소 데이터 상태 점검

2026-04-08 현재 저장소 기준:

- `data/portfolio_nav_model.csv`: 존재, 5032행
- `data/portfolio_nav.csv`: 존재, 5032행
- `data/portfolio_nav_model.csv`와 `data/portfolio_nav.csv`: 현재 파일 내용 동일
- `data/portfolio_nav_actual.csv`: 아직 없음
- `data/portfolio_state.csv`: 아직 없음

의미:

- 코드 구조는 model/actual 분리까지 반영됐지만,
- 저장소에 커밋된 운영 데이터는 아직 actual NAV 체계로 전환 완료된 상태가 아니다.

즉 현재 평가는 다음이 정확하다.

> 구조 반영 완료, 실데이터 actual NAV 적재 및 정합성 검증은 대기 상태

---

## 5. 남은 고급 과제

이번 라운드로 정책/코드 분리는 상당히 정리됐지만, 고급 운용 기준으로는 아직 남은 과제가 있다.

1. `portfolio_nav_model.csv`와 `portfolio_nav_actual.csv`의 리포트 분리 출력
2. actual NAV 기준 기간별 MDD/회복기간 자동 계산
3. 수수료, 세금, 입출금 조정이 반영된 `portfolio_nav_actual_net`
4. 레거시 `portfolio_nav.csv` 완전 퇴역 및 백업 파일 생성 자동화

---

## 6. 결론

이번 라운드 이후 classicQuant의 NAV는 단순히 “개념적으로 다르다” 수준이 아니라, 코드와 파일 레벨에서도 분리되기 시작했다.

한 줄로 요약하면:

> 이제 이 저장소는 NAV를 해석하는 것이 아니라, NAV의 역할을 관리하기 시작했다.
