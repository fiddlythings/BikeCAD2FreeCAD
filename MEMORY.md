# BCad2FreeCAD Project - Session Memory

## Last Updated: 2026-03-12

## Current State
v1 converter implemented and tested. All 52 unit/integration tests pass.

## Files
- `bcad2freecad.py` — single-file converter (parser, geometry, FreeCAD script generator, CLI)
- `tests/test_parser.py` — parser unit tests
- `tests/test_geometry.py` — geometry + script generation tests
- `Gravel.bcad` — sample input file (7216 params)
- `Gravel_freecad.py` — generated FreeCAD macro (13 tubes)

## What's Implemented
- **BcadParser**: Java Properties XML parser with typed getters (float/int/bool/str)
- **FrameGeometry**: Computes 3D tube positions. Origin at BB center, X=forward, Y=up, Z=right.
  - Reference points: BB, HT top/bottom, ST top, rear/front axle
  - Measure style 3: FCD textfield interpreted as Reach (= 410mm for Gravel.bcad)
- **13 tubes**: BB shell, head tube (tapered), seat tube (tapered), top tube, down tube, 2x chainstay, 2x seatstay, seatstay bridge, 2x fork blade, steerer
- **FreeCADScriptGenerator**: Emits standalone FreeCAD Python macro with `make_tube()` helper
- **CLI**: `--dump-params` and `--hollow` flags

## Key Geometry Decisions
- Reach derived from `FCD textfield` when `Top tube front center measure style` = 3
- Fork ATC = `FORK{type}L`, Fork rake = `FORK{type}R`
- Chainstay oval approximated as equivalent-area circle for FreeCAD cones
- Seatstay junction = `Seat stay offset` (35mm) below ST top along seat tube
- Front axle height sanity check: ~10mm discrepancy vs BB drop (acceptable for v1)

## Known Limitations / Future Work
- Chainstays modeled as simple cones (no oval cross-section or S-bend)
- No tube mitering at junctions
- No bent tube support (all bent flags are false in Gravel.bcad)
- Only measure style 3 (Stack & Reach) properly handled
- Wall thickness in FreeCAD only renders with `--hollow` flag
- Needs visual verification in FreeCAD
