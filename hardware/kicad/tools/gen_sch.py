#!/usr/bin/env python3
"""Generate esp32_fem.kicad_sch (KiCad 7 format) from design.py.

Style: every symbol is placed on a grid and each pin gets a short wire stub
ending in a net label.  No long wires - the netlist is defined by labels.
Run:  python3 tools/gen_sch.py   (from hardware/kicad)
"""
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))
import os as _os, importlib as _il  # noqa: E402
_DM = _os.environ.get("DESIGN", "design")
_d = _il.import_module(_DM)
PARTS, PWR_FLAG_NETS, PROJECT, TITLE = [getattr(_d, n) for n in "PARTS, PWR_FLAG_NETS, PROJECT, TITLE".split(", ")]  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD_DIR = os.path.dirname(HERE)
SYSLIB = "/usr/share/kicad/symbols"
LOCAL_LIB = os.path.join(KICAD_DIR, "lib", "esp32_fem.kicad_sym")
GRID = 1.27


def u():
    return str(uuid.uuid4())


def block(s, start):
    d = 0
    for j in range(start, len(s)):
        if s[j] == "(":
            d += 1
        elif s[j] == ")":
            d -= 1
            if d == 0:
                return s[start:j + 1]
    raise ValueError("unbalanced")


_libcache = {}


def lib_text(lib):
    if lib not in _libcache:
        path = os.path.join(KICAD_DIR, "lib", lib + ".kicad_sym") if lib.startswith("esp32_") else os.path.join(SYSLIB, lib + ".kicad_sym")
        _libcache[lib] = open(path).read()
    return _libcache[lib]


def symbol_def(sym):
    """Return the top-level (symbol "name" ...) block from its library."""
    lib, name = sym.split(":")
    s = lib_text(lib)
    i = s.find('(symbol "%s"' % name)
    if i < 0:
        raise KeyError(sym)
    b = block(s, i)
    if "(extends " in b[:200]:
        raise ValueError("%s is a derived symbol; add a flat copy to esp32_fem lib" % sym)
    return b


def symbol_pins(sym):
    """[(number, name, type, x, y, angle, hidden)] in library coordinates."""
    b = symbol_def(sym)
    pins = []
    for m in re.finditer(r"\(pin\s+(\w+)\s+\w+\s*\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)"
                         r"\s*\(length\s+[-\d.]+\)\s*(hide)?", b):
        pb = block(b, m.start())
        name = re.search(r'\(name\s+"([^"]*)"', pb).group(1)
        num = re.search(r'\(number\s+"([^"]*)"', pb).group(1)
        pins.append((num, name, m.group(1), float(m.group(2)), float(m.group(3)),
                     int(float(m.group(4))), bool(m.group(5))))
    return pins


def snap(v):
    return round(round(v / GRID) * GRID, 2)


# ---------------------------------------------------------------------------
# Schematic layout: (ref -> (x, y)) in mm on A3, symbols at rotation 0.
LAYOUT = {
    # power row
    "J1": (35, 60), "R1": (65, 60), "R2": (75, 60), "D1": (95, 60), "C1": (110, 60),
    "U2": (130, 60), "C2": (150, 60), "C3": (160, 60), "R3": (175, 60), "D2": (190, 60),
    # usb-serial row
    "U3": (45, 120), "C4": (70, 120), "R4": (85, 120), "Q1": (100, 120), "R5": (120, 120),
    "Q2": (135, 120), "R6": (155, 120), "C7": (165, 120), "SW1": (185, 120), "SW2": (205, 120),
    "C5": (225, 120), "C6": (235, 120),
    # esp32 + headers
    "U1": (300, 110), "J3": (350, 95), "J4": (380, 95),
    # rf row
    "J2": (30, 215), "C8": (45, 215), "R9": (55, 215), "R8": (65, 215), "R10": (75, 215),
    "U4": (110, 215), "C12": (140, 215), "C13": (150, 215), "L1": (160, 215), "C14": (170, 215),
    "J5": (190, 215),
    # fem supply/control row
    "FB1": (230, 215), "C11": (240, 215), "C9": (250, 215), "C10": (260, 215),
    "R11": (280, 215), "R12": (290, 215), "R13": (305, 215), "D3": (320, 215),
    "TP1": (340, 215), "TP2": (350, 215),
}

NOTES = [
    (20, 20, "ESP32 Wi-Fi front-end board, rev A.  Labels-only schematic: same net name = same net."),
    (20, 25, "Power: USB-C 5V -> D1 -> AMS1117 3.3V.  FEM supply is filtered through FB1 (+3V3_RF)."),
    (20, 30, "USB-serial: CH340C with DTR/RTS auto-reset (Q1/Q2), same as ESP32-DevKitC."),
    (20, 170, "RF: ESP32-WROOM-32U U.FL -> short U.FL-U.FL pigtail -> J2 -> C8 -> pad R8/R9/R10 (0R / DNP)"),
    (20, 175, "-> RFX2401C (PA 20 dBm, LNA 12 dB) -> C12 -> pi filter L1/C13/C14 -> J5 SMA edge."),
    (20, 180, "TX/RX switching: GPIO23 -> TXEN, GPIO18 -> RXEN via esp_wifi_set_ant_gpio() (see firmware/)."),
    (20, 185, "Keep ESP32 TX power at ~+8 dBm max with 0R pad; RFX2401C input P1dB is about +5 dBm."),
]


def main():
    root = u()
    out = []
    w = out.append
    w('(kicad_sch (version 20230121) (generator eeschema)')
    w('  (uuid "%s")' % root)
    w('  (paper "A3")')
    w('  (title_block (title "%s") (date "2026-09-01") (rev "A")' % TITLE)
    w('    (comment 1 "Rev A - first prototype, 4-layer JLCPCB")')
    w('  )')

    # lib_symbols
    used = []
    for p in PARTS:
        if p["sym"] not in used:
            used.append(p["sym"])
    used.append("power:PWR_FLAG")
    w('  (lib_symbols')
    for sym in used:
        b = symbol_def(sym)
        lib, name = sym.split(":")
        b = b.replace('(symbol "%s"' % name, '(symbol "%s"' % sym, 1)
        w("    " + b.replace("\n", "\n    "))
    w('  )')

    labels, wires, ncs, syms, texts = [], [], [], [], []

    def place_symbol(sym, ref, value, fp, X, Y, props=None, dnp=False, jlc=True, lcsc=""):
        pins = symbol_pins(sym)
        s = []
        s.append('  (symbol (lib_id "%s") (at %s %s 0) (unit 1) (in_bom yes) (on_board yes) (dnp %s)'
                 % (sym, X, Y, "yes" if dnp else "no"))
        s.append('    (uuid "%s")' % u())
        s.append('    (property "Reference" "%s" (at %s %s 0) (effects (font (size 1.27 1.27)) (justify left)))'
                 % (ref, X + 2.54, Y - 2.54))
        s.append('    (property "Value" "%s" (at %s %s 0) (effects (font (size 1.27 1.27)) (justify left)))'
                 % (value, X + 2.54, Y + 2.54))
        s.append('    (property "Footprint" "%s" (at %s %s 0) (effects (font (size 1.27 1.27)) hide))'
                 % (fp, X, Y))
        s.append('    (property "Datasheet" "~" (at %s %s 0) (effects (font (size 1.27 1.27)) hide))' % (X, Y))
        s.append('    (property "LCSC" "%s" (at %s %s 0) (effects (font (size 1.27 1.27)) hide))' % (lcsc, X, Y))
        s.append('    (property "JLC_ASSEMBLE" "%s" (at %s %s 0) (effects (font (size 1.27 1.27)) hide))'
                 % ("yes" if jlc else "no", X, Y))
        for num, *_ in pins:
            s.append('    (pin "%s" (uuid "%s"))' % (num, u()))
        s.append('    (instances (project "%s" (path "/%s" (reference "%s") (unit 1))))' % (PROJECT, root, ref))
        s.append('  )')
        syms.append("\n".join(s))
        return pins

    auto_i = [0]
    def auto_xy():
        col = auto_i[0] % 12
        row = auto_i[0] // 12
        auto_i[0] += 1
        return (20 + col * 30, 250 + row * 35)
    for p in PARTS:
        X, Y = LAYOUT.get(p["ref"], None) or auto_xy()
        X, Y = snap(X), snap(Y)
        pins = place_symbol(p["sym"], p["ref"], p["value"], p["fp"], X, Y,
                            dnp=p.get("dnp", False), jlc=p.get("jlc", True), lcsc=p.get("lcsc", ""))
        nc = set(p.get("nc", []))
        for num, name, ptype, px, py, ang, hidden in pins:
            ex, ey = snap(X + px), snap(Y - py)
            if num in nc:
                ncs.append('  (no_connect (at %s %s) (uuid "%s"))' % (ex, ey, u()))
                continue
            net = p["pins"].get(num)
            if net is None:
                if ptype == "no_connect":
                    continue
                if hidden:
                    continue
                raise ValueError("%s pin %s (%s) has no net" % (p["ref"], num, name))
            dx, dy = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[ang]
            fx, fy = snap(ex + dx * 2.54), snap(ey + dy * 2.54)
            wires.append('  (wire (pts (xy %s %s) (xy %s %s)) (stroke (width 0) (type default)) (uuid "%s"))'
                         % (ex, ey, fx, fy, u()))
            rot, just = {(1, 0): (0, "left"), (-1, 0): (180, "right"),
                         (0, -1): (90, "left"), (0, 1): (270, "right")}[(dx, dy)]
            labels.append('  (label "%s" (at %s %s %s) (effects (font (size 1.27 1.27)) (justify %s bottom)) (uuid "%s"))'
                          % (net, fx, fy, rot, just, u()))

    # PWR_FLAGs
    x0 = 220
    for i, net in enumerate(PWR_FLAG_NETS):
        X, Y = snap(x0 + i * 15), snap(55)
        place_symbol("power:PWR_FLAG", "#FLG%d" % (i + 1), "PWR_FLAG", "", X, Y, jlc=False)
        wires.append('  (wire (pts (xy %s %s) (xy %s %s)) (stroke (width 0) (type default)) (uuid "%s"))'
                     % (X, Y, X, snap(Y + 2.54), u()))
        labels.append('  (label "%s" (at %s %s 270) (effects (font (size 1.27 1.27)) (justify right bottom)) (uuid "%s"))'
                      % (net, X, snap(Y + 2.54), u()))

    for x, y, t in NOTES:
        texts.append('  (text "%s" (at %s %s 0) (effects (font (size 2 2)) (justify left bottom)) (uuid "%s"))'
                     % (t.replace('"', "'"), x, y, u()))

    out.extend(texts)
    out.extend(ncs)
    out.extend(wires)
    out.extend(labels)
    out.extend(syms)
    w('  (sheet_instances (path "/" (page "1")))')
    w(')')
    path = os.path.join(KICAD_DIR, PROJECT + ".kicad_sch")
    open(path, "w").write("\n".join(out) + "\n")
    print("wrote", path, "symbols:", len(syms), "labels:", len(labels))


if __name__ == "__main__":
    main()
