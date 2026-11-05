# Пакет оценки модели — Stage 17

| Поле | Значение |
|---|---|
| Model id | `model-20261028-9ce4d4180aa9` |
| Модель | `gru_attention_q7`, hidden 64, 1 слой, dropout 0,1, 7 квантилей, среднее 5 seeds на год, без калибровки |
| Пакет | `eval-20261028-b365e4a12ddb` (`var/data/forecast/`, не в git) |
| Датасет | `fds-20261028-d9e4acd03365`, последовательности `fsq-20261028-80de28a4bff3` |
| Протокол | `stage_17_evaluation`, SHA-256 `26bfc0b3224f20459c1e18369205ec1e1cd06bdf5319a9efc1a489bf64431c96` |
| Настройки | Выбраны на `bench-20261028-f02547836d11` (validation 2016–2019) |
| Полосы | SHA-256 `1623f4ade1d4…` |
| Подпись владельца | 2026-11-06, ответ на вопрос о приёмке этапов 16–18 и кандидате: «Принять и Stage 19» |

## Вердикт

**Модель одобрена для 3 пар из 15, только для исследования.** Это не разрешение для продукта: ни один прогноз приложения от неё не зависит.

| Цель | h | Строк final | Покрытие 50 / 80 / 90% | Pinball к persistence | Pinball к лучшему baseline |
|---|---|---|---|---|---|
| operating margin | 8 | 612 | 52,6 / 80,9 / 90,0 | −29,8% (−37,2..−22,1) | −4,0% (−8,8..+0,7) |
| EBITDA margin | 4 | 1 745 | 55,0 / 83,4 / 90,9 | −29,5% (−36,1..−23,3) | −5,6% (−9,1..−2,2) |
| EBITDA margin | 8 | 560 | 53,6 / 80,9 / 91,2 | −30,1% (−39,5..−20,8) | −6,7% (−12,9..−0,6) |

## Что нельзя утверждать

- **Рост выручки:** прогноз лучший на h = 4 и 8, но интервалы шире заявленных. Не одобрено.
- **FCF margin:** квантильный бустинг значимо лучше на h = 1 и 4, на h = 8 сеть не лучше него. Не одобрено.
- **Debt/EBITDA:** не бьёт persistence на h = 1 и 4 с интервалом ниже нуля. Не одобрено.
- **Горизонты 12 и 20:** вердикта нет, метки ещё не опубликованы.
- **Эффект решений:** этот пакет о нём ничего не говорит.

## Таблица baselines

Средний log pinball, h = 1, 4, 8, знакомые фирмы, ниже — лучше.

| Модель | Development 2020–2023 | Final 2024–2026 |
|---|---|---|
| `gbm_quantile` calibrated | −1,6952 | −1,8487 |
| GRU q7 | −1,6835 | −1,8412 |
| TCN q7 | −1,6673 | −1,8232 |
| `persistence` | −1,3857 | −1,5288 |
| `gbm` | −1,2632 | −1,3761 |
| `elastic_net` | −0,9866 | −1,1135 |

Квантильный бустинг не уступает сети в сумме. Сеть выигрывает на h = 4–8 по росту и EBITDA-марже и проигрывает на h = 1.

## Провалы

Все 22 — в `report.md` пакета. Главные:

- Покрытие в 2020 году: 67–78% вместо 80% при h = 4.
- Рост выручки: 50%-интервал покрывает 55–58%.
- Debt/EBITDA h = 1: только 42% фирм прогнозируются лучше persistence.
- Вне распределения при h = 4 ошибка в 2,4–2,9 раза выше, 90%-интервал покрывает 80–86%.
- Conformal-калибровка ухудшила покрытие на development: 0,051 против 0,029 для 80%-интервала.

## Графики

- [Reliability](17-plots/reliability.svg)
- [Покрытие по годам](17-plots/coverage-by-year.svg)
- [Сравнение с persistence](17-plots/against-persistence.svg)
- [Ablations](17-plots/ablations.svg)

## Подпись

Владелец принял пакет 2026-11-06. Подпись касается только трёх пар выше и только исследования. Новые данные или другой протокол требуют новой оценки.

## Воспроизведение

```bash
uv run python -m multiverse_forecast evaluate train --dataset var/data/forecast/fds-20261028-d9e4acd03365 --benchmark var/data/forecast/bench-20261028-f02547836d11/report.json --baselines var/data/forecast/bench-20261028-641a5b7181ea/report.json --device cuda
```

```bash
uv run python -m multiverse_forecast evaluate baselines --dataset var/data/forecast/fds-20261028-d9e4acd03365 --benchmark var/data/forecast/bench-20261028-f02547836d11/report.json --baselines var/data/forecast/bench-20261028-641a5b7181ea/report.json
```

```bash
uv run python -m multiverse_forecast evaluate report --dataset var/data/forecast/fds-20261028-d9e4acd03365 --benchmark var/data/forecast/bench-20261028-f02547836d11/report.json --baselines var/data/forecast/bench-20261028-641a5b7181ea/report.json --figures docs/stages/17-plots
```
