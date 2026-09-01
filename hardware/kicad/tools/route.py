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
from design import PARTS  # noqa: E402


def fill(board):
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def do_import():
    board = pcbnew.LoadBoard(PCB)
    ok = pcbnew.ImportSpecctraSES(board, os.path.join(BUILD, "esp32_fem.ses"))
    print("SES import:", ok)
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
    {"import": do_import, "drc": do_drc, "fab": do_fab}[cmd]()
