# classicQuant walk-forward / overlap analysis

> 작성일: 2026-04-07
> 재실행 기준: 코드 반영 후 로컬 데이터 직접 실행

---

## 1. 실행 명령

```bash
python3 run_selection_backtest.py --walk-forward --top-n 2 --train-years 5 --test-years 1
python3 run_selection_backtest.py --duplication --years 10
```

---

## 2. Walk-forward 결과

설정:

- train 5년
- test 1년
- `top_n=2`
- 후보 기준: `nav_momentum`, `return_1m`, `return_3m`, `return_6m`, `return_12m`, `sharpe_12m`, `calmar_12m`, `corr_constrained`

요약 표:

| 기준 | 평균 CAGR | 평균 Sharpe | 평균 MDD | 평균 Calmar | Fold 수 |
|------|-----------|-------------|----------|-------------|--------:|
| `sharpe_12m` | 8.9% | 1.11 | -7.4% | 1.90 | 15 |
| `corr_constrained` | 8.3% | 1.02 | -6.9% | 1.57 | 15 |
| `calmar_12m` | 9.0% | 0.98 | -8.4% | 1.47 | 15 |
| `nav_momentum` | 10.9% | 0.77 | -9.6% | 1.35 | 15 |
| `return_3m` | 9.9% | 0.75 | -9.8% | 1.36 | 15 |
| `return_6m` | 9.8% | 0.75 | -10.1% | 1.28 | 15 |
| `return_12m` | 9.6% | 0.73 | -10.0% | 1.08 | 15 |
| `return_1m` | 8.5% | 0.62 | -9.8% | 1.18 | 15 |

Fold 승리 횟수:

| 기준 | 승리 횟수 |
|------|----------:|
| `calmar_12m` | 5 |
| `return_3m` | 3 |
| `sharpe_12m` | 3 |
| `corr_constrained` | 2 |
| `return_12m` | 1 |
| `return_6m` | 1 |

해석:

- 평균 OOS Sharpe 기준으로는 `sharpe_12m`가 가장 안정적이다.
- `corr_constrained`는 샤프는 약간 낮지만 MDD가 더 작다.
- `calmar_12m`는 특정 fold에서 강하게 이기는 경우가 많지만 평균 안정성은 `sharpe_12m`보다 낮다.
- 실운용 관점에서 "수익률 우선"이면 `sharpe_12m`, "방어 우선"이면 `corr_constrained`가 합리적이다.

결론:

- walk-forward 권장 기준: `sharpe_12m`

---

## 3. 전략 중복도 결과

설정:

- 최근 10년
- 기준: 현재 config의 `corr_constrained`
- `top_n=2`

### 전략별 평균 상관과 선택 횟수

| 전략 | 평균 상관 | 선택 횟수 |
|------|----------:|----------:|
| `laa` | 0.829 | 42 |
| `golden_butterfly` | 0.816 | 5 |
| `daa` | 0.816 | 27 |
| `permanent` | 0.805 | 30 |
| `faa` | 0.785 | 20 |
| `ivy` | 0.763 | 5 |
| `gtaa` | 0.760 | 9 |
| `all_weather` | 0.757 | 11 |
| `eaa` | 0.728 | 2 |
| `baa_g4` | 0.719 | 9 |
| `haa` | 0.719 | 0 |
| `vaa` | 0.719 | 22 |
| `paa` | 0.679 | 17 |
| `baa_g12` | 0.676 | 10 |
| `gem` | 0.676 | 24 |

### 가장 유사한 전략쌍

| 전략 A | 전략 B | 상관계수 |
|--------|--------|---------:|
| `baa_g4` | `haa` | 1.000 |
| `baa_g4` | `vaa` | 1.000 |
| `haa` | `vaa` | 1.000 |
| `baa_g12` | `paa` | 0.999 |
| `gtaa` | `ivy` | 0.999 |
| `laa` | `permanent` | 0.976 |
| `golden_butterfly` | `laa` | 0.975 |
| `golden_butterfly` | `permanent` | 0.969 |
| `eaa` | `paa` | 0.961 |
| `baa_g12` | `eaa` | 0.960 |

### 동시 선택 빈도 상위

| 전략 A | 전략 B | 횟수 |
|--------|--------|----:|
| `gem` | `laa` | 8 |
| `daa` | `laa` | 7 |
| `daa` | `permanent` | 6 |
| `all_weather` | `laa` | 6 |
| `daa` | `paa` | 5 |
| `baa_g12` | `laa` | 5 |
| `laa` | `permanent` | 4 |
| `faa` | `permanent` | 4 |
| `daa` | `faa` | 4 |
| `all_weather` | `vaa` | 4 |

해석:

- `baa_g4`, `haa`, `vaa`는 사실상 동일 축이다.
- `baa_g12`와 `paa`, `gtaa`와 `ivy`도 거의 복제 수준이다.
- `laa`, `permanent`, `daa`, `gem` 쪽으로 실질 선택이 집중된다.

결론:

- 전략 수는 15개지만 독립 알파 수는 훨씬 적다.
- 다음 리서치 단계에서는 대표 전략만 남기는 전략군 압축이 타당하다.
