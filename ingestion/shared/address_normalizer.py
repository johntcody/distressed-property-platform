"""Address normalization — parses raw address strings and optionally validates via USPS API."""

import html
import logging
import os
import re
from typing import Optional

import httpx
import usaddress

from .models import NormalizedAddress

log = logging.getLogger(__name__)

# Texas county → city seed map for fallback city inference
_COUNTY_SEAT: dict[str, str] = {
    "hays": "San Marcos",
    "travis": "Austin",
    "williamson": "Georgetown",
    "caldwell": "Lockhart",
    "burnet": "Burnet",
    "bastrop": "Bastrop",
    "lee": "Giddings",
}

_USPS_USER_ID = os.getenv("USPS_USER_ID", "")

# Tag mapping from usaddress library to our fields
_TAG_TO_FIELD = {
    "AddressNumber": "number",
    "StreetNamePreDirectional": "pre_dir",
    "StreetName": "street_name",
    "StreetNamePostType": "street_type",
    "StreetNamePostDirectional": "post_dir",
    "OccupancyType": "unit_type",
    "OccupancyIdentifier": "unit_number",
    "PlaceName": "city",
    "StateName": "state",
    "ZipCode": "zip_code",
}


def parse_address(raw: str) -> NormalizedAddress:
    """Parse a raw address string into structured components using usaddress."""
    raw = raw.strip()
    result = NormalizedAddress(raw=raw)

    try:
        tagged, address_type = usaddress.tag(raw)
    except usaddress.RepeatedLabelError:
        # Fall back to regex extraction on ambiguous input
        result.normalized = _regex_normalize(raw)
        return result

    parts: dict[str, str] = {}
    for tag, value in tagged.items():
        field = _TAG_TO_FIELD.get(tag)
        if field:
            parts[field] = value

    street_parts = filter(None, [
        parts.get("number"),
        parts.get("pre_dir"),
        parts.get("street_name"),
        parts.get("street_type"),
        parts.get("post_dir"),
    ])
    result.street = " ".join(street_parts).title()
    result.city = parts.get("city", "").title() or None
    result.state = parts.get("state", "TX").upper()
    result.zip_code = parts.get("zip_code")

    unit = " ".join(filter(None, [parts.get("unit_type"), parts.get("unit_number")]))
    street_full = f"{result.street} {unit}".strip() if unit else result.street

    result.normalized = _format_normalized(street_full, result.city, result.state, result.zip_code)
    result.confidence = 0.85 if address_type == "Street Address" else 0.5
    return result


def _format_normalized(street: Optional[str], city: Optional[str], state: str, zip_code: Optional[str]) -> str:
    parts = [p for p in [street, city, state, zip_code] if p]
    return ", ".join(parts)


def _regex_normalize(raw: str) -> str:
    """Best-effort cleanup when usaddress fails."""
    cleaned = re.sub(r"\s+", " ", raw).strip()
    cleaned = re.sub(r",\s*,", ",", cleaned)
    return cleaned.title()


async def usps_validate(address: NormalizedAddress) -> NormalizedAddress:
    """
    Call USPS Address Verification API to confirm and standardize the address.
    Requires USPS_USER_ID env var. Returns address unchanged if API unavailable.
    """
    if not _USPS_USER_ID or not address.street:
        return address

    # Escape all user-supplied values to prevent XML injection from scraped data
    xml = (
        f'<AddressValidateRequest USERID="{html.escape(_USPS_USER_ID)}">'
        f"<Revision>1</Revision>"
        f'<Address ID="0">'
        f"<Address1></Address1>"
        f"<Address2>{html.escape(address.street)}</Address2>"
        f"<City>{html.escape(address.city or '')}</City>"
        f"<State>{html.escape(address.state)}</State>"
        f"<Zip5>{html.escape(address.zip_code or '')}</Zip5>"
        f"<Zip4></Zip4>"
        f"</Address>"
        f"</AddressValidateRequest>"
    )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://secure.shippingapis.com/ShippingAPI.dll",
                params={"API": "Verify", "XML": xml},
            )
            resp.raise_for_status()
            text = resp.text

        # Parse USPS XML response — escape tag name to prevent regex metachar injection
        def _extract(tag: str) -> Optional[str]:
            m = re.search(rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", text)
            return html.unescape(m.group(1).strip()) if m else None

        if _extract("Error"):
            return address

        address.street = _extract("Address2") or address.street
        address.city = _extract("City") or address.city
        address.state = _extract("State") or address.state
        address.zip_code = _extract("Zip5") or address.zip_code
        address.normalized = _format_normalized(address.street, address.city, address.state, address.zip_code)
        address.confidence = 1.0

    except Exception as exc:
        log.debug("USPS validation unavailable for '%s': %s", address.street, exc)

    return address


def infer_city_from_county(county: str) -> Optional[str]:
    return _COUNTY_SEAT.get(county.lower())
