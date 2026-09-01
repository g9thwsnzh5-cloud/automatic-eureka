"""rev B: голый ESP32-PICO-D4 + RFX2401C (100 мВт), БЕЗ пигтейла.

ВЧ-сигнал идёт с вывода LNA_IN (pin 2) прямо по плате на усилитель — коаксиального
хвостика U.FL нет. Флеш и кварц у PICO-D4 внутри корпуса, внешние не нужны.
ВЧ-тракт усилителя и вся «передняя» часть (USB-C, CH340C, автосброс, питание 3.3 В)
взяты из rev A. Прошивка та же (TXEN=IO23, RXEN=IO18).

Распиновка PICO-D4 и футпринт (QFN-48 7x7) — из даташита Espressif v1.3.
Выводы внутренней флеши (25,27,28-33) НЕ разводим (соединены с флешью в корпусе).

Мощность 100 мВт — легально. Размер платы меньше rev A за счёт отсутствия разъёма
модуля и пигтейла.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import design as _base  # noqa: E402

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"

# Из rev A берём всё, кроме модуля U1 (заменяем на PICO) и J2 (U.FL, убираем).
DROP = {"U1", "J2"}
COMMON = [dict(p) for p in _base.PARTS if p["ref"] not in DROP]

# В rev A вход усилителя: J2 -> C8(RF_IN->RF_A). Теперь C8 берёт сигнал с LNA_IN.
for p in COMMON:
    if p["ref"] == "C8":
        p["pins"] = {"1": "RF_PICO", "2": "RF_A"}

PICO = [
    dict(ref="U1", sym="esp32_pico:ESP32-PICO-D4", value="ESP32-PICO-D4", fp="esp32_proj:ESP32-PICO-D4",
         lcsc="C2020",
         pins={
             # RF
             "2": "RF_PICO",
             # power (все VDDA/VDD3P3 -> +3V3; VDD_SDIO -> его развязка)
             "1": "+3V3", "3": "+3V3", "4": "+3V3", "19": "+3V3", "37": "+3V3", "43": "+3V3", "46": "+3V3",
             "26": "VDD_SDIO",
             # управление/загрузка
             "9": "EN", "23": "IO0", "40": "U0RXD", "41": "U0TXD",
             # усилитель
             "36": "FEM_TXEN",   # IO23 -> TXEN
             "35": "FEM_RXEN",   # IO18 -> RXEN
             # выведенные GPIO (на гребёнки J3/J4, те же имена что в rev A)
             "5": "SENSOR_VP", "8": "SENSOR_VN", "10": "IO34", "11": "IO35", "12": "IO32",
             "13": "IO33", "14": "IO25", "15": "IO26", "16": "IO27", "17": "IO14", "18": "IO12",
             "20": "IO13", "21": "IO15", "22": "IO2", "24": "IO4", "34": "IO5", "38": "IO19",
             "39": "IO22", "42": "IO21",
             "49": "GND",
         },
         # флеш внутри корпуса + сенсорные CAP + XTAL/CAP NC -> не разводим
         nc=["6", "7", "25", "27", "28", "29", "30", "31", "32", "33", "44", "45", "47", "48"]),
    # Развязка питания PICO (у голого чипа своя, модуль её прятал)
    dict(ref="C40", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525", pins={"1": "+3V3", "2": "GND"}),
    dict(ref="C41", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525", pins={"1": "+3V3", "2": "GND"}),
    dict(ref="C42", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525", pins={"1": "+3V3", "2": "GND"}),
    dict(ref="C43", sym="Device:C", value="1uF", fp=C0402, lcsc="C52923", pins={"1": "+3V3", "2": "GND"}),
    dict(ref="C44", sym="Device:C", value="10uF", fp=C0603, lcsc="C19702", pins={"1": "+3V3", "2": "GND"}),
    dict(ref="C45", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525", pins={"1": "VDD_SDIO", "2": "GND"}),
    # strapping-подтяжки (у голого чипа обязательны): IO0 up, IO2 down, IO12(MTDI) down, IO15 up
    dict(ref="R40", sym="Device:R", value="10k", fp=R0402, lcsc="C25744", pins={"1": "+3V3", "2": "IO0"}),
    dict(ref="R41", sym="Device:R", value="10k", fp=R0402, lcsc="C25744", pins={"1": "IO2", "2": "GND"}),
    dict(ref="R42", sym="Device:R", value="10k", fp=R0402, lcsc="C25744", pins={"1": "IO12", "2": "GND"}),
    dict(ref="R43", sym="Device:R", value="10k", fp=R0402, lcsc="C25744", pins={"1": "+3V3", "2": "IO15"}),
]

PARTS = COMMON + PICO
PWR_FLAG_NETS = ["GND", "VBUS", "+5V", "+3V3_RF", "VDD_SDIO"]
RF_NETS = ["RF_PICO", "RF_A", "RF_B", "RF_C", "RF_D", "RF_OUT"]
PROJECT = "esp32_fem_pico"
TITLE = "ESP32-PICO Wi-Fi FEM board rev B (no pigtail)"

# Размещение новых деталей (остальные refs берут координаты rev A из gen_pcb.PLACE)
# Развязку — вплотную к сторонам U1 (локальные якори +3V3 у каждой группы питания),
# strapping-резисторы у своих выводов на нижней кромке.
PLACE_EXTRA = {
    "C40": (15.0, 15.6, None),   # у верхних +3V3 (выв.37/43/46)
    "C41": (8.6, 19.0, None),    # у левых +3V3 (выв.1/3/4)
    "C42": (8.6, 21.5, None),    # левый, доп.
    "C43": (8.6, 24.0, None),    # 1uF слева
    "C44": (21.4, 19.0, None),   # 10uF справа (у VDD3P3_CPU выв.37 район)
    "C45": (21.4, 26.0, None),   # VDD_SDIO (выв.26, низ-право)
    "R40": (11.5, 27.2, None),   # IO0
    "R41": (13.5, 27.2, None),   # IO2
    "R42": (15.5, 27.2, None),   # IO12
    "R43": (17.5, 27.2, None),   # IO15
}
# ВЧ-тракт разводит freerouting (RF идёт с вывода чипа, не хардкодим)
HAND_RF = False


# Предразводка трудных цепей ДО freerouting (он разведёт остальное в обход).
# Верхние +3V3-выводы U1 (37/43/46) при шаге 0.5 мм не врезать переходными,
# поэтому тянем шину +3V3 над чипом к C40 на верхнем слое.
_Y = 16.6
PREROUTE = [
    {"net": "+3V3", "points": [("U1", "46"), (13.25, _Y), (17.75, _Y), ("U1", "37")], "w": 0.3},
    {"net": "+3V3", "points": [("U1", "43"), (14.75, _Y)], "w": 0.3},
    {"net": "+3V3", "points": [(15.0, _Y), ("C40", "1")], "w": 0.3},
]
