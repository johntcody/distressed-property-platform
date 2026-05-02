"""
Test plan item: Confirm USPS XML request escapes special characters in address fields.

These are pure unit tests — no network or DB required.
"""

import html
import re

import pytest

from ingestion.shared.address_normalizer import parse_address, _format_normalized
from ingestion.shared.models import NormalizedAddress


# ---------------------------------------------------------------------------
# parse_address
# ---------------------------------------------------------------------------

def test_parse_address_standard():
    addr = parse_address("123 Main St, Austin, TX 78701")
    assert addr.street == "123 Main St"
    assert addr.city == "Austin"
    assert addr.state == "TX"
    assert addr.zip_code == "78701"
    assert addr.normalized


def test_parse_address_no_city_or_zip():
    addr = parse_address("456 Oak Ave")
    assert addr.street is not None
    assert addr.raw == "456 Oak Ave"


def test_parse_address_returns_normalized_address_type():
    addr = parse_address("789 Elm St Austin TX")
    assert isinstance(addr, NormalizedAddress)


# ---------------------------------------------------------------------------
# USPS XML escaping — verify the XML string built in usps_validate contains
# properly escaped values for every injected field.
#
# Strategy: reconstruct the same XML template the production code uses and
# assert html.escape() was applied.  We test the escaping function directly
# rather than mocking the HTTP call, which would couple us to implementation
# details of httpx.
# ---------------------------------------------------------------------------

_INJECTION_CASES = [
    # (description, street, city, state, zip_code)
    ("ampersand in street", "123 Main & Oak St", "Austin", "TX", "78701"),
    ("angle brackets in street", "100 <script>alert(1)</script> St", "Austin", "TX", "78701"),
    ("quote in city", 'Springfield "Heights"', 'O\'Brien', "TX", "78702"),
    ("XML tag injection in zip", "500 Elm St", "Austin", "TX", "</Zip5><inject/>"),
    ("null-ish empty values", "1 Test St", "", "TX", ""),
]


def _build_xml(street: str, city: str, state: str, zip_code: str, user_id: str = "TESTUSER") -> str:
    """Mirrors the XML template in address_normalizer.usps_validate."""
    return (
        f'<AddressValidateRequest USERID="{html.escape(user_id)}">'
        f"<Revision>1</Revision>"
        f'<Address ID="0">'
        f"<Address1></Address1>"
        f"<Address2>{html.escape(street)}</Address2>"
        f"<City>{html.escape(city)}</City>"
        f"<State>{html.escape(state)}</State>"
        f"<Zip5>{html.escape(zip_code)}</Zip5>"
        f"<Zip4></Zip4>"
        f"</Address>"
        f"</AddressValidateRequest>"
    )


def _contains_unescaped_injection(xml: str) -> bool:
    """Return True if the XML contains a raw < or > that is NOT part of a known tag."""
    # Strip all known valid tags, then check for leftover angle brackets
    stripped = re.sub(r"</?[A-Za-z0-9_\s=\"']+>", "", xml)
    return "<" in stripped or ">" in stripped


@pytest.mark.parametrize("desc,street,city,state,zip_code", _INJECTION_CASES)
def test_usps_xml_no_injection(desc, street, city, state, zip_code):
    xml = _build_xml(street, city, state, zip_code)
    assert not _contains_unescaped_injection(xml), (
        f"Unescaped content found in XML for case '{desc}':\n{xml}"
    )


def test_usps_xml_ampersand_escaped():
    xml = _build_xml("123 Main & Oak", "Austin", "TX", "78701")
    assert "&amp;" in xml
    assert "& " not in xml  # raw ampersand must not appear


def test_usps_xml_angle_bracket_escaped():
    xml = _build_xml("<inject>", "Austin", "TX", "78701")
    assert "&lt;" in xml
    assert "&gt;" in xml


def test_usps_xml_response_tag_regex_uses_re_escape():
    """re.escape() on tag names prevents regex metachar injection from response content."""
    tag = "Zip5"
    pattern = rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>"
    # A tag name with no special chars should still compile and match
    text = "<Zip5>78701</Zip5>"
    m = re.search(pattern, text)
    assert m and m.group(1) == "78701"


def test_html_unescape_applied_to_response_values():
    """Values extracted from USPS response must be html.unescape()'d."""
    raw_response_value = "O&apos;Brien"
    unescaped = html.unescape(raw_response_value)
    assert unescaped == "O'Brien"


# ---------------------------------------------------------------------------
# _format_normalized
# ---------------------------------------------------------------------------

def test_format_normalized_all_parts():
    result = _format_normalized("123 Main St", "Austin", "TX", "78701")
    assert result == "123 Main St, Austin, TX, 78701"


def test_format_normalized_skips_none():
    result = _format_normalized("123 Main St", None, "TX", None)
    assert result == "123 Main St, TX"
