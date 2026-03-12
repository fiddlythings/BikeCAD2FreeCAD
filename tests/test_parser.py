"""Tests for BcadParser."""

import tempfile
import textwrap
from pathlib import Path

import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bcad2freecad import BcadParser


@pytest.fixture
def sample_bcad(tmp_path):
    """Create a minimal .bcad file for testing."""
    content = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
        <properties>
        <comment>Test file</comment>
        <entry key="Head angle">71.0</entry>
        <entry key="Seat angle">73.0</entry>
        <entry key="Stack">662.0</entry>
        <entry key="BB textfield">65.0</entry>
        <entry key="BB length">68.0</entry>
        <entry key="CS textfield">450.0</entry>
        <entry key="Head tube length textfield">195.0</entry>
        <entry key="Seat tube length">560.0</entry>
        <entry key="Head tube type">1</entry>
        <entry key="Head tube diameter">38.0</entry>
        <entry key="Head tube d">47.6</entry>
        <entry key="Top tube front center measure style">3</entry>
        <entry key="FCD textfield">410.0</entry>
        <entry key="FORK0L">445.0</entry>
        <entry key="FORK0R">55.0</entry>
        <entry key="Fork type">0</entry>
        <entry key="SEATSTAYbrdgCheck">true</entry>
        <entry key="INCLUDE_CHAINSTAY">true</entry>
        <entry key="INCLUDE_SEATSTAY">true</entry>
        <entry key="BB diameter">40.0</entry>
        <entry key="Some bool">false</entry>
        <entry key="Empty value"></entry>
        <entry key="Bad number">not_a_number</entry>
        </properties>
    """)
    p = tmp_path / "test.bcad"
    p.write_text(content)
    return p


@pytest.fixture
def parser(sample_bcad):
    return BcadParser(str(sample_bcad))


class TestBcadParser:
    def test_parse_count(self, parser):
        # 21 real entries (not counting comment)
        assert len(parser.data) >= 20

    def test_get_float(self, parser):
        assert parser.get_float("Head angle") == 71.0
        assert parser.get_float("Stack") == 662.0
        assert parser.get_float("BB textfield") == 65.0

    def test_get_float_default(self, parser):
        assert parser.get_float("nonexistent", 99.9) == 99.9

    def test_get_float_bad_value(self, parser):
        assert parser.get_float("Bad number", -1.0) == -1.0

    def test_get_int(self, parser):
        assert parser.get_int("Head tube type") == 1
        assert parser.get_int("Fork type") == 0

    def test_get_int_default(self, parser):
        assert parser.get_int("nonexistent", 42) == 42

    def test_get_bool(self, parser):
        assert parser.get_bool("SEATSTAYbrdgCheck") is True
        assert parser.get_bool("Some bool") is False

    def test_get_bool_default(self, parser):
        assert parser.get_bool("nonexistent", True) is True
        assert parser.get_bool("nonexistent", False) is False

    def test_get_str(self, parser):
        assert parser.get_str("Head angle") == "71.0"

    def test_get_str_default(self, parser):
        assert parser.get_str("nonexistent", "fallback") == "fallback"

    def test_empty_value(self, parser):
        assert parser.get_str("Empty value") == ""
        assert parser.get_float("Empty value", 5.0) == 5.0

    def test_has(self, parser):
        assert parser.has("Head angle")
        assert not parser.has("nonexistent")

    def test_keys_matching(self, parser):
        matches = parser.keys_matching("tube")
        assert "Head tube type" in matches
        assert "Head tube diameter" in matches
        assert "Seat tube length" in matches


class TestParserWithRealFile:
    """Test against the actual Gravel.bcad if available."""

    GRAVEL = Path(__file__).resolve().parent.parent / "Gravel.bcad"

    @pytest.mark.skipif(
        not GRAVEL.exists(),
        reason="Gravel.bcad not present",
    )
    def test_real_file_parses(self):
        p = BcadParser(str(self.GRAVEL))
        assert len(p.data) > 7000

    @pytest.mark.skipif(
        not GRAVEL.exists(),
        reason="Gravel.bcad not present",
    )
    def test_real_file_key_values(self):
        p = BcadParser(str(self.GRAVEL))
        assert p.get_float("Head angle") == 71.0
        assert p.get_float("Seat angle") == 73.0
        assert p.get_float("Stack") == 662.0
        assert p.get_float("BB textfield") == 65.0
        assert p.get_float("BB length") == 68.0
        assert p.get_float("CS textfield") == 450.0
        assert p.get_float("Head tube length textfield") == 195.0
        assert p.get_float("Seat tube length") == 560.0
        assert p.get_int("Head tube type") == 1
        assert p.get_float("Head tube d") == 47.6
        assert p.get_float("Dropout spacing") == 135.0
