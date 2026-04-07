# classicQuant NAV 정책

> 작성일: 2026-04-08
> 목적: 저장소에서 사용하는 NAV의 의미, 용도, 계산 원칙, 운영 규칙을 명확히 정의한다.

---

## 1. 정책 목적

classicQuant는 개별 전략을 비교해 선택하고, 선택 규칙 자체도 평가하며, 실제 계좌도 운용한다.  
이 구조에서는 `NAV`라는 단어가 하나의 의미만 가지지 않는다.

따라서 이 저장소는 NAV를 역할별로 분리해 관리한다.

---

## 2. NAV 종류

### 2-1. 전략 NAV

명칭:

- `strategy_nav`

의미:

- 개별 전략 하나를 단독으로 연속 운용했다고 가정한 모델 NAV

역할:

- 전략 선택 입력값
- 전략별 수익률, Sharpe, Calmar, drawdown 계산

규칙:

- 전략 선택 로직은 `strategy_nav`만 사용한다.
- `strategy_nav`는 포트폴리오 전체 성과 지표로 해석하지 않는다.

### 2-2. 모델 포트폴리오 NAV

명칭:

- `portfolio_nav_model`

의미:

- 전략 선택 규칙까지 포함해, 이론적으로 포트폴리오를 운용했다고 가정한 모델 NAV

역할:

- `criteria`, `top_n`, `mdd_filter_threshold`, `portfolio_mdd_limit` 같은 메타 설정 검증
- 백테스트, walk-forward, overlap 분석의 기준

규칙:

- 설정 연구와 리서치 보고는 `portfolio_nav_model`을 사용한다.
- 실계좌 리스크 통제에는 사용하지 않는다.

### 2-3. 실제 포트폴리오 NAV

명칭:

- `portfolio_nav_actual`

의미:

- 실제 계좌 총자산 기준 NAV

역할:

- 실전 운용 성과 평가
- 실제 MDD 감시
- 서킷브레이커
- 운영 리포트

규칙:

- 실전 리스크 관리는 `portfolio_nav_actual`만 사용한다.
- 모델 포트폴리오 NAV와 섞어서 해석하지 않는다.

---

## 3. NAV별 사용 원칙

### 원칙 A. 전략 선택은 전략 NAV만 사용

- 어떤 전략을 고를지
- 어떤 전략을 제외할지
- 어떤 전략의 최근 성과가 더 좋은지

이 판단은 전부 `strategy_nav` 기반으로 수행한다.

### 원칙 B. 메타 설정 평가는 모델 포트폴리오 NAV만 사용

- `criteria`
- `top_n`
- 개별 전략 MDD 필터
- 포트폴리오 레벨 파라미터

이 판단은 전부 `portfolio_nav_model` 기반으로 수행한다.

### 원칙 C. 실전 리스크 관리는 실제 포트폴리오 NAV만 사용

- 실제 MDD
- 실제 손실 통제
- 운영 중단/감속 판단
- 월간/연간 성과 평가

이 판단은 전부 `portfolio_nav_actual` 기반으로 수행한다.

---

## 4. 기간 정책

### 전략 NAV

권장 사용:

- 선택 신호: 6개월, 12개월
- 안정성 확인: 12개월, 24개월
- 상관관계: 63거래일 수준의 단기 창

### 모델 포트폴리오 NAV

권장 사용:

- 3년: 최근 적합성
- 5년: 중기 안정성
- 10년: 구조적 일관성
- walk-forward: 필수

### 실제 포트폴리오 NAV

권장 사용:

- 시작 이후 전체
- 최근 3개월
- 최근 12개월

---

## 5. 해석 금지 규칙

다음 해석은 금지한다.

1. `strategy_nav`를 실제 운용 성과로 직접 해석
2. `portfolio_nav_model`을 실제 계좌 손익처럼 해석
3. `portfolio_nav_actual`과 `portfolio_nav_model`을 한 시계열로 이어서 CAGR/MDD를 계산
4. NAV 종류를 명시하지 않고 보고서에서 그냥 `portfolio_nav`라고만 표기

---

## 6. 보고서 표기 규칙

문서, 리포트, 코드 주석에서는 아래 명칭을 사용한다.

- 전략 NAV
- 모델 포트폴리오 NAV
- 실제 포트폴리오 NAV

영문 표기가 필요하면 다음을 사용한다.

- `strategy_nav`
- `portfolio_nav_model`
- `portfolio_nav_actual`

---

## 7. 현재 저장소 기준 TODO

정책상 아직 남아 있는 과제:

1. 모델 포트폴리오 NAV와 실제 포트폴리오 NAV의 파일명을 완전히 분리
2. 서킷브레이커 입력을 `portfolio_nav_actual`로 명시 고정
3. 리서치 스크립트 출력에서 `model` / `actual` 표기를 강제
4. 수수료, 세금, 입출금 조정이 반영된 net actual NAV 계층 추가

---

## 8. 한 줄 원칙

> 전략 NAV는 전략을 고르는 데 쓰고, 모델 포트폴리오 NAV는 규칙을 검증하는 데 쓰고, 실제 포트폴리오 NAV는 실제 돈을 지키는 데 쓴다.
