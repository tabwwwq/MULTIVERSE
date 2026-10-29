"""SEC raw ingestion (Stage 10, ADR-0017): connectors, immutable archive, audit manifests.

US-GAAP and IFRS: domestic filers report in the ``us-gaap`` taxonomy on 10-K and 10-Q;
foreign private issuers file 20-F or 40-F and may report in ``ifrs-full``. The V2 universe
is domestic US-GAAP filers, so the coverage report counts taxonomies and foreign forms per
company instead of assuming them.

Access: EDGAR data needs no account. The filer accounts of EDGAR Next are for submitting
filings and are never used here; the only identity sent is the declared User-Agent.
"""
