#!/bin/bash
# import SES -> patch check -> DRC
cd "$(dirname "$0")/.."
export DESIGN=design_pico
python3 tools/route.py import 2>&1 | tail -3
python3 - <<'PY'
import pcbnew
b = pcbnew.LoadBoard("esp32_fem_pico.kicad_pcb")
u1 = b.FindFootprintByReference("U1")
print("U1 LCSC:", u1.GetProperty("LCSC"), "value:", u1.GetValue())
for p in u1.Pads():
    if p.GetNumber() == "49":
        print("pad49 paste ratio:", p.GetLocalSolderPasteMarginRatio(), "size", pcbnew.ToMM(p.GetSize().x))
nv = sum(1 for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == "GND")
print("GND vias on board:", nv)
PY
python3 tools/route.py drc 2>&1 | tail -40
