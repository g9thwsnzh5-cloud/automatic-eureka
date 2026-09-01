# ESP32 Wi-Fi FEM board

Открытая плата на ESP32 с внешним ВЧ-фронтендом (усилитель мощности + малошумящий
усилитель + переключатель) по мотивам ESP32-M1 Reach Out, но на доступных деталях из
каталога LCSC, под сборку на JLCPCB и в рамках лимита 100 мВт.

```
hardware/kicad/       KiCad 7 проект (схема, плата, библиотека)
hardware/kicad/tools/ генераторы: design.py (детали и цепи), gen_sch.py, gen_pcb.py, route.py
firmware/             ESP-IDF: компонент управления усилителем + тест дальности
docs/design.md        описание конструкции и отличия от оригинала
docs/ordering.md      как заказать на JLCPCB, что докупить, первое включение
```

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

Rev A, не изготавливалась. Перед заказом см. раздел «Что проверить» в `docs/design.md`.
