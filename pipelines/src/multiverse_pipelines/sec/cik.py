"""CIK handling. The CIK, not the ticker, identifies a company.

The API addresses use ten digits with leading zeros (CIK0000097476.json); the Archives
paths use the plain number (/edgar/data/97476/). Submissions JSON writes the CIK as a
string without zeros, company facts as an integer. Tickers change and are reused, so a
ticker is only an observation with a date, never a key.
"""

import re

_DIGITS = re.compile(r"^\d{1,10}$")


def cik_int(value: str | int) -> int:
    text = str(value).strip().upper().removeprefix("CIK")
    if not _DIGITS.fullmatch(text) or int(text) == 0:
        raise ValueError(f"not a CIK: {value!r} (1 to 10 digits, not zero)")
    return int(text)


def cik10(value: str | int) -> str:
    """Ten digits with leading zeros, as data.sec.gov expects."""
    return f"{cik_int(value):010d}"
