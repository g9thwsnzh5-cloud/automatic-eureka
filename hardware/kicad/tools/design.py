"""Single source of truth for the ESP32 Wi-Fi FEM board: parts, pins, nets.

Every component is described once here; gen_sch.py turns it into a KiCad
schematic (labels-only style) and gen_pcb.py uses the same data for
placement and part metadata (LCSC numbers, DNP, assembly flags).
"""

# ---------------------------------------------------------------------------
# Footprint shortcuts
R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
L0402 = "Inductor_SMD:L_0402_1005Metric"
L0805 = "Inductor_SMD:L_0805_2012Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
SOD123 = "Diode_SMD:D_SOD-123"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOT223 = "Package_TO_SOT_SMD:SOT-223-3_TabPin2"
SOIC16 = "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm"
QFN16 = "Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm_ThermalVias"
ESP32U = "RF_Module:ESP32-WROOM-32U"
USBC = "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12"
UFL = "Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical"
SMA = "Connector_Coaxial:SMA_Amphenol_132289_EdgeMount"
HDR13 = "Connector_PinHeader_2.54mm:PinHeader_1x13_P2.54mm_Vertical"
SW6 = "Button_Switch_THT:SW_PUSH_6mm"
TP = "TestPoint:TestPoint_Pad_1.0x1.0mm"

# ---------------------------------------------------------------------------
# Components.
#  ref, lib symbol, value, footprint, LCSC, pin->net, options
#  options: dnp=True (do not populate), jlc=False (not assembled by JLCPCB,
#  user solders it), nc=[pins with a no-connect flag]
PARTS = [
    # --- USB and power ------------------------------------------------------
    dict(ref="J1", sym="Connector:USB_C_Receptacle_USB2.0_16P", value="USB-C 16P",
         fp=USBC, lcsc="C165948",
         pins={"A1": "GND", "A4": "VBUS", "A5": "CC1", "B5": "CC2",
               "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DM", "B7": "USB_DM",
               "S1": "GND"}, nc=["A8", "B8"]),
    dict(ref="R1", sym="Device:R", value="5.1k", fp=R0402, lcsc="C25905",
         pins={"1": "CC1", "2": "GND"}),
    dict(ref="R2", sym="Device:R", value="5.1k", fp=R0402, lcsc="C25905",
         pins={"1": "CC2", "2": "GND"}),
    dict(ref="D1", sym="Device:D_Schottky", value="B5819W", fp=SOD123, lcsc="C8598",
         pins={"2": "VBUS", "1": "+5V"}),
    dict(ref="C1", sym="Device:C", value="10uF", fp=C0603, lcsc="C19702",
         pins={"1": "+5V", "2": "GND"}),
    dict(ref="U2", sym="esp32_fem:AMS1117-3.3", value="AMS1117-3.3", fp=SOT223, lcsc="C6186",
         pins={"3": "+5V", "2": "+3V3", "1": "GND"}),
    dict(ref="C2", sym="Device:C", value="10uF", fp=C0603, lcsc="C19702",
         pins={"1": "+3V3", "2": "GND"}),
    dict(ref="C3", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525",
         pins={"1": "+3V3", "2": "GND"}),
    dict(ref="R3", sym="Device:R", value="1k", fp=R0402, lcsc="C11702",
         pins={"1": "+3V3", "2": "LED_PWR"}),
    dict(ref="D2", sym="Device:LED", value="GREEN", fp=LED0603, lcsc="C72043",
         pins={"2": "LED_PWR", "1": "GND"}),

    # --- USB to serial and auto-reset -------------------------------------
    dict(ref="U3", sym="Interface_USB:CH340C", value="CH340C", fp=SOIC16, lcsc="C84681",
         pins={"16": "+5V", "1": "GND", "4": "V3", "5": "USB_DP", "6": "USB_DM",
               "2": "U0RXD", "3": "U0TXD", "13": "DTR", "14": "RTS"},
         nc=["8", "9", "10", "11", "12", "15"]),
    dict(ref="C4", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525",
         pins={"1": "V3", "2": "GND"}),
    dict(ref="R4", sym="Device:R", value="10k", fp=R0402, lcsc="C25744",
         pins={"1": "DTR", "2": "Q1B"}),
    dict(ref="Q1", sym="esp32_fem:S8050_SOT23", value="S8050", fp=SOT23, lcsc="C2150",
         pins={"1": "Q1B", "2": "RTS", "3": "EN"}),
    dict(ref="R5", sym="Device:R", value="10k", fp=R0402, lcsc="C25744",
         pins={"1": "RTS", "2": "Q2B"}),
    dict(ref="Q2", sym="esp32_fem:S8050_SOT23", value="S8050", fp=SOT23, lcsc="C2150",
         pins={"1": "Q2B", "2": "DTR", "3": "IO0"}),

    # --- ESP32 module -----------------------------------------------------
    dict(ref="U1", sym="RF_Module:ESP32-WROOM-32U", value="ESP32-WROOM-32U-N4", fp=ESP32U,
         lcsc="C328062",
         pins={"1": "GND", "2": "+3V3", "3": "EN", "4": "SENSOR_VP", "5": "SENSOR_VN",
               "6": "IO34", "7": "IO35", "8": "IO32", "9": "IO33", "10": "IO25",
               "11": "IO26", "12": "IO27", "13": "IO14", "14": "IO12", "16": "IO13",
               "23": "IO15", "24": "IO2", "25": "IO0", "26": "IO4", "27": "IO16",
               "28": "IO17", "29": "IO5", "30": "FEM_RXEN", "31": "IO19", "33": "IO21",
               "34": "U0RXD", "35": "U0TXD", "36": "IO22", "37": "FEM_TXEN"},
         nc=["17", "18", "19", "20", "21", "22"]),
    dict(ref="C5", sym="Device:C", value="10uF", fp=C0603, lcsc="C19702",
         pins={"1": "+3V3", "2": "GND"}),
    dict(ref="C6", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525",
         pins={"1": "+3V3", "2": "GND"}),
    dict(ref="R6", sym="Device:R", value="10k", fp=R0402, lcsc="C25744",
         pins={"1": "+3V3", "2": "EN"}),
    dict(ref="C7", sym="Device:C", value="1uF", fp=C0402, lcsc="C52923",
         pins={"1": "EN", "2": "GND"}),
    dict(ref="SW1", sym="Switch:SW_Push", value="RESET", fp=SW6, lcsc="", jlc=False,
         pins={"1": "EN", "2": "GND"}),
    dict(ref="SW2", sym="Switch:SW_Push", value="BOOT", fp=SW6, lcsc="", jlc=False,
         pins={"1": "IO0", "2": "GND"}),
    dict(ref="J3", sym="Connector_Generic:Conn_01x13", value="GPIO_L", fp=HDR13, lcsc="", jlc=False,
         pins={"1": "+3V3", "2": "EN", "3": "SENSOR_VP", "4": "SENSOR_VN", "5": "IO34",
               "6": "IO35", "7": "IO32", "8": "IO33", "9": "IO25", "10": "IO26",
               "11": "IO27", "12": "IO14", "13": "GND"}),
    dict(ref="J4", sym="Connector_Generic:Conn_01x13", value="GPIO_R", fp=HDR13, lcsc="", jlc=False,
         pins={"1": "+5V", "2": "GND", "3": "IO12", "4": "IO13", "5": "IO15", "6": "IO2",
               "7": "IO4", "8": "IO16", "9": "IO17", "10": "IO5", "11": "IO19",
               "12": "IO21", "13": "IO22"}),

    # --- RF chain: module U.FL -> pad -> FEM -> filter -> SMA ---------------
    dict(ref="J2", sym="Connector:Conn_Coaxial", value="U.FL RF_IN", fp=UFL, lcsc="C88374",
         pins={"1": "RF_IN", "2": "GND"}),
    dict(ref="C8", sym="Device:C", value="100pF", fp=C0402, lcsc="C1546",
         pins={"1": "RF_IN", "2": "RF_A"}),
    dict(ref="R9", sym="Device:R", value="DNP", fp=R0402, lcsc="", dnp=True,
         pins={"1": "RF_A", "2": "GND"}),
    dict(ref="R8", sym="Device:R", value="0R", fp=R0402, lcsc="C17168",
         pins={"1": "RF_A", "2": "RF_B"}),
    dict(ref="R10", sym="Device:R", value="DNP", fp=R0402, lcsc="", dnp=True,
         pins={"1": "RF_B", "2": "GND"}),
    dict(ref="U4", sym="esp32_fem:RFX2401C", value="RFX2401C", fp=QFN16, lcsc="C19213",
         pins={"4": "RF_B", "5": "FEM_TXEN", "6": "FEM_RXEN", "10": "RF_C",
               "14": "+3V3_RF", "16": "+3V3_RF",
               "2": "GND", "3": "GND", "8": "GND", "9": "GND", "11": "GND", "13": "GND",
               "17": "GND"},
         nc=["1", "7", "12", "15"]),
    dict(ref="C12", sym="Device:C", value="100pF", fp=C0402, lcsc="C1546",
         pins={"1": "RF_C", "2": "RF_D"}),
    dict(ref="C13", sym="Device:C", value="1.2pF", fp=C0402, lcsc="C327292",
         pins={"1": "RF_D", "2": "GND"}),
    dict(ref="L1", sym="Device:L", value="3nH", fp=L0402, lcsc="C269824",
         pins={"1": "RF_D", "2": "RF_OUT"}),
    dict(ref="C14", sym="Device:C", value="1.2pF", fp=C0402, lcsc="C327292",
         pins={"1": "RF_OUT", "2": "GND"}),
    dict(ref="J5", sym="Connector:Conn_Coaxial", value="SMA edge", fp=SMA, lcsc="", jlc=False,
         pins={"1": "RF_OUT", "2": "GND"}),

    # --- FEM supply and control -------------------------------------------
    dict(ref="FB1", sym="Device:FerriteBead", value="100R@100MHz", fp=L0805, lcsc="C1015",
         pins={"1": "+3V3", "2": "+3V3_RF"}),
    dict(ref="C11", sym="Device:C", value="10uF", fp=C0603, lcsc="C19702",
         pins={"1": "+3V3_RF", "2": "GND"}),
    dict(ref="C9", sym="Device:C", value="100nF", fp=C0402, lcsc="C1525",
         pins={"1": "+3V3_RF", "2": "GND"}),
    dict(ref="C10", sym="Device:C", value="10pF", fp=C0402, lcsc="C32949",
         pins={"1": "+3V3_RF", "2": "GND"}),
    dict(ref="R11", sym="Device:R", value="100k", fp=R0402, lcsc="C25741",
         pins={"1": "FEM_TXEN", "2": "GND"}),
    dict(ref="R12", sym="Device:R", value="100k", fp=R0402, lcsc="C25741",
         pins={"1": "FEM_RXEN", "2": "GND"}),
    dict(ref="R13", sym="Device:R", value="1k", fp=R0402, lcsc="C11702",
         pins={"1": "FEM_TXEN", "2": "TXLED"}),
    dict(ref="D3", sym="Device:LED", value="RED TX", fp=LED0603, lcsc="C2286",
         pins={"2": "TXLED", "1": "GND"}),
    dict(ref="TP1", sym="Connector:TestPoint", value="TXEN", fp=TP, lcsc="", jlc=False,
         pins={"1": "FEM_TXEN"}),
    dict(ref="TP2", sym="Connector:TestPoint", value="RXEN", fp=TP, lcsc="", jlc=False,
         pins={"1": "FEM_RXEN"}),
]

# Nets that need a PWR_FLAG so ERC sees a driver.
PWR_FLAG_NETS = ["GND", "VBUS", "+5V", "+3V3_RF"]

# Nets routed as 50 ohm microstrip (net class "RF").
RF_NETS = ["RF_IN", "RF_A", "RF_B", "RF_C", "RF_D", "RF_OUT"]

PROJECT = "esp32_fem"
TITLE = "ESP32 Wi-Fi front-end (PA/LNA) board"
