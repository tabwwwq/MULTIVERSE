"""Data pipelines of MULTIVERSE.

Responsibility: source catalog (Stage 09), SEC raw ingestion with checksums (Stage 10),
XBRL normalization (Stage 11), point-in-time warehouse (Stage 12) and macro vintages
(Stage 13), following docs/04.

Rules: no network access unless MULTIVERSE_ALLOW_NETWORK_DOWNLOADS=true; respect SEC
fair access (declared User-Agent, conservative throttle); raw files are never committed."""

__version__ = "0.1.0"
