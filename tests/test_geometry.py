"""Tests for FrameGeometry and FreeCAD script generation."""

import math
import textwrap
from pathlib import Path

import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bcad2freecad import BcadParser, FrameGeometry, FreeCADScriptGenerator, Vec3


@pytest.fixture
def sample_bcad(tmp_path):
    """Create a .bcad file with Gravel.bcad key geometry values."""
    content = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
        <properties>
        <comment>Test geometry</comment>
        <entry key="Head angle">71.0</entry>
        <entry key="Seat angle">73.0</entry>
        <entry key="Stack">662.0</entry>
        <entry key="BB textfield">65.0</entry>
        <entry key="BB length">68.0</entry>
        <entry key="BB diameter">40.0</entry>
        <entry key="CS textfield">450.0</entry>
        <entry key="Head tube length textfield">195.0</entry>
        <entry key="Seat tube length">560.0</entry>
        <entry key="Head tube type">1</entry>
        <entry key="Head tube diameter">38.0</entry>
        <entry key="Head tube d">47.6</entry>
        <entry key="Seat tube type">1</entry>
        <entry key="Seat tube diameter">29.8</entry>
        <entry key="Seat tube bottom diameter textfield">28.6</entry>
        <entry key="Top tube diameter">29.8</entry>
        <entry key="Top tube type">0</entry>
        <entry key="Down tube type">1</entry>
        <entry key="Down tube diameter">31.8</entry>
        <entry key="Down tube front diameter">38.1</entry>
        <entry key="Top tube front center measure style">3</entry>
        <entry key="FCD textfield">410.0</entry>
        <entry key="Fork type">0</entry>
        <entry key="FORK0L">445.0</entry>
        <entry key="FORK0R">55.0</entry>
        <entry key="FORK0D">35.0</entry>
        <entry key="FORK0H">20.0</entry>
        <entry key="FORK0W">40.0</entry>
        <entry key="Dropout spacing">135.0</entry>
        <entry key="INCLUDE_CHAINSTAY">true</entry>
        <entry key="INCLUDE_SEATSTAY">true</entry>
        <entry key="Chain stay horizontal diameter">18.0</entry>
        <entry key="Chain stay vertical diameter">26.0</entry>
        <entry key="Chain stay back diameter">18.0</entry>
        <entry key="Seat stay offset">35.0</entry>
        <entry key="SEATSTAY_VF">19.0</entry>
        <entry key="SEATSTAY_HR">17.0</entry>
        <entry key="SEATSTAYtaperLength">100.0</entry>
        <entry key="SSTopZOFFSET">8.0</entry>
        <entry key="SEATSTAYbrdgCheck">true</entry>
        <entry key="SEATSTAYbrdgdia1">16.0</entry>
        <entry key="SEATSTAYbrdgshift">330.0</entry>
        <entry key="Wall thickness Top tube">0.9</entry>
        <entry key="Wall thickness Seat tube">0.9</entry>
        <entry key="Wall thickness Down tube">0.9</entry>
        <entry key="Wall thickness Chain stay">1.2</entry>
        <entry key="Wall thickness Seat stay">1.0</entry>
        </properties>
    """)
    p = tmp_path / "test.bcad"
    p.write_text(content)
    return p


@pytest.fixture
def geom(sample_bcad):
    parser = BcadParser(str(sample_bcad))
    g = FrameGeometry(parser)
    g.compute()
    return g


class TestVec3:
    def test_add(self):
        a = Vec3(1, 2, 3)
        b = Vec3(4, 5, 6)
        c = a + b
        assert c.x == 5 and c.y == 7 and c.z == 9

    def test_sub(self):
        a = Vec3(5, 5, 5)
        b = Vec3(1, 2, 3)
        c = a - b
        assert c.x == 4 and c.y == 3 and c.z == 2

    def test_mul(self):
        a = Vec3(1, 2, 3) * 2
        assert a.x == 2 and a.y == 4 and a.z == 6

    def test_rmul(self):
        a = 3 * Vec3(1, 2, 3)
        assert a.x == 3 and a.y == 6 and a.z == 9

    def test_length(self):
        assert abs(Vec3(3, 4, 0).length() - 5.0) < 1e-9

    def test_normalized(self):
        n = Vec3(0, 0, 5).normalized()
        assert abs(n.z - 1.0) < 1e-9
        assert abs(n.x) < 1e-9

    def test_zero_normalized(self):
        n = Vec3(0, 0, 0).normalized()
        assert n.length() < 1e-9


class TestReferencePoints:
    def test_bb_center_at_origin(self, geom):
        assert geom.bb_center.x == 0
        assert geom.bb_center.y == 0
        assert geom.bb_center.z == 0

    def test_stack(self, geom):
        """HT top Y coordinate should equal Stack."""
        assert abs(geom.ht_top.y - 662.0) < 0.1

    def test_reach(self, geom):
        """HT top X coordinate should equal Reach."""
        assert abs(geom.ht_top.x - 410.0) < 0.1

    def test_head_tube_length(self, geom):
        """Distance from HT bottom to HT top should equal HT length."""
        ht_len = (geom.ht_top - geom.ht_bottom).length()
        assert abs(ht_len - 195.0) < 0.1

    def test_seat_tube_length(self, geom):
        """Distance from BB to ST top should equal ST length."""
        st_len = (geom.st_top - geom.bb_center).length()
        assert abs(st_len - 560.0) < 0.1

    def test_rear_axle_above_bb(self, geom):
        """Rear axle should be above BB by BB drop amount."""
        assert abs(geom.rear_axle.y - 65.0) < 0.1

    def test_rear_axle_behind_bb(self, geom):
        """Rear axle should be behind (negative X) the BB."""
        assert geom.rear_axle.x < 0

    def test_cs_length(self, geom):
        """Distance from BB to rear axle should approximate CS length."""
        cs_len = geom.rear_axle.length()
        assert abs(cs_len - 450.0) < 1.0

    def test_front_axle_in_front(self, geom):
        """Front axle should be well in front of BB."""
        assert geom.front_axle.x > 400

    def test_front_axle_height_sanity(self, geom):
        """Front axle Y should be within 20mm of BB drop (approximate)."""
        assert abs(geom.front_axle.y - 65.0) < 20

    def test_head_tube_angle(self, geom):
        """Head tube direction should match head angle."""
        ht_vec = geom.ht_top - geom.ht_bottom
        # angle from horizontal = atan2(dy, -dx) since tube goes backward
        angle = math.degrees(math.atan2(ht_vec.y, -ht_vec.x))
        assert abs(angle - 71.0) < 0.1

    def test_seat_tube_angle(self, geom):
        """Seat tube direction should match seat angle."""
        st_vec = geom.st_top - geom.bb_center
        angle = math.degrees(math.atan2(st_vec.y, -st_vec.x))
        assert abs(angle - 73.0) < 0.1


class TestTubes:
    def test_tube_count(self, geom):
        """Should have 15 tubes: BB, HT, ST, TT, DT, 2xCS, 2xSS, bridge,
        2x fork blade, 2x fork crown, steerer."""
        assert len(geom.tubes) == 15

    def test_no_zero_length_tubes(self, geom):
        for t in geom.tubes:
            assert t.length > 1.0, f"{t.name} has near-zero length"

    def test_no_negative_radii(self, geom):
        for t in geom.tubes:
            assert t.radius1 > 0, f"{t.name} has non-positive radius1"
            assert t.radius2 > 0, f"{t.name} has non-positive radius2"

    def test_bb_shell_is_cylinder(self, geom):
        bb = next(t for t in geom.tubes if t.name == "BB_Shell")
        assert bb.is_cylinder
        assert abs(bb.length - 68.0) < 0.1

    def test_head_tube_is_tapered(self, geom):
        ht = next(t for t in geom.tubes if t.name == "Head_Tube")
        assert not ht.is_cylinder
        # Bottom (start) should be larger than top (end)
        assert ht.radius1 > ht.radius2

    def test_chainstays_symmetric(self, geom):
        drive = next(t for t in geom.tubes if t.name == "Chainstay_Drive")
        non_drive = next(t for t in geom.tubes if t.name == "Chainstay_NonDrive")
        assert abs(drive.length - non_drive.length) < 0.01
        assert drive.start.z > 0  # drive side is positive Z
        assert non_drive.start.z < 0

    def test_seatstays_symmetric(self, geom):
        drive = next(t for t in geom.tubes if t.name == "Seatstay_Drive")
        non_drive = next(t for t in geom.tubes if t.name == "Seatstay_NonDrive")
        assert abs(drive.length - non_drive.length) < 0.01

    def test_fork_blades_symmetric(self, geom):
        drive = next(t for t in geom.tubes if t.name == "Fork_Blade_Drive")
        non_drive = next(t for t in geom.tubes if t.name == "Fork_Blade_NonDrive")
        assert abs(drive.length - non_drive.length) < 0.01
        assert drive.start.z > 0
        assert non_drive.start.z < 0

    def test_seatstay_bridge_lateral(self, geom):
        bridge = next(t for t in geom.tubes if t.name == "Seatstay_Bridge")
        # Bridge should span the Z axis (left to right)
        assert bridge.start.z < 0
        assert bridge.end.z > 0
        # X and Y should be the same at both ends
        assert abs(bridge.start.x - bridge.end.x) < 0.01
        assert abs(bridge.start.y - bridge.end.y) < 0.01

    def test_tube_names_unique(self, geom):
        names = [t.name for t in geom.tubes]
        assert len(names) == len(set(names))


class TestFreeCADScriptGenerator:
    def test_generates_valid_python(self, geom):
        gen = FreeCADScriptGenerator(geom.tubes)
        script = gen.generate()
        # Should compile without errors
        compile(script, "<test>", "exec")

    def test_generates_valid_python_hollow(self, geom):
        gen = FreeCADScriptGenerator(geom.tubes, hollow=True)
        script = gen.generate()
        compile(script, "<test>", "exec")

    def test_contains_all_tube_names(self, geom):
        gen = FreeCADScriptGenerator(geom.tubes)
        script = gen.generate()
        for tube in geom.tubes:
            assert tube.name in script

    def test_contains_freecad_imports(self, geom):
        gen = FreeCADScriptGenerator(geom.tubes)
        script = gen.generate()
        assert "import FreeCAD" in script
        assert "import Part" in script

    def test_hollow_includes_cut(self, geom):
        gen = FreeCADScriptGenerator(geom.tubes, hollow=True)
        script = gen.generate()
        assert "outer.cut(inner)" in script

    def test_solid_excludes_cut(self, geom):
        gen = FreeCADScriptGenerator(geom.tubes, hollow=False)
        script = gen.generate()
        assert "outer.cut(inner)" not in script


class TestWithRealFile:
    """Integration tests using the actual Gravel.bcad file."""

    GRAVEL = Path(__file__).resolve().parent.parent / "Gravel.bcad"

    @pytest.mark.skipif(
        not GRAVEL.exists(),
        reason="Gravel.bcad not present",
    )
    def test_full_pipeline(self):
        parser = BcadParser(str(self.GRAVEL))
        geom = FrameGeometry(parser)
        tubes = geom.compute()

        assert len(tubes) == 15

        gen = FreeCADScriptGenerator(tubes)
        script = gen.generate()
        compile(script, "<gravel>", "exec")

    @pytest.mark.skipif(
        not GRAVEL.exists(),
        reason="Gravel.bcad not present",
    )
    def test_dump_params_no_crash(self):
        parser = BcadParser(str(self.GRAVEL))
        geom = FrameGeometry(parser)
        geom.compute()
        output = geom.dump_params()
        assert "Head angle" in output
        assert "Tubes:" in output
