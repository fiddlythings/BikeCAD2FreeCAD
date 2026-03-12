#!/usr/bin/env python3
"""BCad2FreeCAD - Convert BikeCAD .bcad files to FreeCAD Python macros.

Reads a .bcad (Java Properties XML) file and generates a standalone FreeCAD
Python script that creates a 3D model of the frame tubes.

Usage:
    python bcad2freecad.py Gravel.bcad -o Gravel_freecad.py
    python bcad2freecad.py Gravel.bcad --dump-params
"""

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1: Parser
# ═══════════════════════════════════════════════════════════════════════════════

class BcadParser:
    """Parse a .bcad (Java Properties XML) file into a key-value store."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.data: dict[str, str] = {}
        self._parse()

    def _parse(self):
        tree = ET.parse(self.path)
        root = tree.getroot()
        for entry in root.findall("entry"):
            key = entry.get("key", "")
            value = entry.text or ""
            self.data[key] = value

    def get_str(self, key: str, default: str = "") -> str:
        return self.data.get(key, default)

    def get_float(self, key: str, default: float = 0.0) -> float:
        raw = self.data.get(key)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    def get_int(self, key: str, default: int = 0) -> int:
        raw = self.data.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.data.get(key)
        if raw is None:
            return default
        return raw.strip().lower() == "true"

    def has(self, key: str) -> bool:
        return key in self.data

    def keys_matching(self, substring: str) -> list[str]:
        """Return all keys containing the given substring (case-insensitive)."""
        sub = substring.lower()
        return [k for k in self.data if sub in k.lower()]


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2-4: Geometry
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Vec3:
    """Simple 3D vector."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, s: float) -> "Vec3":
        return Vec3(self.x * s, self.y * s, self.z * s)

    def __rmul__(self, s: float) -> "Vec3":
        return self.__mul__(s)

    def length(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def normalized(self) -> "Vec3":
        ln = self.length()
        if ln < 1e-9:
            return Vec3(0, 0, 0)
        return Vec3(self.x / ln, self.y / ln, self.z / ln)

    def tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass
class TubeSpec:
    """Specification for one tube to be generated in FreeCAD."""
    name: str
    start: Vec3
    end: Vec3
    radius1: float          # radius at start
    radius2: float          # radius at end (same as radius1 for cylinder)
    wall: float = 0.0       # wall thickness (0 = solid)
    color: tuple[float, float, float] = (0.6, 0.6, 0.65)  # steel gray

    @property
    def direction(self) -> Vec3:
        return (self.end - self.start).normalized()

    @property
    def length(self) -> float:
        return (self.end - self.start).length()

    @property
    def is_cylinder(self) -> bool:
        return abs(self.radius1 - self.radius2) < 0.01


class FrameGeometry:
    """Compute 3D tube positions from parsed .bcad parameters.

    Coordinate system:
        Origin: BB center
        X: forward (toward head tube / front wheel)
        Y: upward
        Z: right (drive side)
    """

    def __init__(self, parser: BcadParser):
        self.p = parser
        self.tubes: list[TubeSpec] = []
        self.warnings: list[str] = []

        # Computed reference points (populated by _compute_reference_points)
        self.bb_center = Vec3(0, 0, 0)
        self.rear_axle = Vec3()
        self.ht_top = Vec3()
        self.ht_bottom = Vec3()
        self.st_top = Vec3()
        self.front_axle = Vec3()

    def compute(self) -> list[TubeSpec]:
        """Compute all tube specs. Returns list of TubeSpec."""
        self._compute_reference_points()
        self._make_bb_shell()
        self._make_head_tube()
        self._make_seat_tube()
        self._make_top_tube()
        self._make_down_tube()
        self._make_chainstays()
        self._make_seatstays()
        self._make_seatstay_bridge()
        self._make_fork()
        return self.tubes

    def _compute_reference_points(self):
        """Derive all reference points from .bcad parameters."""
        p = self.p

        # ── Angles (convert to radians) ──
        head_angle = math.radians(p.get_float("Head angle", 72.0))
        seat_angle = math.radians(p.get_float("Seat angle", 73.0))

        # ── Key dimensions ──
        stack = p.get_float("Stack", 600.0)
        bb_drop = p.get_float("BB textfield", 65.0)
        cs_length = p.get_float("CS textfield", 450.0)
        ht_length = p.get_float("Head tube length textfield", 150.0)
        st_length = p.get_float("Seat tube length", 500.0)

        # ── Reach ──
        # With measure style 3 (Stack & Reach), FCD textfield stores Reach
        measure_style = p.get_int("Top tube front center measure style", 0)
        fcd = p.get_float("FCD textfield", 400.0)
        if measure_style == 3:
            reach = fcd
        else:
            # Fallback: estimate reach from front center distance
            # This is approximate and should be refined for other styles
            reach = fcd - 250  # rough estimate
            self.warnings.append(
                f"Measure style {measure_style} (not Stack&Reach). "
                f"Reach estimated as {reach:.1f}mm from FCD={fcd}. "
                "Geometry may be inaccurate."
            )

        # ── Fork parameters ──
        fork_type = p.get_int("Fork type", 0)
        fork_atc = p.get_float(f"FORK{fork_type}L", 445.0)
        fork_rake = p.get_float(f"FORK{fork_type}R", 55.0)

        # ── Reference points ──

        # Head tube top (defines the Stack & Reach point)
        self.ht_top = Vec3(reach, stack, 0)

        # Head tube axis direction (bottom → top): backward and up
        ht_dir = Vec3(-math.cos(head_angle), math.sin(head_angle), 0)

        # Head tube bottom
        self.ht_bottom = self.ht_top - ht_dir * ht_length

        # Seat tube top
        st_dir = Vec3(-math.cos(seat_angle), math.sin(seat_angle), 0)
        self.st_top = self.bb_center + st_dir * st_length

        # Rear axle: behind and above BB by CS length and BB drop
        rear_axle_y = bb_drop
        rear_axle_x = -math.sqrt(max(cs_length**2 - bb_drop**2, 0))
        self.rear_axle = Vec3(rear_axle_x, rear_axle_y, 0)

        # Front axle: from head tube bottom along fork
        steerer_down = Vec3(math.cos(head_angle), -math.sin(head_angle), 0)
        rake_dir = Vec3(math.sin(head_angle), math.cos(head_angle), 0)
        self.front_axle = (
            self.ht_bottom
            + steerer_down * fork_atc
            + rake_dir * fork_rake
        )

        # ── Sanity checks ──
        front_axle_y = self.front_axle.y
        expected_axle_y = bb_drop
        axle_y_error = abs(front_axle_y - expected_axle_y)
        if axle_y_error > 20:
            self.warnings.append(
                f"Front axle height ({front_axle_y:.1f}mm) differs from "
                f"BB drop ({expected_axle_y:.1f}mm) by {axle_y_error:.1f}mm. "
                "Fork/geometry parameters may be inconsistent."
            )

        # Store key values for dump
        self._params = {
            "Head angle (deg)": math.degrees(head_angle),
            "Seat angle (deg)": math.degrees(seat_angle),
            "Stack": stack,
            "Reach": reach,
            "BB drop": bb_drop,
            "CS length": cs_length,
            "HT length": ht_length,
            "ST length": st_length,
            "Fork ATC": fork_atc,
            "Fork rake": fork_rake,
            "HT top": f"({self.ht_top.x:.1f}, {self.ht_top.y:.1f})",
            "HT bottom": f"({self.ht_bottom.x:.1f}, {self.ht_bottom.y:.1f})",
            "ST top": f"({self.st_top.x:.1f}, {self.st_top.y:.1f})",
            "Rear axle": f"({self.rear_axle.x:.1f}, {self.rear_axle.y:.1f})",
            "Front axle": f"({self.front_axle.x:.1f}, {self.front_axle.y:.1f})",
        }

    # ── Phase 2: Main triangle ─────────────────────────────────────────────

    def _make_bb_shell(self):
        p = self.p
        bb_dia = p.get_float("BB diameter", 40.0)
        bb_len = p.get_float("BB length", 68.0)
        r = bb_dia / 2
        start = Vec3(0, 0, -bb_len / 2)
        end = Vec3(0, 0, bb_len / 2)
        self.tubes.append(TubeSpec(
            name="BB_Shell", start=start, end=end,
            radius1=r, radius2=r,
            wall=3.0,  # typical BB shell wall
            color=(0.45, 0.45, 0.48),
        ))

    def _make_head_tube(self):
        p = self.p
        ht_type = p.get_int("Head tube type", 0)
        top_dia = p.get_float("Head tube diameter", 38.0)
        if ht_type == 1:  # tapered
            bottom_dia = p.get_float("Head tube d", top_dia)
        else:
            bottom_dia = top_dia
        self.tubes.append(TubeSpec(
            name="Head_Tube", start=self.ht_bottom, end=self.ht_top,
            radius1=bottom_dia / 2, radius2=top_dia / 2,
            wall=1.5,
            color=(0.55, 0.55, 0.58),
        ))

    def _make_seat_tube(self):
        p = self.p
        st_type = p.get_int("Seat tube type", 0)
        top_dia = p.get_float("Seat tube diameter", 28.6)
        if st_type == 1:  # tapered
            bottom_dia = p.get_float("Seat tube bottom diameter textfield", top_dia)
        else:
            bottom_dia = top_dia
        self.tubes.append(TubeSpec(
            name="Seat_Tube", start=self.bb_center, end=self.st_top,
            radius1=bottom_dia / 2, radius2=top_dia / 2,
            wall=p.get_float("Wall thickness Seat tube", 0.9),
            color=(0.6, 0.6, 0.63),
        ))

    def _make_top_tube(self):
        p = self.p
        tt_dia = p.get_float("Top tube diameter", 28.6)
        # TT connects ST top to HT top
        self.tubes.append(TubeSpec(
            name="Top_Tube", start=self.st_top, end=self.ht_top,
            radius1=tt_dia / 2, radius2=tt_dia / 2,
            wall=p.get_float("Wall thickness Top tube", 0.9),
            color=(0.6, 0.6, 0.63),
        ))

    def _make_down_tube(self):
        p = self.p
        dt_type = p.get_int("Down tube type", 0)
        rear_dia = p.get_float("Down tube diameter", 31.8)
        if dt_type == 1:
            front_dia = p.get_float("Down tube front diameter", rear_dia)
        else:
            front_dia = rear_dia
        # DT connects BB area to HT bottom
        self.tubes.append(TubeSpec(
            name="Down_Tube", start=self.bb_center, end=self.ht_bottom,
            radius1=rear_dia / 2, radius2=front_dia / 2,
            wall=p.get_float("Wall thickness Down tube", 0.9),
            color=(0.6, 0.6, 0.63),
        ))

    # ── Phase 3: Stays ─────────────────────────────────────────────────────

    def _make_chainstays(self):
        p = self.p
        if not p.get_bool("INCLUDE_CHAINSTAY", True):
            return

        bb_len = p.get_float("BB length", 68.0)
        dropout_spacing = p.get_float("Dropout spacing", 135.0)
        cs_offset = p.get_float("CHAINSTAYOFFSET", 0.0)

        # Chainstay cross-section at BB end: oval
        horz_dia = p.get_float("Chain stay horizontal diameter", 18.0)
        vert_dia = p.get_float("Chain stay vertical diameter", 26.0)
        # At dropout end: round
        rear_dia = p.get_float("Chain stay back diameter", 18.0)

        # For FreeCAD, approximate oval as circle with equivalent area
        # area of ellipse = pi * a * b; equivalent circle r = sqrt(a*b)
        equiv_radius_bb = math.sqrt((horz_dia / 2) * (vert_dia / 2))

        # BB-end z offset: typically starts at BB shell edge
        bb_z_offset = bb_len / 2
        cs_bb_z_position = p.get_float("Chain stay position on BB", 15.0)

        # Dropout z offset: half the dropout spacing
        dropout_z = dropout_spacing / 2

        for side, z_sign in [("Drive", 1.0), ("NonDrive", -1.0)]:
            start = Vec3(0, 0, z_sign * bb_z_offset)
            end = Vec3(
                self.rear_axle.x,
                self.rear_axle.y,
                z_sign * dropout_z,
            )
            self.tubes.append(TubeSpec(
                name=f"Chainstay_{side}",
                start=start, end=end,
                radius1=equiv_radius_bb,
                radius2=rear_dia / 2,
                wall=p.get_float("Wall thickness Chain stay", 1.2),
                color=(0.58, 0.56, 0.55),
            ))

    def _make_seatstays(self):
        p = self.p
        if not p.get_bool("INCLUDE_SEATSTAY", True):
            return

        seat_angle = math.radians(p.get_float("Seat angle", 73.0))
        ss_offset = p.get_float("Seat stay offset", 35.0)
        dropout_spacing = p.get_float("Dropout spacing", 135.0)
        ss_z_offset_top = p.get_float("SSTopZOFFSET", 8.0)

        # Seatstay diameters
        ss_front_dia = p.get_float("SEATSTAY_VF", 19.0)
        ss_rear_dia = p.get_float("SEATSTAY_HR", 17.0)
        taper_len = p.get_float("SEATSTAYtaperLength", 100.0)

        # SS junction on seat tube: offset mm below ST top, along seat tube
        st_dir = Vec3(-math.cos(seat_angle), math.sin(seat_angle), 0)
        ss_junction_2d = self.st_top - st_dir * ss_offset

        # Dropout z offset
        dropout_z = dropout_spacing / 2

        for side, z_sign in [("Drive", 1.0), ("NonDrive", -1.0)]:
            start = Vec3(
                ss_junction_2d.x,
                ss_junction_2d.y,
                z_sign * ss_z_offset_top,
            )
            end = Vec3(
                self.rear_axle.x,
                self.rear_axle.y,
                z_sign * dropout_z,
            )
            self.tubes.append(TubeSpec(
                name=f"Seatstay_{side}",
                start=start, end=end,
                radius1=ss_front_dia / 2,
                radius2=ss_rear_dia / 2,
                wall=p.get_float("Wall thickness Seat stay", 1.0),
                color=(0.58, 0.58, 0.60),
            ))

    def _make_seatstay_bridge(self):
        p = self.p
        if not p.get_bool("SEATSTAYbrdgCheck", False):
            return

        bridge_dia = p.get_float("SEATSTAYbrdgdia1", 16.0)
        # Bridge shift is distance from rear axle along seatstay
        bridge_shift = p.get_float("SEATSTAYbrdgshift", 330.0)

        # Position the bridge between the two seatstays
        # Approximate: fraction along seatstay from dropout end
        # We need the seatstay length to compute the fraction
        seat_angle = math.radians(p.get_float("Seat angle", 73.0))
        ss_offset = p.get_float("Seat stay offset", 35.0)
        st_dir = Vec3(-math.cos(seat_angle), math.sin(seat_angle), 0)
        ss_junction = self.st_top - st_dir * ss_offset

        # Seatstay vector (2D, from dropout to junction)
        ss_vec_2d = Vec3(
            ss_junction.x - self.rear_axle.x,
            ss_junction.y - self.rear_axle.y,
            0,
        )
        ss_length_2d = ss_vec_2d.length()

        if ss_length_2d < 1:
            return

        # fraction along stay from dropout
        frac = min(bridge_shift / ss_length_2d, 0.95)

        dropout_spacing = p.get_float("Dropout spacing", 135.0)
        dropout_z = dropout_spacing / 2
        ss_z_top = p.get_float("SSTopZOFFSET", 8.0)

        # Interpolate position on each seatstay
        bridge_x = self.rear_axle.x + frac * ss_vec_2d.x
        bridge_y = self.rear_axle.y + frac * ss_vec_2d.y
        bridge_z_right = dropout_z + frac * (ss_z_top - dropout_z)
        bridge_z_left = -bridge_z_right

        r = bridge_dia / 2
        self.tubes.append(TubeSpec(
            name="Seatstay_Bridge",
            start=Vec3(bridge_x, bridge_y, bridge_z_left),
            end=Vec3(bridge_x, bridge_y, bridge_z_right),
            radius1=r, radius2=r,
            wall=0.0,
            color=(0.55, 0.55, 0.58),
        ))

    # ── Phase 4: Fork ──────────────────────────────────────────────────────

    def _make_fork(self):
        p = self.p
        fork_type = p.get_int("Fork type", 0)
        prefix = f"FORK{fork_type}"

        fork_atc = p.get_float(f"{prefix}L", 445.0)
        fork_rake = p.get_float(f"{prefix}R", 55.0)
        crown_dia = p.get_float(f"{prefix}D", 35.0)
        dropout_dia = p.get_float(f"{prefix}H", 20.0)
        fork_width = p.get_float(f"{prefix}W", 40.0)

        head_angle = math.radians(p.get_float("Head angle", 72.0))

        # Steerer direction (downward from crown)
        steerer_down = Vec3(math.cos(head_angle), -math.sin(head_angle), 0)
        # Rake direction (perpendicular to steerer, forward)
        rake_dir = Vec3(math.sin(head_angle), math.cos(head_angle), 0)

        # For a straight-blade fork, blades are parallel to steerer but
        # offset by the full rake amount
        blade_top_2d = self.ht_bottom + rake_dir * fork_rake
        blade_bottom_2d = blade_top_2d + steerer_down * fork_atc

        half_w = fork_width / 2

        for side, z_sign in [("Drive", 1.0), ("NonDrive", -1.0)]:
            start = Vec3(blade_top_2d.x, blade_top_2d.y, z_sign * half_w)
            end = Vec3(blade_bottom_2d.x, blade_bottom_2d.y, z_sign * half_w)
            self.tubes.append(TubeSpec(
                name=f"Fork_Blade_{side}",
                start=start, end=end,
                radius1=crown_dia / 2,
                radius2=dropout_dia / 2,
                wall=p.get_float("Wall thickness Down tube", 0.9),
                color=(0.50, 0.50, 0.55),
            ))

        # Fork crown: connects head tube bottom to each blade top
        # FORK0A is crown height along steerer axis
        crown_height = p.get_float(f"{prefix}A", 40.0)
        crown_base = self.ht_bottom + steerer_down * crown_height
        for side, z_sign in [("Drive", 1.0), ("NonDrive", -1.0)]:
            blade_top = Vec3(blade_top_2d.x, blade_top_2d.y, z_sign * half_w)
            self.tubes.append(TubeSpec(
                name=f"Fork_Crown_{side}",
                start=crown_base, end=blade_top,
                radius1=crown_dia / 2, radius2=crown_dia / 2,
                wall=0.0,
                color=(0.50, 0.50, 0.55),
            ))

        # Steerer tube (through head tube)
        steerer_dia = 28.6  # standard 1-1/8" steerer
        self.tubes.append(TubeSpec(
            name="Steerer",
            start=self.ht_bottom, end=self.ht_top,
            radius1=steerer_dia / 2, radius2=steerer_dia / 2,
            wall=2.0,
            color=(0.48, 0.48, 0.50),
        ))

    def dump_params(self) -> str:
        """Return a formatted string of computed geometry parameters."""
        lines = ["Computed Frame Geometry", "=" * 50]
        for k, v in self._params.items():
            lines.append(f"  {k:.<30s} {v}")
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ! {w}")
        lines.append("")
        lines.append("Tubes:")
        for t in self.tubes:
            r_str = f"R={t.radius1:.1f}"
            if not t.is_cylinder:
                r_str = f"R={t.radius1:.1f}->{t.radius2:.1f}"
            lines.append(
                f"  {t.name:.<25s} L={t.length:.1f}mm  {r_str}"
            )
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# FreeCAD Script Generator
# ═══════════════════════════════════════════════════════════════════════════════

class FreeCADScriptGenerator:
    """Generate a standalone FreeCAD Python macro from TubeSpecs."""

    def __init__(self, tubes: list[TubeSpec], hollow: bool = False):
        self.tubes = tubes
        self.hollow = hollow

    def generate(self) -> str:
        parts = [self._header()]
        for tube in self.tubes:
            parts.append(self._make_tube(tube))
        parts.append(self._footer())
        return "\n".join(parts)

    def _header(self) -> str:
        hollow_code = ""
        if self.hollow:
            hollow_code = """
    # Hollow tube: cut inner volume
    if wall > 0 and wall < min(r1, r2):
        ir1 = r1 - wall
        ir2 = r2 - wall
        if abs(ir1 - ir2) < 0.01:
            inner = Part.makeCylinder(ir1, length, s, direction)
        else:
            inner = Part.makeCone(ir1, ir2, length, s, direction)
        shape = outer.cut(inner)
"""
        return f'''\
"""FreeCAD macro generated by BCad2FreeCAD.

Open this file in FreeCAD and run it (Macro > Execute) to create
a 3D model of the bike frame.
"""

import FreeCAD
import Part

doc = FreeCAD.newDocument("BikeFrame")


def make_tube(name, start, end, r1, r2, wall=0, color=(0.6, 0.6, 0.65)):
    """Create a tube (cylinder or cone) from start to end."""
    s = FreeCAD.Vector(*start)
    e = FreeCAD.Vector(*end)
    direction = e - s
    length = direction.Length
    if length < 0.01:
        return None

    if abs(r1 - r2) < 0.01:
        outer = Part.makeCylinder(r1, length, s, direction)
    else:
        outer = Part.makeCone(r1, r2, length, s, direction)

    shape = outer
{hollow_code}
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    obj.ViewObject.ShapeColor = color
    return obj

'''

    def _make_tube(self, t: TubeSpec) -> str:
        s = t.start.tuple()
        e = t.end.tuple()
        wall = t.wall if self.hollow else 0
        return (
            f'make_tube("{t.name}",\n'
            f"    start=({s[0]:.2f}, {s[1]:.2f}, {s[2]:.2f}),\n"
            f"    end=({e[0]:.2f}, {e[1]:.2f}, {e[2]:.2f}),\n"
            f"    r1={t.radius1:.2f}, r2={t.radius2:.2f},\n"
            f"    wall={wall:.1f},\n"
            f"    color=({t.color[0]:.2f}, {t.color[1]:.2f}, {t.color[2]:.2f}))\n"
        )

    def _footer(self) -> str:
        return """
doc.recompute()

# Fit the view if running in GUI mode
try:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.fitAll()
    FreeCADGui.SendMsgToActiveView("ViewFit")
except Exception:
    pass  # headless mode

print("BikeFrame created successfully with %d tubes." % len(doc.Objects))
"""


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="Convert a BikeCAD .bcad file to a FreeCAD Python macro."
    )
    ap.add_argument("bcad_file", help="Path to .bcad file")
    ap.add_argument(
        "-o", "--output",
        help="Output .py file (default: <input>_freecad.py)",
    )
    ap.add_argument(
        "--dump-params", action="store_true",
        help="Print extracted geometry parameters and exit",
    )
    ap.add_argument(
        "--hollow", action="store_true",
        help="Generate hollow tubes (slower render but more realistic)",
    )
    args = ap.parse_args()

    # Parse
    bcad_path = Path(args.bcad_file)
    if not bcad_path.exists():
        print(f"Error: file not found: {bcad_path}", file=sys.stderr)
        sys.exit(1)

    parser = BcadParser(str(bcad_path))
    print(f"Parsed {len(parser.data)} parameters from {bcad_path.name}")

    # Compute geometry
    geom = FrameGeometry(parser)
    tubes = geom.compute()

    # Print warnings
    for w in geom.warnings:
        print(f"  Warning: {w}", file=sys.stderr)

    if args.dump_params:
        print(geom.dump_params())
        sys.exit(0)

    # Generate FreeCAD script
    gen = FreeCADScriptGenerator(tubes, hollow=args.hollow)
    script = gen.generate()

    # Determine output path
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = bcad_path.with_name(bcad_path.stem + "_freecad.py")

    out_path.write_text(script)
    print(f"Wrote {len(tubes)} tubes to {out_path}")
    print(f"Open in FreeCAD: Macro > Execute Macro > {out_path.name}")


if __name__ == "__main__":
    main()
