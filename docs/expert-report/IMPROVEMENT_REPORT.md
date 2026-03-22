# classicQuant 개선 리포트

> 최초 분석: 2026-03-22 | 마지막 업데이트: 2026-03-22
> 분석 기준: 현재 소스코드 직접 라인별 검증

---

## 전체 이슈 현황

| ID | 심각도 | 내용 | 상태 |
|----|--------|------|------|
| C-1 | 🔴 Critical | NAV 가격 순서 버그 | ✅ 수정됨 (리팩터링 시) |
| C-2 | 🔴 Critical | 가격 0 처리 부재 | ✅ 수정됨 (리팩터링 시) |
| C-3 | 🔴 Critical | Fallback 전략 검증 누락 | ✅ 수정됨 |
| N-1 | 🔴 Critical | `assets_file` 속성 오류 (매일 크래시) | ✅ 수정됨 |
| N-4 | 🔴 Critical | `get_strategy()` 생성자에 `assets_file=None` 전달 | ✅ 수정됨 |
| H-1 | 🟠 High | `factor.py` 0 나누기 | ✅ 수정됨 (리팩터링 시) |
| H-2 | 🟠 High | LAA FRED 실패 시 무조건 공격 모드 | 🟠 **잔존** |
| H-3 | 🟠 High | GitHub Actions 고정 재시도 (백오프 없음) | ✅ 수정됨 |
| H-4 | 🟠 High | CSV 중복 저장 무음 실패 | 🟡 낮음으로 하향 (운용 영향 미미) |
| N-2 | 🟠 High | 구 보유종목 매도 누락 | 🟡 **조건부 잔존** |
| **Workflow** | 🔴 Critical | `strategy_nav.csv` 미업데이트 (run_collect 누락) | ✅ 수정됨 |
| L-1 | 🟢 Low | KIS API 타임아웃 없음 | 🟢 **잔존** |
| L-2 | 🟢 Low | 매직넘버 상수화 | ✅ 수정됨 (리팩터링 시) |
| N-3 | 🟢 Low | `_rank_by_score` 이중 정의 | 🟢 **잔존** |

---

## 수정 완료 항목

### C-3. Fallback 전략 검증 ✅
`run_rebalance.py` — 서킷브레이커 발동 시 `fallback_strategy`가 `all_results`에 없으면 명시적 `RuntimeError` 발생.

### N-1. `assets_file` 속성 오류 ✅
`run_collect.py:137` — `strategy.assets_file` → `strategy.assets`

### N-4. `get_strategy()` 생성자 오류 ✅
`app/strategies/__init__.py` — `get_strategy(name, assets_file=None)` → `get_strategy(name)`, `_REGISTRY[name]()` 로 수정.
리팩터링 후 전략 클래스에 `__init__` 없어 `TypeError` 유발하던 문제 해결.

### Workflow — `run_collect.py` 추가 ✅
`.github/workflows/classicQuant.yml` — `run_rebalance.py` 실행 전 `run_collect.py` 스텝 추가.
`strategy_nav.csv`가 매일 갱신되어 전략 선택 기준이 실시간화됨.

### H-3. 지수 백오프 ✅
워크플로 양쪽 스텝(collect, rebalance) 모두 고정 30초 → 지수 백오프(30→60→120→240→480초) 적용.

---

## 잔존 이슈

### 🟠 H-2. LAA FRED API 실패 시 무조건 공격 모드

**파일:** `app/strategies/laa/__init__.py:81-89`

```python
except Exception as e:
    print(f"  ⚠️  LAA: FRED 실업률 조회 실패 ({e}), risk-on 유지")
    return False  # ← 실패 시 항상 공격 모드
```

네트워크 불안정 시 LAA가 침체 국면에서도 방어 전환을 하지 않는 구조.

**수정 방향:** 마지막 성공한 FRED 결과를 `data/fred_cache.json`에 저장, 실패 시 캐시 사용.

---

### 🟡 N-2. 구 보유종목 매도 누락 (조건부)

**파일:** `app/execution/portfolio.py:137-138`

Phase 1에서 15개 전략 전체를 실행하므로 (`asset_files`에 전체 전략 자산 포함), 정상 동작 시에는 문제 없음.

**문제 발생 조건:** Phase 1에서 특정 전략이 예외로 실패하면, 해당 전략의 티커가 `merge_assets`에서 누락 → `known_asset_groups()`에 없음 → 해당 티커 보유 시 매도 주문 미생성.

**수정 방향:** Phase 1 실패 전략의 `ASSETS`도 별도로 `asset_files`에 추가하거나, 캐시 외 보유 종목을 전량 매도로 처리하는 예외 로직 추가.

---

### 🟢 L-1. KIS API 타임아웃 없음

**파일:** `app/data/kis_api.py`

모든 `requests.get/post()` 호출에 `timeout` 파라미터 없음 → 응답 없는 API에 무한 대기 가능.
FRED API는 `_TIMEOUT = 15`로 수정됐으나 KIS API는 미적용.

**수정 방향:** `requests.get(url, ..., timeout=30)` 일괄 추가.

---

### 🟢 N-3. `_rank_by_score` 이중 정의

```python
# app/strategies/mixins.py:11  (모듈 수준 함수)
def _rank_by_score(assets, scores, n=None): ...

# app/strategy.py:64  (BaseStrategy 정적 메서드)
@staticmethod
def _rank_by_score(assets, scores, n=None): ...
```

동작은 동일하지만 한쪽만 수정하는 실수 위험 존재.

---

## 백테스트 구조적 이슈 (미수정)

운용 안전성과 무관한 장기 개선 과제입니다.

| 항목 | 영향 |
|------|------|
| **생존자 편향** | GLDM(2018), QQQM(2020) 등 신규 ETF를 전체 기간에 소급 적용 → CAGR 과대평가 |
| **리밸런싱 지연 미반영** | 월말 신호 당일 즉시 반영, 실거래는 익영업일 실행 |
| **거래비용 미반영** | KIS 수수료 0.25% + 세금 22% 미반영 |
| **Walk-Forward 분석 없음** | 파라미터 과적합 위험 |
