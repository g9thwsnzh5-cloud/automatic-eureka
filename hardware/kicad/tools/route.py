#!/usr/bin/env python3
"""Post-route pipeline: import the freerouting session, fill zones, run DRC,
and export fabrication files (Gerbers, drill, JLCPCB BOM and CPL).

Usage (from hardware/kicad):
    python3 tools/route.py import   # after freerouting wrote build/esp32_fem.ses
    python3 tools/route.py fab      # DRC report + gerbers/drill/bom/cpl into build/fab
"""
import csv
import os
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD_DIR = os.path.dirname(HERE)
BUILD = os.path.join(KICAD_DIR, "build")
PCB = os.path.join(KICAD_DIR, "esp32_fem.kicad_pcb")  # overridden below after DESIGN import

sys.path.insert(0, HERE)
import importlib as _il
_DM = os.environ.get("DESIGN", "design")
_d = _il.import_module(_DM)
PARTS, RF_NETS = _d.PARTS, _d.RF_NETS
_PROJECT = getattr(_d, "PROJECT", "esp32_fem")
_HAND_RF = getattr(_d, "HAND_RF", True)


PCB = os.path.join(KICAD_DIR, _PROJECT + ".kicad_pcb")
_NET = _PROJECT + ".net"
_DSN = _PROJECT + ".dsn"
_SES = _PROJECT + ".ses"


def fill(board):
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def parse_ses(path):
    """Minimal Specctra session parser: returns (wires, vias).

    wires: [(layer, width_um, [(x_um, y_um), ...], net)], vias: [(x_um, y_um, net)]
    Coordinates are in the session's resolution units converted to um.
    """
    import re as _re
    s = open(path).read()
    res = _re.search(r"\(resolution\s+(\w+)\s+(\d+)\)", s)
    unit, per = res.group(1), int(res.group(2))
    scale = (1000.0 if unit == "mm" else 1.0) / per  # -> um
    wires, vias = [], []
    ns = s[s.find("(network_out"):]
    for m in _re.finditer(r'\(net "?([^\s")]+)"?', ns):
        net = m.group(1)
        d = 0
        i = m.start()
        for j in range(i, len(ns)):
            if ns[j] == "(":
                d += 1
            elif ns[j] == ")":
                d -= 1
                if d == 0:
                    break
        body = ns[i:j + 1]
        for w in _re.finditer(r"\(wire\s*\(path\s+(\S+)\s+([\d.]+)\s+([-\d.\s]+?)\)", body):
            nums = [float(v) for v in w.group(3).split()]
            pts = [(nums[k] * scale, -nums[k + 1] * scale) for k in range(0, len(nums), 2)]
            wires.append((w.group(1), float(w.group(2)) * scale, pts, net))
        for v in _re.finditer(r'\(via\s+"?[^\s"]+"?\s+([-\d.]+)\s+([-\d.]+)', body):
            vias.append((float(v.group(1)) * scale, -float(v.group(2)) * scale, net))
    return wires, vias


def do_dsn():
    """Export a Specctra DSN for freerouting: RF nets get their own class
    (route them by hand, freerouting is told to ignore the class) and the
    outer-layer GND pours are dropped so the router has room; gen_pcb.py
    re-creates the pours and route.py import fills them."""
    import re as _re
    board = pcbnew.LoadBoard(PCB)
    raw = os.path.join(BUILD, _PROJECT + "_raw.dsn")
    pcbnew.ExportSpecctraDSN(board, raw)
    d = open(raw).read()
    m = _re.search(r'\(class kicad_default "" (.*?)\n      \(circuit', d, _re.S)
    body = m.group(1)
    for n in RF_NETS:
        body = _re.sub(r"\b%s\b" % n, "", body)
    d = d[:m.start(1)] + body + d[m.end(1):]
    rfclass = ("    (class RF \"\" %s\n      (circuit\n        (use_via Via[0-3]_600:300_um)\n      )\n"
               "      (rule\n        (width 380)\n        (clearance 200.1)\n      )\n    )\n" % " ".join(RF_NETS))
    i = d.rfind("  )\n  (wiring")
    d = d[:i] + rfclass + d[i:]
    _skip = getattr(_d, "SKIP_NETS", [])
    if _skip:
        # un-routed nets (GND: pours + stitching) go to their own class that freerouting is told
        # to ignore (-inc RF,SKIP); their existing vias stay as obstacles, planes stay defined
        m = _re.search(r'\(class kicad_default "" (.*?)\n      \(circuit', d, _re.S)
        body = m.group(1)
        for n in _skip:
            body = _re.sub(r'(?<=[\s"])%s(?=[\s"])' % _re.escape(n), "", body)
        d = d[:m.start(1)] + body + d[m.end(1):]
        skclass = ("    (class SKIP \"\" %s\n      (circuit\n        (use_via Via[0-3]_600:300_um)\n      )\n"
                   "      (rule\n        (width 250)\n        (clearance 150.1)\n      )\n    )\n" % " ".join(_skip))
        i = d.rfind("  )\n  (wiring")
        d = d[:i] + skclass + d[i:]
    if getattr(_d, "NO_INNER_ROUTING", False):
        # planes: tell freerouting not to route on In1/In2
        d = _re.sub(r"\(layer (In1)\.Cu\n(\s+)\(type signal\)", r"(layer \1.Cu\n\2(type power)", d)
    d = "\n".join(l for l in d.split("\n") if "plane GND (polygon F.Cu" not in l and "plane GND (polygon B.Cu" not in l)
    out = os.path.join(BUILD, _DSN)
    open(out, "w").write(d)
    print("wrote", out)
    print("now run: java -jar freerouting-1.9.0.jar -de build/%s -do build/%s -mp 30 -inc RF%s" % (_DSN, _SES, ",SKIP" if _skip else ""))


def do_import():
    board = pcbnew.LoadBoard(PCB)
    wires, vias = parse_ses(os.path.join(BUILD, _SES))
    _keep = set(getattr(_d, "SKIP_NETS", []))
    # ignored classes are echoed back in the session: the board already carries them
    wires = [w for w in wires if w[3] not in _keep]
    vias = [v for v in vias if v[2] not in _keep]
    # the session contains every wire and via (pre-routed RF included): start clean
    for t in list(board.GetTracks()):
        if t.IsLocked() or t.GetNetname() in _keep:   # keep hand/pre-routed copper and un-routed nets (stitching)
            continue
        board.Remove(t)
    nets = {n: board.FindNet(n) for n in {w[3] for w in wires} | {v[2] for v in vias}}
    layer_ids = {board.GetLayerName(l): l for l in range(pcbnew.PCB_LAYER_ID_COUNT) if board.IsLayerEnabled(l)}
    n_t = n_v = 0
    for layer, width, pts, net in wires:
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(a[0] * 1000), int(a[1] * 1000)))
            t.SetEnd(pcbnew.VECTOR2I(int(b[0] * 1000), int(b[1] * 1000)))
            t.SetWidth(int(width * 1000))
            t.SetLayer(layer_ids[layer])
            t.SetNet(nets[net])
            board.Add(t)
            n_t += 1
    for x, y, net in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(int(x * 1000), int(y * 1000)))
        v.SetWidth(pcbnew.FromMM(0.6))
        v.SetDrill(pcbnew.FromMM(0.3))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(nets[net])
        board.Add(v)
        n_v += 1
    print("SES import: %d track segments, %d vias" % (n_t, n_v))
    fill(board)
    pcbnew.SaveBoard(PCB, board)
    # island repair in a fresh interpreter: after the Remove()/Add() churn SWIG hands back
    # unwrapped objects in this process
    subprocess.check_call([sys.executable, os.path.abspath(__file__), "repair"], env=dict(os.environ, DESIGN=_DM))


def do_repair():
    board = pcbnew.LoadBoard(PCB)
    fill(board)
    for _ in range(3):
        if not repair_islands(board):
            break
        fill(board)
    pcbnew.SaveBoard(PCB, board)


def repair_islands(board):
    """After routing, a GND pour piece can be left holding a pad but no via (the router cut
    it off from the rest of the pour). Drop a via into every such piece so it reaches the
    inner planes. Returns the number of vias added."""
    gcode = next(t.GetNetCode() for t in board.GetTracks() if t.GetNetname() == "GND")
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    pth = [p for p in pads if p.GetNetCode() == gcode and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
    edge = board.GetBoardEdgesBoundingBox()

    def _dseg(px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        if dx == dy == 0:
            return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        return ((px - x1 - t * dx) ** 2 + (py - y1 - t * dy) ** 2) ** 0.5

    def spot_ok(x, y, poly):
        P = pcbnew.VECTOR2I
        M = pcbnew.FromMM
        if not all(poly.Contains(P(M(x + dx), M(y + dy))) for dx, dy in ((0.45, 0), (-0.45, 0), (0, 0.45), (0, -0.45))):
            return False
        if x - 1.0 < edge.GetLeft() / 1e6 or x + 1.0 > edge.GetRight() / 1e6 or y - 1.0 < edge.GetTop() / 1e6 or y + 1.0 > edge.GetBottom() / 1e6:
            return False
        for t in tracks:
            if t.GetNetCode() == gcode:
                continue
            if _dseg(x, y, t.GetStart().x / 1e6, t.GetStart().y / 1e6, t.GetEnd().x / 1e6, t.GetEnd().y / 1e6) < t.GetWidth() / 2e6 + 0.3 + 0.2:
                return False
        for v in vias:
            if (x - v.GetPosition().x / 1e6) ** 2 + (y - v.GetPosition().y / 1e6) ** 2 < 1.0 ** 2:
                return False
        for p in pads:
            bb = p.GetBoundingBox()
            m = 0.55 if p.GetNetCode() != gcode else 0.35
            if bb.GetLeft() / 1e6 - m <= x <= bb.GetRight() / 1e6 + m and bb.GetTop() / 1e6 - m <= y <= bb.GetBottom() / 1e6 + m:
                return False
        return True

    added = 0
    for z in board.Zones():
        if z.GetNetCode() != gcode:
            continue
        layer = z.GetFirstLayer()
        if layer not in (pcbnew.F_Cu, pcbnew.B_Cu):
            continue
        f = z.GetFilledPolysList(layer)
        for i in range(f.OutlineCount()):
            poly = pcbnew.SHAPE_POLY_SET(f.Outline(i))
            if any(poly.Contains(v.GetPosition()) for v in vias) or any(poly.Contains(p.GetPosition()) for p in pth):
                continue
            has_pad = any(poly.Contains(p.GetPosition()) for p in pads if p.GetNetCode() == gcode)
            if not has_pad:
                continue                      # a bare island: the fill removes it
            bb = f.Outline(i).BBox()
            best = None
            y = bb.GetTop() / 1e6 + 0.5
            while y < bb.GetBottom() / 1e6 and best is None:
                x = bb.GetLeft() / 1e6 + 0.5
                while x < bb.GetRight() / 1e6:
                    if spot_ok(x, y, poly):
                        best = (x, y)
                        break
                    x += 0.25
                y += 0.25
            if best is None:
                print("island on %s near (%.1f, %.1f): no room for a via" % (board.GetLayerName(layer), bb.GetLeft() / 1e6, bb.GetTop() / 1e6))
                continue
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(best[0]), pcbnew.FromMM(best[1])))
            v.SetWidth(pcbnew.FromMM(0.6)); v.SetDrill(pcbnew.FromMM(0.3))
            v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNetCode(gcode); v.SetLocked(True)
            board.Add(v); vias.append(v); added += 1
            print("island on %s: via at (%.2f, %.2f)" % (board.GetLayerName(layer), best[0], best[1]))
    return added


def do_drc():
    board = pcbnew.LoadBoard(PCB)
    fill(board)
    pcbnew.SaveBoard(PCB, board)
    rpt = os.path.join(BUILD, "drc.rpt")
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    txt = open(rpt).read()
    import re as _re
    kinds = _re.findall(r"^\[(\w+)\]", txt, _re.M)
    from collections import Counter
    print("DRC summary:", dict(Counter(kinds)) or "clean")
    for blk in _re.findall(r"^\[\w+\].*(?:\n    .*)*", txt, _re.M)[:80]:
        print("\n".join(l for l in blk.split("\n") if "Local override" not in l and "Severity" not in l))
    return txt


def do_fab():
    fab = os.path.join(BUILD, "fab" if _PROJECT == "esp32_fem" else "fab_" + _PROJECT.replace("esp32_fem_", ""))
    os.makedirs(fab, exist_ok=True)
    layers = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
    subprocess.check_call(["kicad-cli", "pcb", "export", "gerbers", "--layers", layers,
                           "--subtract-soldermask", "--no-x2", "--use-drill-file-origin",
                           "-o", fab + "/", PCB])
    subprocess.check_call(["kicad-cli", "pcb", "export", "drill", "--format", "excellon",
                           "--excellon-separate-th", "--generate-map", "--map-format", "gerberx2",
                           "-o", fab + "/", PCB])
    # JLCPCB BOM + CPL
    board = pcbnew.LoadBoard(PCB)
    meta = {p["ref"]: p for p in PARTS}
    bom = {}
    with open(os.path.join(fab, _PROJECT + "_cpl.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            p = meta.get(ref)
            if p is None or p.get("dnp") or not p.get("jlc", True) or not p.get("lcsc"):
                continue
            pos = fp.GetPosition()
            w.writerow([ref, "%.3fmm" % (pos.x / 1e6), "%.3fmm" % (-pos.y / 1e6),
                        "Top" if fp.GetLayer() == pcbnew.F_Cu else "Bottom",
                        "%.1f" % fp.GetOrientationDegrees()])
            key = (p["value"], p["fp"].split(":")[1], p["lcsc"])
            bom.setdefault(key, []).append(ref)
    with open(os.path.join(fab, _PROJECT + "_bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (val, fpn, lcsc), refs in sorted(bom.items(), key=lambda kv: kv[1][0]):
            w.writerow([val, ",".join(refs), fpn, lcsc])
    with open(os.path.join(fab, "hand_soldered_parts.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Value", "Footprint", "Note"])
        for p in PARTS:
            if not p.get("jlc", True) and not p.get("dnp"):
                w.writerow([p["ref"], p["value"], p["fp"].split(":")[1], "not assembled by JLCPCB"])
    print("fab files in", fab, os.listdir(fab))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "drc"
    {"dsn": do_dsn, "import": do_import, "repair": do_repair, "drc": do_drc, "fab": do_fab}[cmd]()
