# ESP32 Wi-Fi FEM board

Открытая плата на ESP32 с внешним ВЧ-фронтендом (усилитель мощности + малошумящий
усилитель + переключатель) по мотивам ESP32-M1 Reach Out, но на доступных деталях из
каталога LCSC, под сборку на JLCPCB и в рамках лимита 100 мВт.

```
hardware/kicad/       KiCad 7 проект (схема, плата, библиотека)
hardware/kicad/tools/ генераторы: design.py (детали и цепи), gen_sch.py, gen_pcb.py, route.py
firmware/             ESP-IDF: компонент управления усилителем + тест дальности
docs/design.md        описание конструкции и отличия от оригинала (rev A)
docs/design_pico.md   rev B: ESP32-PICO-D4 без пигтейла
docs/design_1w.md     вариант 1 Вт (QPF4219) — схема и BOM, без разводки
docs/ordering.md      как заказать на JLCPCB, что докупить, первое включение
docs/review*.md       результаты ревью субагентами и статус правок
```

Три варианта в одном генераторе (переменная `DESIGN`):

| Вариант | Файл | Мощность | Состояние |
|---|---|---|---|
| rev A | `design.py` → `esp32_fem.*` | 100 мВт (RFX2401C), модуль WROOM-32U + пигтейл | разведена, DRC 0, файлы в `build/fab/` |
| rev B | `design_pico.py` → `esp32_fem_pico.*` | 100 мВт, голый ESP32-PICO-D4, без пигтейла | разведена, DRC 0, файлы в `build/fab_pico/` |
| 1 Вт | `design_1w.py` → `esp32_fem_1w.*` | 1 Вт (QPF4219 + RFSW8009), только для лаборатории | схема и BOM проверены, разводки нет |

## Ключевые параметры

| | |
|---|---|
| Модуль | ESP32-WROOM-32U-N4 (внешняя антенна через U.FL) |
| Фронтенд | RFX2401C: PA до +20 дБм, LNA 12 дБ, 3,3 В |
| Управление | GPIO23 = TXEN, GPIO18 = RXEN через `esp_wifi_set_ant_gpio()` |
| Плата | 4 слоя, 64 × 52 мм, стек JLC04161H-7628, микрополосок 0,38 мм |
| Интерфейс | USB-C, CH340C, автосброс DTR/RTS, кнопки RESET/BOOT |
| Антенна | SMA/RP-SMA edge-mount |

## Как пересобрать файлы

```bash
cd hardware/kicad
python3 tools/gen_sch.py                                  # схема из design.py
kicad-cli sch export netlist --format kicadsexpr -o build/esp32_fem.net esp32_fem.kicad_sch
python3 tools/gen_pcb.py                                  # плата: размещение, ВЧ-дорожки, полигоны
# автотрассировка остальных цепей (freerouting), затем:
python3 tools/route.py import                             # импорт .ses, заливка полигонов
python3 tools/route.py drc                                # отчёт DRC в build/drc.rpt
python3 tools/route.py fab                                # Gerber, сверловка, BOM и CPL для JLCPCB
```

Для rev B — то же с `DESIGN=design_pico` перед каждой командой (файлы `esp32_fem_pico.*`,
freerouting запускать с `-inc RF,SKIP`: ВЧ и земля роутеру закрыты; см. `build/run_pico.sh`).
Для 1 Вт — `DESIGN=design_1w` (только схема).

Плату можно открыть и править в KiCad 7/8 как обычный проект.

## Прошивка

```bash
cd firmware
idf.py set-target esp32
idf.py menuconfig      # FEM board -> SSID, пароль, мощность
idf.py build flash monitor
```

Компонент `fem_rfx2401` можно перенести в любой другой проект (например в esp32_nat_router):
вызвать `fem_rfx2401_init()` после `esp_wifi_init()` и `fem_rfx2401_set_tx_power(32)` после
`esp_wifi_start()`.

## Статус

Rev A и rev B разведены и проверены DRC, ни одна пока не изготавливалась. Перед заказом см.
`docs/ordering.md` и итоги ревью в `docs/review.md`, `docs/review_revB.md`.
