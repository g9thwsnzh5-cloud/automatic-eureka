#!/usr/bin/env python3
"""Build esp32_fem.kicad_pcb with the pcbnew Python API (KiCad 7).

Steps: read the exported netlist, place every footprint at the coordinates
below, draw the outline, hand-route the 50 ohm RF path on F.Cu, add GND
pours on all four layers and save.  Non-RF nets are routed afterwards by
route.py (freerouting) - see that file.

Run from hardware/kicad:
    kicad-cli sch export netlist --format kicadsexpr -o build/esp32_fem.net esp32_fem.kicad_sch
    python3 tools/gen_pcb.py
"""
import os
import re
import sys

import pcbnew
from pcbnew import FromMM, VECTOR2I, VECTOR2I_MM

sys.path.insert(0, os.path.dirname(__file__))
import os as _os, importlib as _il  # noqa: E402
_DM = _os.environ.get("DESIGN", "design")
_d = _il.import_module(_DM)
PARTS, RF_NETS, PROJECT = [getattr(_d, n) for n in "PARTS, RF_NETS, PROJECT".split(", ")]  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD_DIR = os.path.dirname(HERE)
BUILD = os.path.join(KICAD_DIR, "build")
FPLIB = "/usr/share/kicad/footprints"

BOARD_W, BOARD_H = 64.0, 52.0
RF_W = 0.38            # 50 ohm microstrip on JLC04161H-7628 (F.Cu over In1 GND)
RF_IN_Y = 10.25        # y of the input line (U4 pin 4)
RF_OUT_Y = 9.75        # y of the output line (U4 pin 10)

# ref -> (x, y, rot).  rot=None on 2-pin parts means "pin 1 must be on top"
PLACE = {
    # ESP32 module and its support parts (left half)
    "U1": (15.0, 21.0, 0), "J3": (2.54, 10.0, 0),
    "C5": (9.0, 9.0, 0), "C6": (12.5, 9.0, 0), "R6": (9.0, 6.4, 0), "C7": (12.5, 6.4, 0),
    "SW1": (9.5, 42.0, 0), "SW2": (19.1, 42.0, 0),
    # USB, serial bridge, auto reset (bottom middle)
    "J1": (33.0, 47.8, 0), "R1": (28.5, 41.0, 0), "R2": (31.0, 41.0, 0),
    "U3": (33.5, 33.0, 0), "C4": (28.5, 30.0, 0),
    "R4": (38.3, 29.05, 0), "Q1": (41.5, 30.0, 0), "R5": (38.3, 34.05, 0), "Q2": (41.5, 35.0, 0),
    # power (bottom right)
    "D1": (41.5, 41.8, 0), "U2": (48.0, 37.0, 0), "C1": (47.0, 41.8, 0),
    "C2": (47.0, 32.5, 0), "C3": (50.5, 32.5, 0), "R3": (54.5, 35.0, None), "D2": (54.5, 40.0, 90),
    "J4": (61.0, 18.0, 0),
    # RF chain along the top edge
    "J2": (27.3, RF_IN_Y, 180), "C8": (30.5, RF_IN_Y, 0), "R9": (32.6, 11.7, None),
    "R8": (34.4, RF_IN_Y, 0), "R10": (36.4, 11.7, None), "U4": (40.0, 9.5, 0),
    "C12": (44.0, RF_OUT_Y, 0), "C13": (46.0, 11.2, None), "L1": (47.6, RF_OUT_Y, 0),
    "C14": (49.7, 11.2, None), "J5": (60.8, RF_OUT_Y, 0),
    # FEM supply (above U4) and control (below U4)
    "C9": (38.2, 6.4, "pin2top"), "C10": (41.3, 6.4, "pin2top"), "FB1": (39.75, 4.3, None),
    "C11": (43.6, 4.3, 0),
    "R11": (38.0, 14.2, None), "R12": (42.5, 14.2, None), "TP1": (36.0, 17.0, 0),
    "TP2": (43.5, 17.0, 0), "R13": (46.5, 14.0, 0), "D3": (49.6, 14.0, 180),
}
HOLES = [(4.0, 4.0), (52.0, 4.0), (4.0, 48.0), (52.0, 48.5)]

PLACE = {**PLACE, **getattr(_d, "PLACE_EXTRA", {})}
HAND_RF = getattr(_d, "HAND_RF", True)


def read_netlist(path):
    s = open(path).read()
    nets = {}
    for chunk in s.split("(net (code")[1:]:
        name = re.search(r'\(name "([^"]+)"', chunk).group(1)
        for ref, pin in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', chunk):
            nets.setdefault(name, []).append((ref, pin))
    return nets


def main():
    os.makedirs(BUILD, exist_ok=True)
    nets = read_netlist(os.path.join(BUILD, PROJECT + ".net"))
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.m_MinClearance = FromMM(0.127)
    ds.m_TrackMinWidth = FromMM(0.127)
    ds.m_ViasMinSize = FromMM(0.5)
    ds.m_MinThroughDrill = FromMM(0.2)   # WROOM-32U paddle vias are 0.2 mm (JLC 4-layer ok)
    ds.m_CopperEdgeClearance = FromMM(0.2)
    ds.m_SolderMaskMinWidth = 0
    try:
        nc = ds.m_NetSettings.m_DefaultNetClass
        nc.SetClearance(FromMM(0.15))
        nc.SetTrackWidth(FromMM(0.25))
        nc.SetViaDiameter(FromMM(0.6))
        nc.SetViaDrill(FromMM(0.3))
    except Exception as e:  # pragma: no cover
        print("netclass API not available:", e)

    # nets --------------------------------------------------------------
    netmap = {}
    pin2net = {}
    for name, nodes in nets.items():
        clean = name[1:] if name.startswith("/") else name
        ni = pcbnew.NETINFO_ITEM(board, clean)
        board.Add(ni)
        netmap[clean] = ni
        for ref, pin in nodes:
            pin2net[(ref, pin)] = ni

    # footprints ----------------------------------------------------------
    fps = {}
    for p in PARTS:
        lib, name = p["fp"].split(":")
        lib_dir = os.path.join(KICAD_DIR, "lib", lib + ".pretty") if lib == "esp32_proj" else os.path.join(FPLIB, lib + ".pretty")
        fp = pcbnew.FootprintLoad(lib_dir, name)
        if fp is None:
            raise SystemExit("footprint not found: " + p["fp"])
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(p["ref"])
        fp.SetValue(p["value"])
        x, y, rot = PLACE[p["ref"]]
        fp.SetPosition(VECTOR2I_MM(x, y))
        if rot is None or rot == "pin2top":
            # 2-pin part standing vertically: choose the rotation that puts pad 1 (or 2) on top
            top = "2" if rot == "pin2top" else "1"
            fp.SetOrientationDegrees(90)
            pads = {pd.GetNumber(): pd.GetPosition() for pd in fp.Pads()}
            if pads[top].y > pads["1" if top == "2" else "2"].y:
                fp.SetOrientationDegrees(270)
        else:
            fp.SetOrientationDegrees(rot)
        for pd in fp.Pads():
            ni = pin2net.get((p["ref"], pd.GetNumber()))
            if ni is not None:
                pd.SetNet(ni)
        attrs = fp.GetAttributes()
        if p.get("dnp"):
            attrs |= pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
            if hasattr(pcbnew, "FP_DNP"):
                attrs |= pcbnew.FP_DNP
        if not p.get("jlc", True):
            attrs |= pcbnew.FP_EXCLUDE_FROM_POS_FILES
        fp.SetAttributes(attrs)
        r = fp.Reference()
        r.SetTextSize(VECTOR2I(FromMM(0.8), FromMM(0.8)))
        r.SetTextThickness(FromMM(0.12))
        fp.Value().SetVisible(False)
        fp.SetProperty("LCSC", p.get("lcsc", ""))
        board.Add(fp)
        fps[p["ref"]] = fp

    for i, (x, y) in enumerate(HOLES):
        fp = pcbnew.FootprintLoad(os.path.join(FPLIB, "MountingHole.pretty"), "MountingHole_3.2mm_M3")
        fp.SetFPID(pcbnew.LIB_ID("MountingHole", "MountingHole_3.2mm_M3"))
        fp.SetReference("H%d" % (i + 1))
        fp.SetValue("M3")
        fp.SetPosition(VECTOR2I_MM(x, y))
        fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
        board.Add(fp)

    def pad_pos(ref, num):
        for pd in fps[ref].Pads():
            if pd.GetNumber() == num:
                return pd.GetPosition()
        raise KeyError((ref, num))

    # outline -------------------------------------------------------------
    corners = [(0, 0), (BOARD_W, 0), (BOARD_W, BOARD_H), (0, BOARD_H)]
    for i in range(4):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(VECTOR2I_MM(*corners[i]))
        seg.SetEnd(VECTOR2I_MM(*corners[(i + 1) % 4]))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(FromMM(0.1))
        board.Add(seg)

    # silkscreen texts ----------------------------------------------------
    def text(s, x, y, layer=pcbnew.F_SilkS, size=1.0, rot=0):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetPosition(VECTOR2I_MM(x, y))
        t.SetLayer(layer)
        t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
        t.SetTextThickness(FromMM(0.15))
        t.SetTextAngleDegrees(rot)
        board.Add(t)

    text("ESP32 Wi-Fi FEM  rev A", 51.0, 24.0, size=1.2)
    text("RF IN", 27.3, 12.9, size=0.8)
    text("ANT", 58.0, 2.5, size=0.8)
    text("USB", 32.0, 40.5, size=0.8)
    text("RST", 10.75, 40.5, size=0.8)
    text("BOOT", 19.75, 40.5, size=0.8)

    # RF hand routing on F.Cu ---------------------------------------------
    def track(a, b, net, w=RF_W, layer=pcbnew.F_Cu):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(a)
        t.SetEnd(b)
        t.SetWidth(FromMM(w))
        t.SetLayer(layer)
        t.SetNet(netmap[net])
        board.Add(t)

    def via(x, y, net, d=0.6, drill=0.3):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(VECTOR2I_MM(x, y))
        v.SetWidth(FromMM(d))
        v.SetDrill(FromMM(drill))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(netmap[net])
        board.Add(v)

    def line(points, net, w=RF_W):
        pts = [pad_pos(*p) if isinstance(p, tuple) and isinstance(p[0], str) else VECTOR2I_MM(*p)
               for p in points]
        for a, b in zip(pts, pts[1:]):
            track(a, b, net, w=w)

    if HAND_RF:
        # input: U.FL -> C8 -> R8 -> U4.4, with shunt stubs to R9/R10
        line([("J2", "1"), ("C8", "1")], "RF_IN")
        line([("C8", "2"), ("R8", "1")], "RF_A")
        line([("R9", "1"), (32.6, RF_IN_Y)], "RF_A")
        line([("R8", "2"), (37.6, RF_IN_Y)], "RF_B")
        track(VECTOR2I_MM(37.6, RF_IN_Y), pad_pos("U4", "4"), "RF_B", w=0.2)   # neck into the QFN pad
        line([("R10", "1"), (36.4, RF_IN_Y)], "RF_B")
        # output: U4.10 -> C12 -> L1 (pi filter) -> SMA
        track(pad_pos("U4", "10"), VECTOR2I_MM(42.4, RF_OUT_Y), "RF_C", w=0.2)  # neck out of the QFN pad
        line([(42.4, RF_OUT_Y), ("C12", "1")], "RF_C")
        line([("C12", "2"), ("L1", "1")], "RF_D")
        line([("C13", "1"), (46.0, RF_OUT_Y)], "RF_D")
        line([("L1", "2"), ("J5", "1")], "RF_OUT")
        line([("C14", "1"), (49.7, RF_OUT_Y)], "RF_OUT")

        # GND vias for the RF shunt parts and the FEM ground paddle
        for ref in ("R9", "R10", "C13", "C14"):
            pp = pad_pos(ref, "2")
            via(pp.x / 1e6, pp.y / 1e6 + 0.75, "GND")
            track(pp, VECTOR2I_MM(pp.x / 1e6, pp.y / 1e6 + 0.75), "GND", w=0.3)
        for ref in ("C9", "C10"):
            pp = pad_pos(ref, "2")
            via(pp.x / 1e6, pp.y / 1e6 - 0.8, "GND")
            track(pp, VECTOR2I_MM(pp.x / 1e6, pp.y / 1e6 - 0.8), "GND", w=0.3)
        # stitching vias along the RF lines (ground fence)
        fence = []
        fence += [(x, 7.9) for x in range(26, 37, 2)] + [(x, 7.9) for x in range(47, 62, 2)]
        fence += [(x, 15.5) for x in range(26, 53, 2) if abs(x - 36) > 1.4 and abs(x - 43.5) > 1.4]
        fence += [(x, 12.5) for x in range(53, 62, 2)]
        fence += [(24.5, 8.5), (24.5, 12.0), (34.5, 6.0), (46.5, 5.5), (48.5, 3.5)]
        for x, y in fence:
            via(x, y, "GND")

    else:
        # pico: freerouting routes RF; add a couple of GND fence vias near the FEM
        for _fx, _fy in [(24.5, 8.5), (24.5, 12.0)]:
            via(_fx, _fy, "GND")
        for _pr in getattr(_d, "PREROUTE", []):
            _pts = [pad_pos(*q) if isinstance(q, tuple) and isinstance(q[0], str) else VECTOR2I_MM(*q)
                    for q in _pr["points"]]
            _lay = getattr(pcbnew, _pr.get("layer", "F_Cu"))
            for _a, _b in zip(_pts, _pts[1:]):
                _t = pcbnew.PCB_TRACK(board)
                _t.SetStart(_a); _t.SetEnd(_b); _t.SetWidth(FromMM(_pr.get("w", 0.25)))
                _t.SetLayer(_lay); _t.SetNet(netmap[_pr["net"]]); _t.SetLocked(True)
                board.Add(_t)

    # GND pours on all layers ---------------------------------------------
    for layer, clr in [(pcbnew.F_Cu, 0.5), (pcbnew.In1_Cu, 0.3), (pcbnew.In2_Cu, 0.3), (pcbnew.B_Cu, 0.5)]:
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(netmap["GND"])
        z.SetZoneName("GND_" + pcbnew.BOARD.GetStandardLayerName(layer))
        z.SetLocalClearance(FromMM(clr))
        z.SetMinThickness(FromMM(0.2))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(FromMM(0.3))
        z.SetThermalReliefSpokeWidth(FromMM(0.35))
        z.SetIsFilled(False)
        inset = 0.4
        for x, y in [(inset, inset), (BOARD_W - inset, inset), (BOARD_W - inset, BOARD_H - inset),
                     (inset, BOARD_H - inset)]:
            z.AppendCorner(VECTOR2I_MM(x, y), -1)
        board.Add(z)

    # CC1 is boxed in between the USB pads: route it by hand (freerouting gave up on it)
    line([("J1", "A5"), (31.75, 42.5), (28.6, 42.5), (27.99, 41.9), ("R1", "1")], "CC1", w=0.2)

    # RF pads: solid connection to the pour (GND side of shunt parts and QFN paddle)
    for ref in ("U4", "J2", "J5", "C13", "C14", "R9", "R10", "C9", "C10", "U1", "J1"):
        if ref not in fps:
            continue
        for pd in fps[ref].Pads():
            if pd.GetNetname() == "GND":
                pd.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    out = os.path.join(KICAD_DIR, PROJECT + ".kicad_pcb")
    pcbnew.SaveBoard(out, board)
    print("wrote", out, "footprints:", len(fps), "nets:", len(netmap))


if __name__ == "__main__":
    main()
