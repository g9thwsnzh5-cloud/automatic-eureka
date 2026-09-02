"""Вариант на 1 Вт: ESP32-WROOM-32U + Qorvo QPF4219 (PA+LNA+SP2T, 5 В).

Схема ВЧ-части воспроизводит открытый (GPL) проект ESP32-M1 Reach Out
(Bison Science), но только Wi-Fi (Bluetooth-тракт убран). Передняя часть
(модуль ESP32, USB-C, CH340C, автосброс, питание 3.3 В) взята без изменений
из rev A (design.py) — она проверена по библиотечным футпринтам KiCad.

ВНИМАНИЕ, посадочные места помечены как «проверить»:
  - QPF4219: QFN-24 3x5 мм. В открытых библиотеках KiCad такого нет; здесь
    подставлен ближайший QFN-24 4x5 как ЗАГЛУШКА. Перед заказом заменить на
    реальный футпринт (EasyEDA/LCSC C471154 или даташит Qorvo).
  - RFSW8009 (SP2T переключатель ESP32<->PA/LNA): футпринт SC-70-6 как
    приближение; сверить с даташитом.
  - Выходной фильтр — LTCC BPF 2.45 ГГц (как DEA162450), корпус 0603.
Пока эти три места не подтверждены, файл — СХЕМА и BOM для доводки в EasyEDA,
а не готовая к заказу плата.

Мощность 1 Вт (30 дБм) на 2.4 ГГц в Израиле и ЕС вне закона (лимит ~100 мВт
ЭИИМ). Плата только для лаборатории/по лицензии; в прошивке мощность ESP32
крутится вниз, а PA держать в линейном режиме.

Питание PA: VCC берётся от USB 5 В (net V_PA) через ферритовую бусину и
крупную развязку. QPF4219 хочет >=4.75 В; USB даёт ~5 В. Для чистого питания
в rev B лучше поставить LDO (как TPS7A5201 в оригинале) — помечено в доке.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import design as _base  # noqa: E402

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
L0402 = "Inductor_SMD:L_0402_1005Metric"
L0805 = "Inductor_SMD:L_0805_2012Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
SC70_6 = "Package_TO_SOT_SMD:SOT-363_SC-70-6"           # ЗАГЛУШКА под RFSW8009
QFN24 = "Package_DFN_QFN:QFN-24-1EP_4x5mm_P0.5mm_EP2.65x3.65mm_ThermalVias"  # ЗАГЛУШКА под QPF4219 3x5
UFL = "Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical"
SMA = "Connector_Coaxial:SMA_Amphenol_132289_EdgeMount"

# Берём всю «переднюю» часть rev A, кроме её ВЧ-секции (её меняем целиком).
RF_REFS_REVA = {"J2", "C8", "R9", "R8", "R10", "U4", "C12", "C13", "L1", "C14",
                "J5", "FB1", "C11", "C9", "C10", "R11", "R12", "R13", "D3", "TP1", "TP2"}
COMMON = [dict(p) for p in _base.PARTS if p["ref"] not in RF_REFS_REVA]

# ESP32: GPIO23 (pin37) -> TX_EN, GPIO18 (pin30) -> RX_EN (как в rev A).
for p in COMMON:
    if p["ref"] == "U1":
        p["pins"]["37"] = "TX_EN"
        p["pins"]["30"] = "RX_EN"
    # D1 rev A даёт +5V после диода для 3.3В-стабилизатора; для PA берём чистый VBUS.

RF_1W = [
    # Вход с модуля ESP32 -> SP2T -> {PA_IN, LNA_OUT}
    dict(ref="J2", sym="Connector:Conn_Coaxial", value="U.FL RF_IN", fp=UFL, lcsc="C88374",
         pins={"1": "RF_ESP", "2": "GND"}),
    dict(ref="C20", sym="Device:C", value="100pF", fp=C0402, lcsc="C1546",
         pins={"1": "RF_ESP", "2": "SW_COM"}),
    # RFSW8009 SP2T (даташит Qorvo Rev E): 1=RF1, 2=GND, 3=RF2, 4=VCONT2, 5=RFC, 6=VCONT1
    # Таблица: RF1-RFC при VCONT1=H (TX), RF2-RFC при VCONT2=H (RX)
    dict(ref="U10", sym="esp32_1w:RFSW8009", value="RFSW8009", fp="esp32_proj:RFSW8009_DFN6_1.86x1.5", lcsc="",
         pins={"5": "SW_COM", "1": "TX_PATH", "3": "RX_PATH", "6": "TX_EN", "4": "RX_EN", "2": "GND"}),
    dict(ref="C21", sym="Device:C", value="100pF", fp=C0402, lcsc="C1546",
         pins={"1": "TX_PATH", "2": "ATT_IN"}),
    # Пи-аттенюатор 6 дБ перед TX_IN (QPF4219: abs.max +12 дБм, для +28 дБм на выходе нужно ~-5 дБм)
    dict(ref="R22", sym="Device:R", value="39R", fp=R0402, lcsc="", pins={"1": "ATT_IN", "2": "PA_IN"}),
    dict(ref="R23", sym="Device:R", value="150R", fp=R0402, lcsc="", pins={"1": "ATT_IN", "2": "GND"}),
    dict(ref="R24", sym="Device:R", value="150R", fp=R0402, lcsc="", pins={"1": "PA_IN", "2": "GND"}),
    dict(ref="C22", sym="Device:C", value="100pF", fp=C0402, lcsc="C1546",
         pins={"1": "RX_PATH", "2": "LNA_OUT"}),
    # QPF4219 QFN-24 (распиновка из GPL-схемы Reach Out, лист 2, U9)
    dict(ref="U9", sym="esp32_1w:QPF4219", value="QPF4219", fp="esp32_proj:QPF4219_QFN24_3x5", lcsc="C471154",
         pins={"2": "PA_IN", "17": "PA_ANT", "15": "RX_OUT", "13": "LNA_IN", "12": "LNA_OUT",
               "4": "TX_EN", "19": "TX_EN", "16": "RX_EN",
               "10": "V_PA", "22": "V_PA", "23": "V_PA", "24": "V_PA",
               "1": "GND", "3": "GND", "7": "GND", "9": "GND", "11": "GND", "14": "GND",
               "18": "GND", "21": "GND", "25": "GND", "8": "GND", "20": "GND"},
         nc=["5", "6"]),
    # Внешняя перемычка RX_OUT -> LNA_IN (можно обойти LNA, поставив 0R/через С)
    dict(ref="C23", sym="Device:C", value="100pF", fp=C0402, lcsc="C1546",
         pins={"1": "RX_OUT", "2": "LNA_IN"}),
    # Выход PA -> антенна через LTCC BPF + пи-фильтр (ретюн под 2-ю гармонику)
    dict(ref="C24", sym="Device:C", value="100pF", fp=C0402, lcsc="C1546",
         pins={"1": "PA_ANT", "2": "ANT_A"}),
    dict(ref="FIL1", sym="Device:L", value="BPF2450", fp=C0603, lcsc="",
         pins={"1": "ANT_A", "2": "ANT_B"}),
    dict(ref="L2", sym="Device:L", value="4.3nH", fp=L0402, lcsc="",
         pins={"1": "ANT_B", "2": "RF_OUT"}),
    dict(ref="C25", sym="Device:C", value="1.8pF", fp=C0402, lcsc="",
         pins={"1": "ANT_B", "2": "GND"}),
    dict(ref="C26", sym="Device:C", value="1.8pF", fp=C0402, lcsc="",
         pins={"1": "RF_OUT", "2": "GND"}),
    dict(ref="J5", sym="Connector:Conn_Coaxial", value="SMA edge", fp=SMA, lcsc="", jlc=False,
         pins={"1": "RF_OUT", "2": "GND"}),
    # Питание PA от USB 5 В (VBUS) через ферритовую бусину
    dict(ref="FB2", sym="Device:FerriteBead", value="100R@100MHz", fp=L0805, lcsc="C1015",
         pins={"1": "VBUS", "2": "V_PA"}),
    dict(ref="C27", sym="Device:C", value="22uF", fp=C0603, lcsc="C45783",
         pins={"1": "V_PA", "2": "GND"}),
    dict(ref="C28", sym="Device:C", value="1uF", fp=C0402, lcsc="C52923",
         pins={"1": "V_PA", "2": "GND"}),
    dict(ref="C29", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525",
         pins={"1": "V_PA", "2": "GND"}),
    dict(ref="C30", sym="Device:C", value="10pF", fp=C0402, lcsc="C32949",
         pins={"1": "V_PA", "2": "GND"}),
    # Развязка у КАЖДОГО вывода питания QPF4219 (по EVB Qorvo: 2.2u + 0.1u на VCC0/1/2, 0.1u на VDD)
    dict(ref="C31", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525", pins={"1": "V_PA", "2": "GND"}),
    dict(ref="C32", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525", pins={"1": "V_PA", "2": "GND"}),
    dict(ref="C33", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525", pins={"1": "V_PA", "2": "GND"}),
    dict(ref="C34", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525", pins={"1": "V_PA", "2": "GND"}),
    dict(ref="C35", sym="Device:C", value="2.2uF", fp=C0402, lcsc="", pins={"1": "V_PA", "2": "GND"}),
    dict(ref="C36", sym="Device:C", value="2.2uF", fp=C0402, lcsc="", pins={"1": "V_PA", "2": "GND"}),
    dict(ref="C37", sym="Device:C", value="2.2uF", fp=C0402, lcsc="", pins={"1": "V_PA", "2": "GND"}),
    # ВЧ-фильтрация линий управления (EVB: 100p на PA_EN; RFSW8009 EVB: 1n на VCONT)
    dict(ref="C38", sym="Device:C", value="1nF", fp=C0402, lcsc="C1523", pins={"1": "TX_EN", "2": "GND"}),
    dict(ref="C39", sym="Device:C", value="1nF", fp=C0402, lcsc="C1523", pins={"1": "RX_EN", "2": "GND"}),
    # Подтяжки управления вниз (PA спит до инициализации)
    dict(ref="R20", sym="Device:R", value="10k", fp=R0402, lcsc="C25744",
         pins={"1": "TX_EN", "2": "GND"}),
    dict(ref="R21", sym="Device:R", value="10k", fp=R0402, lcsc="C25744",
         pins={"1": "RX_EN", "2": "GND"}),
    dict(ref="TP1", sym="Connector:TestPoint", value="TXEN", fp="TestPoint:TestPoint_Pad_1.0x1.0mm", lcsc="", jlc=False,
         pins={"1": "TX_EN"}),
    dict(ref="TP2", sym="Connector:TestPoint", value="RXEN", fp="TestPoint:TestPoint_Pad_1.0x1.0mm", lcsc="", jlc=False,
         pins={"1": "RX_EN"}),
    dict(ref="TP3", sym="Connector:TestPoint", value="V_PA", fp="TestPoint:TestPoint_Pad_1.0x1.0mm", lcsc="", jlc=False,
         pins={"1": "V_PA"}),
]

PARTS = COMMON + RF_1W
PWR_FLAG_NETS = ["GND", "VBUS", "+5V", "V_PA"]
RF_NETS = ["RF_ESP", "SW_COM", "TX_PATH", "RX_PATH", "ATT_IN", "PA_IN", "PA_ANT",
           "RX_OUT", "LNA_IN", "LNA_OUT", "ANT_A", "ANT_B", "RF_OUT"]
PROJECT = "esp32_fem_1w"
TITLE = "ESP32 Wi-Fi 1W front-end (QPF4219) board rev A"
