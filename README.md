# BCad2FreeCAD

Convert BikeCAD `.bcad` files to FreeCAD 3D models — without BikeCAD Pro.

BikeCAD Pro can export to FreeCAD natively, but if you only have the free version or a `.bcad` file from a builder, this tool generates a standalone FreeCAD Python macro that recreates the frame tubes as a 3D model.

```
Gravel.bcad  -->  [bcad2freecad.py]  -->  Gravel_freecad.py  -->  [FreeCAD]  -->  3D frame
```

## What it produces

A FreeCAD macro that creates 15 tubes:

- **Main triangle**: bottom bracket shell, head tube (tapered), seat tube, top tube, down tube
- **Rear triangle**: chainstays (x2), seatstays (x2), seatstay bridge
- **Fork**: fork blades (x2), fork crown arms (x2), steerer tube

The scope is **frame and fork tubes only** — no wheels, brakes, dropouts, saddle, or other catalog components.

## Requirements

- Python 3.10+
- [FreeCAD](https://www.freecad.org/) (to open the generated macro)
- No additional Python packages needed

## Usage

```bash
# Generate a FreeCAD macro
python bcad2freecad.py MyBike.bcad

# Specify output filename
python bcad2freecad.py MyBike.bcad -o my_frame.py

# Inspect extracted geometry without generating a script
python bcad2freecad.py MyBike.bcad --dump-params

# Generate hollow tubes (more realistic but slower to render)
python bcad2freecad.py MyBike.bcad --hollow
```

Then in FreeCAD: **Macro > Execute Macro** and select the generated `.py` file.

## Example output from `--dump-params`

```
Computed Frame Geometry
==================================================
  Head angle (deg).............. 71.0
  Seat angle (deg).............. 73.0
  Stack......................... 662.0
  Reach......................... 410.0
  BB drop....................... 65.0
  CS length..................... 450.0
  HT length..................... 195.0
  ST length..................... 560.0
  Fork ATC...................... 445.0
  Fork rake..................... 55.0
  ...

Tubes:
  BB_Shell................. L=68.0mm  R=20.0
  Head_Tube................ L=195.0mm  R=23.8->19.0
  Seat_Tube................ L=560.0mm  R=14.3->14.9
  Top_Tube................. L=587.5mm  R=14.9
  Down_Tube................ L=672.5mm  R=15.9->19.1
  ...
```

## Coordinate system

- **Origin**: bottom bracket center
- **X**: forward (toward front wheel)
- **Y**: upward
- **Z**: right (drive side)

## Limitations

This is a v1 tool built by reverse-engineering the `.bcad` format. Known limitations:

- **Chainstays** are modeled as tapered cones, not oval-to-round lofts with S-bends
- **No tube mitering** at junctions (tubes overlap rather than being trimmed)
- **Bent tubes** are not supported (straight only — though most steel frames use straight tubes)
- **Measure style 3** (Stack & Reach) is the only fully supported geometry mode; other BikeCAD measure styles use a rough estimate for Reach
- **Fork geometry** assumes straight blades; curved fork blades are not modeled
- Visual fidelity is approximate — this is for visualization and reference, not manufacturing

## How it works

1. **BcadParser** reads the `.bcad` file (Java Properties XML) into a key-value store with typed getters
2. **FrameGeometry** computes 3D endpoints for every tube from the parsed parameters, using the BB center as origin
3. **FreeCADScriptGenerator** emits a standalone Python script that uses FreeCAD's `Part.makeCylinder()` and `Part.makeCone()` to create each tube

## Running tests

```bash
python -m pytest tests/ -v
```

## License

MIT
