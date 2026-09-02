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
HOLES = [(4.0, 4.0), (52.0, 4.0), (4.0, 48.0), (52.0, 48.0)]

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
    ds.m_CopperEdgeClearance = FromMM(0.5)     # JLC: inner-layer copper >= 0.5 mm from the routed edge
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

    for _t, _x, _y, _sz in getattr(_d, "SILK", [("ESP32 Wi-Fi FEM  rev A", 51.0, 24.0, 1.2), ("RF IN", 27.3, 12.9, 0.8)]):
        text(_t, _x, _y, size=_sz)
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
        if "J2" in fps:
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
        # stitching vias along the RF lines (ground fence) -- rev A positions
        fence = []
        fence += [(x, 7.9) for x in range(26, 37, 2)] + [(x, 7.9) for x in range(47, 62, 2)]
        fence += [(x, 15.5) for x in range(26, 53, 2) if abs(x - 36) > 1.4 and abs(x - 43.5) > 1.4]
        fence += [(x, 12.5) for x in range(53, 62, 2)]
        fence += [(24.5, 8.5), (24.5, 12.0), (34.5, 6.0), (46.5, 5.5), (48.5, 3.5)]
        if "J2" not in fps:
            fence = []            # rev B: only the generic fence/stitching below
        for x, y in fence:
            if not any(l <= x <= r and t_ <= y <= b for (l, t_, r, b) in [
                    (fp.GetBoundingBox(False, False).GetLeft() / 1e6 - 0.3, fp.GetBoundingBox(False, False).GetTop() / 1e6 - 0.3,
                     fp.GetBoundingBox(False, False).GetRight() / 1e6 + 0.3, fp.GetBoundingBox(False, False).GetBottom() / 1e6 + 0.3)
                    for fp in board.GetFootprints()]):
                via(x, y, "GND")

    else:
        # pico: freerouting routes RF; add a couple of GND fence vias near the FEM
        for _fx, _fy in [(24.5, 8.5), (24.5, 12.0)]:
            via(_fx, _fy, "GND")

    # design pre-routes (locked)
    for _pr in getattr(_d, "PREROUTE", []):
        _pts = [pad_pos(*q) if isinstance(q, tuple) and isinstance(q[0], str) else VECTOR2I_MM(*q)
                for q in _pr["points"]]
        _lay = getattr(pcbnew, _pr.get("layer", "F_Cu"))
        for _a, _b in zip(_pts, _pts[1:]):
            _t = pcbnew.PCB_TRACK(board)
            _t.SetStart(_a); _t.SetEnd(_b); _t.SetWidth(FromMM(_pr.get("w", 0.25)))
            _t.SetLayer(_lay); _t.SetNet(netmap[_pr["net"]]); _t.SetLocked(True)
            board.Add(_t)

    for _vx, _vy, _vn in getattr(_d, "PREROUTE_VIAS", []):
        _v = pcbnew.PCB_VIA(board); _v.SetPosition(VECTOR2I_MM(_vx, _vy)); _v.SetWidth(FromMM(0.6)); _v.SetDrill(FromMM(0.3))
        _v.SetViaType(pcbnew.VIATYPE_THROUGH); _v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); _v.SetNet(netmap[_vn]); _v.SetLocked(True); board.Add(_v)

    # CC1 is boxed in between the USB pads: route it by hand (freerouting gave up on it)
    line([("J1", "A5"), (31.75, 42.5), (28.6, 42.5), (27.99, 41.9), ("R1", "1")], "CC1", w=0.2)

    # pads sharing a number (tactile switch legs, SOT-223 tab+pin): freerouting treats them as
    # one pin and never routes between them; KiCad wants copper -> join with a locked track
    for _fp in board.GetFootprints():
        if _fp.GetPadCount() > 6:
            continue              # connectors (USB-C shell legs): the pour joins them
        _groups = {}
        for _p in _fp.Pads():
            if _p.GetNetCode() > 0:
                _groups.setdefault((_p.GetNumber(), _p.GetNetCode()), []).append(_p)
        for (_num, _nc), _pl in _groups.items():
            for _a, _b in zip(_pl, _pl[1:]):
                ax, ay = _a.GetPosition().x / 1e6, _a.GetPosition().y / 1e6
                bx, by = _b.GetPosition().x / 1e6, _b.GetPosition().y / 1e6
                blocked = False
                for _o in board.GetPads():
                    if _o.GetNetCode() == _nc:
                        continue
                    _ob = _o.GetBoundingBox()
                    l, t_, r, b_ = _ob.GetLeft() / 1e6 - 0.35, _ob.GetTop() / 1e6 - 0.35, _ob.GetRight() / 1e6 + 0.35, _ob.GetBottom() / 1e6 + 0.35
                    if any(l <= ax + (bx - ax) * k / 20 <= r and t_ <= ay + (by - ay) * k / 20 <= b_ for k in range(21)):
                        blocked = True
                        break
                if blocked:
                    continue      # straight jumper would cross a foreign pad (SMA centre pin): leave to the pour
                _t = pcbnew.PCB_TRACK(board)
                _t.SetStart(_a.GetPosition()); _t.SetEnd(_b.GetPosition()); _t.SetWidth(FromMM(0.3))
                _t.SetLayer(pcbnew.F_Cu); _t.SetNetCode(_nc); _t.SetLocked(True)
                board.Add(_t)

    # spots free of footprints (for fence / stitching vias)
    _boxes = []
    for _fp in board.GetFootprints():
        _bb = _fp.GetBoundingBox(False, False)
        _boxes.append((_bb.GetLeft() / 1e6 - 0.45, _bb.GetTop() / 1e6 - 0.45,
                       _bb.GetRight() / 1e6 + 0.45, _bb.GetBottom() / 1e6 + 0.45))
    _rf_ids = {netmap[n].GetNetCode() for n in RF_NETS if n in netmap}
    _all_segs = [(t.GetStart().x / 1e6, t.GetStart().y / 1e6, t.GetEnd().x / 1e6, t.GetEnd().y / 1e6, t.GetNetCode())
                 for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    _rf_segs = [sg[:4] for sg in _all_segs if sg[4] in _rf_ids]

    def _dseg(px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        if dx == dy == 0:
            return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        return ((px - x1 - t * dx) ** 2 + (py - y1 - t * dy) ** 2) ** 0.5

    _vias = [(t.GetPosition().x / 1e6, t.GetPosition().y / 1e6) for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]

    def free(x, y, rf_min=1.0):
        if not (1.2 < x < BOARD_W - 1.2 and 1.2 < y < BOARD_H - 1.2):
            return False
        if any((x - vx) ** 2 + (y - vy) ** 2 < 1.0 for vx, vy in _vias):
            return False
        for l, t_, r, b in _boxes:
            if l <= x <= r and t_ <= y <= b:
                return False
        if any(_dseg(x, y, *sg[:4]) < 0.6 for sg in _all_segs):
            return False
        return all(_dseg(x, y, *sg) >= rf_min for sg in _rf_segs)

    # GND fanout: every small SMD GND pad gets its own via to the planes (short 0.3 mm stub),
    # placed before autorouting so the router treats them as obstacles
    if getattr(_d, "GND_FANOUT", False):
        import math as _m
        _gnd = netmap["GND"].GetNetCode()
        _pads = []
        for _fp in board.GetFootprints():
            for _p in _fp.Pads():
                _bb = _p.GetBoundingBox()
                _pads.append((_bb.GetLeft() / 1e6, _bb.GetTop() / 1e6, _bb.GetRight() / 1e6, _bb.GetBottom() / 1e6, _p))
        _big = [(_bb.GetLeft() / 1e6, _bb.GetTop() / 1e6, _bb.GetRight() / 1e6, _bb.GetBottom() / 1e6, _fp)
                for _fp in board.GetFootprints() for _bb in [_fp.GetBoundingBox(False, False)] if _fp.GetPadCount() > 8]

        def _why(x, y, own, r):
            if not (1.0 < x < BOARD_W - 1.0 and 1.0 < y < BOARD_H - 1.0):
                return "edge"
            for l, t_, rr, b, pp in _pads:
                if pp.m_Uuid.AsString() == own.m_Uuid.AsString():
                    continue
                m = 0.15 if pp.GetNetCode() == _gnd else r      # same-net neighbours may sit close
                if l - m <= x <= rr + m and t_ - m <= y <= b + m:
                    return "pad %s-%s" % (pp.GetParent().GetReference(), pp.GetNumber())
            for l, t_, rr, b, fpb in _big:
                if fpb.GetReference() == own.GetParent().GetReference():
                    continue           # a stub next to its own pad is fine
                if l - 0.2 <= x <= rr + 0.2 and t_ - 0.2 <= y <= b + 0.2:
                    return "body " + fpb.GetReference()
            if any(_dseg(x, y, *sg[:4]) < r + 0.25 for sg in _all_segs if sg[4] != _gnd):
                return "track"
            if any(_dseg(x, y, *sg) < 0.75 for sg in _rf_segs):
                return "rf"
            if not all((x - vx) ** 2 + (y - vy) ** 2 >= 0.8 ** 2 for vx, vy in _vias):
                return "via"
            return ""

        def _clear(x, y, own, r):
            return _why(x, y, own, r) == ""

        _fan = 0
        _dbg = os.environ.get("DEBUG_FANOUT", "")
        for _fp in board.GetFootprints():
            _fc = _fp.GetPosition()
            # QFN with a GND paddle: tie the GND side pins to the paddle with short stubs
            _ep = [q for q in _fp.Pads() if q.GetNetCode() == _gnd and q.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                   and min(q.GetSize().x, q.GetSize().y) / 1e6 >= 1.5]
            if _ep:
                _e = _ep[0]
                ex, ey = _e.GetPosition().x / 1e6, _e.GetPosition().y / 1e6
                ew, eh = _e.GetSize().x / 1e6 / 2, _e.GetSize().y / 1e6 / 2
                for _p in _fp.Pads():
                    if _p.GetNetCode() != _gnd or _p is _e or max(_p.GetSize().x, _p.GetSize().y) / 1e6 > 1.5:
                        continue
                    px, py = _p.GetPosition().x / 1e6, _p.GetPosition().y / 1e6
                    sx, sy = _p.GetSize().x / 1e6, _p.GetSize().y / 1e6
                    tx, ty = (ex, py) if sx > sy else (px, ey)
                    if abs(tx - ex) <= ew and abs(ty - ey) <= eh:
                        track(VECTOR2I_MM(px, py), VECTOR2I_MM(tx, ty), "GND", w=min(sx, sy))
                        _fan += 1
                continue
            for _p in _fp.Pads():
                if _p.GetNetCode() != _gnd or _p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                    continue
                if _p.GetSize().x / 1e6 > 2.0 or _p.GetSize().y / 1e6 > 2.0:
                    continue          # exposed pads / big lugs have their own vias
                px, py = _p.GetPosition().x / 1e6, _p.GetPosition().y / 1e6
                if any((px - vx) ** 2 + (py - vy) ** 2 < 1.0 for vx, vy in _vias):
                    continue          # already has a via next to it
                a0 = _m.atan2(py - _fc.y / 1e6, px - _fc.x / 1e6)
                done = False
                for dang in (0, 45, -45, 90, -90, 135, -135, 180):
                    a = a0 + _m.radians(dang)
                    for dist in (0.75, 0.9, 1.1, 1.4):
                        vx, vy = px + dist * _m.cos(a), py + dist * _m.sin(a)
                        mx, my = (px + vx) / 2, (py + vy) / 2
                        if _dbg and _fp.GetReference() == _dbg:
                            print("  try", _p.GetNumber(), round(vx, 2), round(vy, 2), _why(vx, vy, _p, 0.42) or "ok", "/", _why(mx, my, _p, 0.3) or "ok")
                        if _clear(vx, vy, _p, 0.47) and _clear(mx, my, _p, 0.3):
                            via(vx, vy, "GND")            # 0.6/0.3: annular 0.15 (0.5/0.25 sits on JLC's minimum)
                            track(VECTOR2I_MM(px, py), VECTOR2I_MM(vx, vy), "GND", w=0.3)
                            _p.SetZoneConnection(pcbnew.ZONE_CONNECTION_NONE)   # the stub is the connection (no starved-thermal DRC)
                            _vias.append((vx, vy)); _all_segs.append((px, py, vx, vy, _gnd))
                            _fan += 1; done = True
                            break
                    if done:
                        break
        print("GND fanout vias:", _fan)

    _stitch = getattr(_d, "STITCH", 0)
    if _stitch:
        _n = 0
        _gx = _stitch
        _y = 2.0
        while _y < BOARD_H - 1.5:
            _x = 2.0 + (_gx / 2 if int(_y / _stitch) % 2 else 0)
            while _x < BOARD_W - 1.5:
                if free(_x, _y, rf_min=1.2):
                    via(_x, _y, "GND"); _vias.append((_x, _y)); _n += 1
                _x += _gx
            _y += _stitch
        # RF fence: vias 0.9 mm either side of every hand-routed RF segment
        for x1, y1, x2, y2 in _rf_segs:
            L = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            if L < 1.0:
                continue
            nx, ny = -(y2 - y1) / L, (x2 - x1) / L
            k = 0.8
            while k < L - 0.4:
                cx, cy = x1 + (x2 - x1) * k / L, y1 + (y2 - y1) * k / L
                for sgn in (1, -1):
                    fx, fy = cx + sgn * 0.95 * nx, cy + sgn * 0.95 * ny
                    if free(fx, fy, rf_min=0.85):
                        via(fx, fy, "GND"); _vias.append((fx, fy)); _n += 1
                k += 1.6
        print("stitching/fence vias:", _n)

    # GND pours on all layers ---------------------------------------------
    _in2 = getattr(_d, "IN2_NET", "GND")   # pico: In2 is a +3V3 plane (SIG/GND/PWR/SIG stack)
    for layer, clr in [(pcbnew.F_Cu, 0.5), (pcbnew.In1_Cu, 0.3), (pcbnew.In2_Cu, 0.3), (pcbnew.B_Cu, 0.5)]:
        _znet = _in2 if layer == pcbnew.In2_Cu else "GND"
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(netmap[_znet])
        z.SetZoneName(_znet + "_" + pcbnew.BOARD.GetStandardLayerName(layer))
        z.SetLocalClearance(FromMM(clr))
        z.SetMinThickness(FromMM(0.2))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(FromMM(0.3))
        z.SetThermalReliefSpokeWidth(FromMM(0.35))
        z.SetIsFilled(False)
        if hasattr(pcbnew, "ISLAND_REMOVAL_MODE_ALWAYS"):
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        inset = 0.4
        for x, y in [(inset, inset), (BOARD_W - inset, inset), (BOARD_W - inset, BOARD_H - inset),
                     (inset, BOARD_H - inset)]:
            z.AppendCorner(VECTOR2I_MM(x, y), -1)
        board.Add(z)

    # QFN paddle paste: KiCad's ThermalVias footprints print ~76 %; JLC/Qorvo want ~50 %
    for _fp in board.GetFootprints():
        for _p in _fp.Pads():
            if _p.GetNumber() == "" and _p.GetLayerSet().Seq() and all(board.GetLayerName(l) in ("F.Paste", "B.Paste") for l in _p.GetLayerSet().Seq()):
                _p.SetSize(pcbnew.VECTOR2I(int(_p.GetSize().x * 0.81), int(_p.GetSize().y * 0.81)))

    # RF pads: solid connection to the pour (GND side of shunt parts and QFN paddle)
    for ref in ("U4", "J2", "J5", "C13", "C14", "R9", "R10", "C9", "C10", "U1", "J1", "R41", "C41", "C4", "R12", "C6", "J4", "C43", "U2", "J5", "R2", "C42"):
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
