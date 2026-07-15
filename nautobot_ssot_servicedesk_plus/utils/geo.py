"""Geographic classification helpers for ServiceDesk-imported Sites.

NRTC's location taxonomy is Country -> Super Region -> Region (US state) -> Site.
The Site LocationType requires a Region parent, but ServiceDesk gives us only a free-text
site name (usually "City, ST"). We parse the US state from the name and place the Site
under that state's Region (Census Super Region), creating the Region tier on demand.
Names we can't classify fall back to a holding-pen Region named ``UNASSIGNED_REGION``,
which a separate reconciliation pass can re-group later.
"""

import re

from nautobot.dcim.models import Location, LocationType
from nautobot.extras.models import Status

COUNTRY = "US"
UNASSIGNED_REGION = "Unassigned"
UNASSIGNED_SUPER_REGION = "Uncategorized"

# US state (abbr) -> US Census region (our Super Region tier)
CENSUS = {
    **{s: "Northeast" for s in "CT ME MA NH RI VT NJ NY PA".split()},
    **{s: "Midwest" for s in "IL IN MI OH WI IA KS MN MO NE ND SD".split()},
    **{s: "South" for s in "DE FL GA MD NC SC VA DC WV AL KY MS TN AR LA OK TX".split()},
    **{s: "West" for s in "AZ CO ID MT NV NM UT WY AK CA HI OR WA".split()},
}
STATE_NAME = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}
_STATE_NAME_LOWER = {v.lower(): k for k, v in STATE_NAME.items()}

# Best-effort city -> state gazetteer for site names that carry a city but no state token
# (e.g. "El Paso/Cornell"). Deliberately small and limited to unambiguous large metros;
# SITE_REGION_OVERRIDES is the authoritative mechanism and always wins.
CITY_STATE = {
    "el paso": "TX",
    "albuquerque": "NM",
    "las vegas": "NV",
    "salt lake city": "UT",
    "oklahoma city": "OK",
    "new orleans": "LA",
    "san antonio": "TX",
    "phoenix": "AZ",
    "milwaukee": "WI",
    "minneapolis": "MN",
    "indianapolis": "IN",
    "philadelphia": "PA",
    "chicago": "IL",
    "detroit": "MI",
    "seattle": "WA",
    "atlanta": "GA",
    "denver": "CO",
    "boston": "MA",
    "honolulu": "HI",
}

# Authoritative manual site-name -> US state code overrides for names no parser can resolve
# (company/facility names, ambiguous cities). Consulted before parsing; populate with the
# NRTC-known location of each. Example: "Signal House": "TN".
SITE_REGION_OVERRIDES = {}


def parse_state(site_name):
    """Return the 2-letter US state code parsed from a site name, or None.

    Handles trailing 2-letter codes ("Dallas, TX", "Dallas TX"), full state names
    ("Denver, Colorado") and parenthetical suffixes ("Windhorst, TX (Headend)"). When no
    state token is present, applies the CITY_STATE gazetteer to the whole name and to its
    "/", ",", ";", "-"-separated fragments ("El Paso/Cornell" -> TX).
    """
    if not site_name:
        return None
    n = re.sub(r"\([^)]*\)", "", site_name).strip().rstrip(".")
    tokens = re.split(r"[,\s]+", n)
    if tokens and tokens[-1].upper() in CENSUS:
        return tokens[-1].upper()
    low = n.lower()
    for full in sorted(_STATE_NAME_LOWER, key=len, reverse=True):
        if low.endswith(full):
            return _STATE_NAME_LOWER[full]
    for fragment in [low, *(f.strip() for f in re.split(r"[/,;\-]", low))]:
        if fragment in CITY_STATE:
            return CITY_STATE[fragment]
    return None


def ensure_region_parent(site_name):
    """Ensure the target Region exists and return its (globally unique) name.

    Parses the state from ``site_name`` and get_or_creates
    Country(US) -> Super Region(Census) -> Region(state); unparseable names get the
    ``UNASSIGNED_REGION`` holding pen. Returns the Region name to use as the Site's
    ``parent__name``.
    """
    active = Status.objects.get(name="Active")

    def loc(name, type_name, parent):
        ltype = LocationType.objects.get(name=type_name)
        obj, _ = Location.objects.get_or_create(
            name=name, location_type=ltype, defaults={"parent": parent, "status": active}
        )
        return obj

    country = loc(COUNTRY, "Country", None)
    state = SITE_REGION_OVERRIDES.get(site_name) or parse_state(site_name)
    if not state:
        sr = loc(UNASSIGNED_SUPER_REGION, "Super Region", country)
        loc(UNASSIGNED_REGION, "Region", sr)
        return UNASSIGNED_REGION
    sr = loc(CENSUS[state], "Super Region", country)
    region = loc(STATE_NAME[state], "Region", sr)
    return region.name
