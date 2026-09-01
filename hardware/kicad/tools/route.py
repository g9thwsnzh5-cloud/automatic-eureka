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
PCB = os.path.join(KICAD_DIR, "esp32_fem.kicad_pcb")

sys.path.insert(0, HERE)
from design import PARTS, RF_NETS  # noqa: E402


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
    raw = os.path.join(BUILD, "esp32_fem_raw.dsn")
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
    d = "\n".join(l for l in d.split("\n") if "plane GND (polygon F.Cu" not in l and "plane GND (polygon B.Cu" not in l)
    out = os.path.join(BUILD, "esp32_fem.dsn")
    open(out, "w").write(d)
    print("wrote", out)
    print("now run: java -jar freerouting-1.9.0.jar -de build/esp32_fem.dsn -do build/esp32_fem.ses -mp 30 -inc RF")


def do_import():
    board = pcbnew.LoadBoard(PCB)
    wires, vias = parse_ses(os.path.join(BUILD, "esp32_fem.ses"))
    # the session contains every wire and via (pre-routed RF included): start clean
    for t in list(board.GetTracks()):
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


def do_drc():
    board = pcbnew.LoadBoard(PCB)
    fill(board)
    pcbnew.SaveBoard(PCB, board)
    rpt = os.path.join(BUILD, "drc.rpt")
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    txt = open(rpt).read()
    print(txt[-3000:])
    return txt


def do_fab():
    fab = os.path.join(BUILD, "fab")
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
    with open(os.path.join(fab, "esp32_fem_cpl.csv"), "w", newline="") as f:
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
    with open(os.path.join(fab, "esp32_fem_bom.csv"), "w", newline="") as f:
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
    {"dsn": do_dsn, "import": do_import, "drc": do_drc, "fab": do_fab}[cmd]()
