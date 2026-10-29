"""The source catalog of Stage 09 and the command that writes it as JSON.

Every statement about a source comes from its official documentation as read on
2026-10-29 (``VERIFIED_ON``); re-read it before the first download of each source.
Company metadata (CIK, SIC, fiscal year end, filer category, tickers) was checked by
hand on the SEC submissions pages the same day. Anything not checked is a score with
``Evidence.EXPECTED`` and is confirmed on real data in Stages 10 and 11.

Usage:
    uv run python -m multiverse_contracts.source_catalog           # write catalog/sources.json
    uv run python -m multiverse_contracts.source_catalog --check   # exit 1 if the file is stale
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from multiverse_contracts.interventions import InterventionType as T
from multiverse_contracts.sources import (
    AccessCategory,
    AcquisitionStep,
    Authentication,
    CompanyCandidate,
    Criterion,
    DataFormat,
    Dataset,
    DataSource,
    DecisionStatus,
    DictionaryField,
    DocKind,
    DocLink,
    DownloadDecision,
    DownloadScope,
    Evidence,
    FieldRole,
    FieldType,
    KeyStatus,
    Level,
    Licence,
    LicensedNeed,
    RateLimit,
    Redistribution,
    Resale,
    Risk,
    RiskCategory,
    Score,
    SectorPriority,
    SourceCatalog,
)
from multiverse_contracts.version import CONTRACTS_VERSION

# multiverse_contracts/source_catalog.py -> packages/contracts/catalog/
CATALOG_PATH = Path(__file__).resolve().parents[3] / "catalog" / "sources.json"
VERIFIED_ON = date(2026, 10, 29)

AWAITING = DownloadDecision(
    status=DecisionStatus.AWAITING_OWNER,
    note="No automatic download until the owner approves this source (Stage 10 or later).",
)
SEC_SAMPLE_APPROVED = DownloadDecision(
    status=DecisionStatus.APPROVED,
    decided_on=date(2026, 10, 29),
    scope=DownloadScope.SAMPLE,
    note=(
        "Decision D-09: the owner approved a sample of the ten candidates (submissions with "
        "their older-filing pages and company facts, through the API) and one HEAD request for "
        "companyfacts.zip, within 200 MB on disk. Bulk files wait for decision D-10."
    ),
)
RAW_PROVENANCE = (
    "Request URL and the User-Agent or key reference used (never the key itself)",
    "downloaded_at in UTC",
    "HTTP status, Content-Length, Last-Modified and ETag when present",
    "SHA-256 of the file as published, after HTTP gzip is removed",
    "Licence name and terms version in force on the download date",
)


def field(name: str, kind: FieldType, role: FieldRole, description: str) -> DictionaryField:
    return DictionaryField(name=name, type=kind, role=role, description=description)


def doc(title: str, url: str, kind: DocKind) -> DocLink:
    return DocLink(title=title, url=url, kind=kind)


STR, INT, DEC, DATE, DT, CODE, BOOL, OBJ = (
    FieldType.STRING,
    FieldType.INTEGER,
    FieldType.DECIMAL,
    FieldType.DATE,
    FieldType.DATETIME,
    FieldType.CODE,
    FieldType.BOOLEAN,
    FieldType.OBJECT,
)
ID, PER, KT, VAL, UNIT, REV, META = (
    FieldRole.IDENTIFIER,
    FieldRole.PERIOD,
    FieldRole.KNOWLEDGE_TIME,
    FieldRole.VALUE,
    FieldRole.UNIT,
    FieldRole.REVISION,
    FieldRole.METADATA,
)

SEC_APIS = doc(
    "EDGAR application programming interfaces",
    "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
    DocKind.API_REFERENCE,
)
SEC_FAIR_ACCESS = doc(
    "Accessing EDGAR data (fair access)",
    "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data",
    DocKind.ACCESS_POLICY,
)
SEC_POLICY = doc(
    "SEC.gov privacy and security policy: website dissemination and internet security",
    "https://www.sec.gov/privacy",
    DocKind.TERMS,
)

SEC = DataSource(
    source_id="sec-edgar",
    name="SEC EDGAR",
    publisher="U.S. Securities and Exchange Commission",
    region="United States",
    priority=1,
    access=AccessCategory.PUBLIC_ACCESS,
    authentication=Authentication.DECLARED_USER_AGENT,
    key_status=KeyStatus.NOT_REQUIRED,
    licence=Licence(
        name="SEC.gov website dissemination policy",
        summary=(
            "Information on sec.gov is public information and may be copied or further "
            "distributed; the SEC asks for citation as the source and forbids use of its seal "
            "and logos. Resale is not addressed, so it is not treated as granted."
        ),
        redistribution=Redistribution.PUBLIC_INFORMATION,
        resale=Resale.NOT_GRANTED,
        attribution="Source: U.S. Securities and Exchange Commission, EDGAR.",
        exceptions=(
            "The SEC cannot guarantee the accuracy of the financial statement data sets; "
            "they do not replace the filings."
        ),
    ),
    rate_limit=RateLimit(
        documented=(
            "No more than 10 requests per second in total, regardless of the number of "
            "machines; the SEC may limit request rates and block IP addresses that submit "
            "excessive requests."
        ),
        documented_requests_per_second="10",
        chosen_requests_per_second="2",
    ),
    request_rules=(
        "Declare a User-Agent with an organisation name and a contact email; the app "
        "refuses to start downloads without MULTIVERSE_SEC_USER_AGENT containing '@'.",
        "Send Accept-Encoding: gzip, deflate.",
        "Download only what is needed: history from bulk files, not API loops.",
        "One request at a time through a token bucket of 2 requests per second for the "
        "whole process.",
        "No crawling of sec.gov pages; only the documented API and bulk file addresses.",
    ),
    retry_policy=(
        "Retry only 429, 500, 502, 503 and 504, at most 3 times, with exponential backoff "
        "from 10 seconds plus jitter and Retry-After when sent. Stop the whole run on 403: "
        "it means the access policy was violated."
    ),
    checksum_policy=(
        "The SEC publishes no checksums for these files, so MULTIVERSE computes SHA-256 on "
        "receipt, stores it with Last-Modified and ETag, and never overwrites a raw file: a "
        "changed file is a new snapshot."
    ),
    official_hosts=("www.sec.gov", "data.sec.gov"),
    docs=(SEC_APIS, SEC_FAIR_ACCESS, SEC_POLICY),
    datasets=(
        Dataset(
            dataset_id="sec-submissions",
            title="Submissions (filing history)",
            description=(
                "Per company: current name, former names with dates, tickers, exchanges, "
                "SIC, fiscal year end, filer category and the list of filings."
            ),
            endpoints=(
                "https://data.sec.gov/submissions/CIK{cik10}.json",
                "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip",
            ),
            formats=(DataFormat.JSON, DataFormat.ZIP),
            update_frequency=(
                "API in real time (typical delay under a second); the ZIP is recompiled "
                "nightly at about 03:00 ET."
            ),
            knowledge_time=(
                "acceptanceDateTime of each filing, with filingDate as the official date; "
                "the time zone of acceptanceDateTime is checked against the filing index in "
                "Stage 10 before it is used for leakage rules."
            ),
            revision_semantics=(
                "Company fields show the current state (current tickers only); history comes "
                "from formerNames and from the filings themselves. Amendments are separate "
                "filings such as 10-K/A."
            ),
            coverage=(
                "Every EDGAR filer. The recent block holds at least one year or 1,000 filings; "
                "older filings are in linked files."
            ),
            identifiers=("CIK, 10 digits with leading zeros", "Accession number", "Ticker"),
            provenance=RAW_PROVENANCE,
            fields=(
                field("cik", STR, ID, "Central Index Key, the stable company identifier."),
                field("name", STR, META, "Current registered name."),
                field("formerNames", FieldType.ARRAY, META, "Earlier names with from and to."),
                field("tickers", FieldType.ARRAY, ID, "Current tickers only; reused over time."),
                field("exchanges", FieldType.ARRAY, META, "Current listing exchanges."),
                field("sic", CODE, META, "Standard Industrial Classification code."),
                field("fiscalYearEnd", CODE, PER, "Month and day, for example 1231."),
                field("category", STR, META, "Filer category, for example large accelerated."),
                field("filings.recent.accessionNumber", STR, ID, "Identifier of a filing."),
                field("filings.recent.form", CODE, META, "Form type: 10-K, 10-Q, 8-K, 10-K/A."),
                field("filings.recent.reportDate", DATE, PER, "Period the filing reports on."),
                field("filings.recent.filingDate", DATE, KT, "Official filing date."),
                field("filings.recent.acceptanceDateTime", DT, KT, "When EDGAR accepted it."),
                field("filings.recent.isXBRL", BOOL, META, "Whether the filing has XBRL data."),
            ),
            docs=(SEC_APIS,),
        ),
        Dataset(
            dataset_id="sec-companyfacts",
            title="XBRL company facts and frames",
            description=(
                "All XBRL facts of a company from standard taxonomies (us-gaap, ifrs-full, "
                "dei, srt) that apply to the whole filing entity, one array per unit."
            ),
            endpoints=(
                "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",
                "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/{taxonomy}/{tag}.json",
                "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json",
                "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
            ),
            formats=(DataFormat.JSON, DataFormat.ZIP),
            update_frequency=(
                "API typically within a minute of dissemination; the ZIP is recompiled nightly "
                "at about 03:00 ET."
            ),
            knowledge_time="filed (date of the filing that reported the fact), with accn.",
            revision_semantics=(
                "The same period can appear several times: in later filings, restated, or as "
                "comparatives. Facts are kept with their accession and filing date; the "
                "original value is the earliest filed one, the latest is the newest."
            ),
            coverage=(
                "Forms 10-Q, 10-K, 8-K, 20-F, 40-F, 6-K and variants; only non-custom "
                "taxonomies, so company extension tags are missing."
            ),
            identifiers=("CIK", "Taxonomy and tag", "Unit", "Accession number (accn)"),
            provenance=RAW_PROVENANCE,
            fields=(
                field("cik", INT, ID, "Company identifier."),
                field("entityName", STR, META, "Company name."),
                field("facts.{taxonomy}.{tag}", OBJ, ID, "Concept, with label and description."),
                field("units.{unit}", FieldType.ARRAY, UNIT, "Unit, for example USD or shares."),
                field("start", DATE, PER, "Start of a duration; absent for instants."),
                field("end", DATE, PER, "End of the duration or the instant."),
                field("val", DEC, VAL, "Reported value in the unit, not scaled."),
                field("accn", STR, REV, "Accession number of the filing that reported it."),
                field("fy", INT, PER, "Fiscal year of the filing, not of the fact."),
                field("fp", CODE, PER, "Fiscal period of the filing: FY, Q1, Q2, Q3."),
                field("form", CODE, META, "Form of the filing."),
                field("filed", DATE, KT, "Filing date of the reporting filing."),
                field("frame", CODE, PER, "Calendar frame such as CY2019Q1I, when assigned."),
            ),
            size=(
                "The size of companyfacts.zip is read with one HEAD request after the owner's "
                "decision; it is not assumed here."
            ),
            docs=(SEC_APIS,),
        ),
        Dataset(
            dataset_id="sec-financial-statement-data-sets",
            title="Financial Statement Data Sets",
            description=(
                "Numbers from the face financial statements of every XBRL filing, quarterly, "
                "presented without change from the reports as filed."
            ),
            endpoints=(
                "https://www.sec.gov/files/dera/data/financial-statement-data-sets/{yyyy}q{q}.zip",
            ),
            formats=(DataFormat.ZIP, DataFormat.TSV),
            update_frequency=(
                "Quarterly; a filing made after a quarter's last business day appears in the "
                "next quarter's file."
            ),
            knowledge_time="filed and accepted of the submission (SUB table).",
            revision_semantics=(
                "As filed: an amendment or a later filing is a new submission; nothing is "
                "overwritten, which makes these files the source of original vintages."
            ),
            coverage="January 2009 to September 2026 (71 quarterly files at the check date).",
            identifiers=("adsh (accession number)", "CIK", "Tag and taxonomy version"),
            provenance=RAW_PROVENANCE,
            fields=(
                field("sub.adsh", STR, ID, "Accession number, key of the submission."),
                field("sub.cik", INT, ID, "Company identifier."),
                field("sub.form", CODE, META, "Form type."),
                field("sub.period", DATE, PER, "Balance sheet date of the report."),
                field("sub.fy", INT, PER, "Fiscal year."),
                field("sub.fp", CODE, PER, "Fiscal period."),
                field("sub.filed", DATE, KT, "Filing date."),
                field("sub.accepted", DT, KT, "Acceptance date and time."),
                field("sub.prevrpt", BOOL, REV, "Whether a later filing amended this one."),
                field("num.tag", STR, ID, "Concept name."),
                field("num.version", STR, ID, "Taxonomy, or the accession for custom tags."),
                field("num.ddate", DATE, PER, "End date of the value."),
                field("num.qtrs", INT, PER, "Duration in quarters; 0 for an instant."),
                field("num.uom", CODE, UNIT, "Unit of measure."),
                field("num.segments", STR, META, "Segment of the value; empty when consolidated."),
                field("num.coreg", STR, META, "Co-registrant; empty for the filer itself."),
                field("num.value", DEC, VAL, "Value as reported."),
            ),
            size="From 13.22 KB (2009 Q1) to 121.92 MB (2025 Q3) per quarterly ZIP.",
            docs=(
                doc(
                    "Financial Statement Data Sets",
                    "https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets",
                    DocKind.DATASET_PAGE,
                ),
                doc(
                    "Financial Statement Data Sets: scope, organisation and table definitions",
                    "https://www.sec.gov/files/financial-statement-data-sets.pdf",
                    DocKind.DOCUMENTATION,
                ),
            ),
        ),
        Dataset(
            dataset_id="sec-financial-statement-notes-data-sets",
            title="Financial Statement and Notes Data Sets",
            description=(
                "Text and numbers from all financial statements and their notes, flattened; "
                "needed where a metric is only disclosed in a note."
            ),
            endpoints=(
                "https://www.sec.gov/files/dera/data/financial-statement-notes-data-sets/{yyyy}_{mm}_notes.zip",
                "https://www.sec.gov/files/dera/data/financial-statement-notes-data-sets/{yyyy}q{q}_notes.zip",
            ),
            formats=(DataFormat.ZIP, DataFormat.TSV),
            update_frequency=(
                "Monthly since November 2020, quarterly before; monthly files are consolidated "
                "into quarterly files after a year."
            ),
            knowledge_time="filed and accepted of the submission.",
            revision_semantics="As filed, like the Financial Statement Data Sets.",
            coverage="January 2009 to September 2026.",
            identifiers=("adsh (accession number)", "CIK", "Tag and taxonomy version"),
            provenance=RAW_PROVENANCE,
            fields=(
                field("adsh", STR, ID, "Accession number."),
                field("tag", STR, ID, "Concept name."),
                field("value", DEC, VAL, "Numeric value; text facts are in a separate table."),
            ),
            size="From 27.41 KB (2009 Q1) to 810.44 MB (2021 Q1) per file.",
            docs=(
                doc(
                    "Financial Statement and Notes Data Sets",
                    "https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets",
                    DocKind.DATASET_PAGE,
                ),
                doc(
                    "The Financial Statement and Notes Data: table definitions",
                    "https://www.sec.gov/files/aqfsn_1.pdf",
                    DocKind.DOCUMENTATION,
                ),
            ),
        ),
        Dataset(
            dataset_id="sec-filing-documents",
            title="Filing documents (EDGAR archives)",
            description=(
                "The filings themselves: 10-K, 10-Q and 8-K documents, the evidence for "
                "decision events in the event registry."
            ),
            endpoints=("https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/",),
            formats=(DataFormat.HTML, DataFormat.XML),
            update_frequency="As filed.",
            knowledge_time="Acceptance date and time of the filing.",
            revision_semantics="Never changed; amendments are new filings.",
            coverage="All EDGAR filings.",
            identifiers=("CIK", "Accession number", "Primary document name"),
            provenance=RAW_PROVENANCE,
            fields=(
                field("primaryDocument", STR, ID, "File name of the main document."),
                field("items", STR, META, "8-K item numbers, for example 2.01 for an acquisition."),
            ),
            docs=(SEC_FAIR_ACCESS,),
        ),
    ),
    verified_on=VERIFIED_ON,
    download=SEC_SAMPLE_APPROVED,
    notes=(
        "data.sec.gov does not support CORS: requests come from the server, never the browser.",
        "The SEC offers no technical support for scripted downloads.",
    ),
)

FRED_OBSERVATIONS = doc(
    "fred/series/observations",
    "https://fred.stlouisfed.org/docs/api/fred/series_observations.html",
    DocKind.API_REFERENCE,
)
FRED_TERMS = doc(
    "FRED API terms of use", "https://fred.stlouisfed.org/docs/api/terms_of_use.html", DocKind.TERMS
)

FRED = DataSource(
    source_id="fred-alfred",
    name="FRED and ALFRED",
    publisher="Federal Reserve Bank of St. Louis",
    region="United States",
    priority=2,
    access=AccessCategory.API_KEY,
    authentication=Authentication.API_KEY,
    key_status=KeyStatus.OWNER_MUST_REGISTER,
    licence=Licence(
        name="FRED API terms of use",
        summary=(
            "A registered key is required. Series owned by third parties need the owner's "
            "permission for anything beyond personal use; they carry 'Copyright' in their "
            "notes. Applications must show that they use the FRED API without endorsement."
        ),
        redistribution=Redistribution.PERMISSION_REQUIRED,
        resale=Resale.NOT_GRANTED,
        attribution=(
            "This product uses the FRED® API but is not endorsed or certified by the Federal "
            "Reserve Bank of St. Louis."
        ),
        exceptions=(
            "Free access does not grant permission for third-party series; terms may change "
            "without notice."
        ),
    ),
    rate_limit=RateLimit(
        documented=(
            "No number is published; the Bank may limit bandwidth or transactions and forbids "
            "an unreasonable amount of bandwidth."
        ),
        chosen_requests_per_second="1",
    ),
    request_rules=(
        "The key comes from MULTIVERSE_FRED_API_KEY (a secret, never logged, never in the "
        "browser or the repository).",
        "Request vintages explicitly (realtime_start, realtime_end or vintage_dates); never "
        "use today's values for history.",
        "Check each series' notes for 'Copyright' before storing it.",
    ),
    retry_policy=(
        "Retry 429 and 5xx at most 3 times with exponential backoff from 5 seconds; stop on "
        "400 or 401, which mean a bad request or key."
    ),
    checksum_policy=(
        "No checksums are published: SHA-256 of each response, stored with the series "
        "last_updated and the requested real-time period."
    ),
    official_hosts=("fred.stlouisfed.org", "api.stlouisfed.org", "alfred.stlouisfed.org"),
    docs=(
        FRED_OBSERVATIONS,
        FRED_TERMS,
        doc(
            "Real-time periods",
            "https://fred.stlouisfed.org/docs/api/fred/realtime_period.html",
            DocKind.DOCUMENTATION,
        ),
    ),
    datasets=(
        Dataset(
            dataset_id="fred-series-observations",
            title="Series observations with vintages",
            description="Values of a series as known in a real-time period or on vintage dates.",
            endpoints=("https://api.stlouisfed.org/fred/series/observations?series_id={id}",),
            formats=(DataFormat.JSON, DataFormat.XML, DataFormat.CSV, DataFormat.XLSX),
            update_frequency="With each release of the series.",
            knowledge_time=(
                "realtime_start of the observation: the date it became known. Dates only, no "
                "time of day."
            ),
            revision_semantics=(
                "Real-time periods mark when a value was true; output_type 2 gives values by "
                "vintage date, 4 gives the initial release only. The default is today's "
                "values, which must not be used for history."
            ),
            coverage="Real-time dates from 1776-07-04 to 9999-12-31 as API bounds.",
            identifiers=("series_id", "realtime_start", "date"),
            provenance=RAW_PROVENANCE,
            fields=(
                field("realtime_start", DATE, KT, "First date the value was known."),
                field("realtime_end", DATE, REV, "Last date the value was current."),
                field("date", DATE, PER, "Observation period."),
                field("value", DEC, VAL, "Value as text; '.' marks a missing value."),
            ),
            size="At most 100,000 observations per request; vintage downloads are capped lower.",
            docs=(FRED_OBSERVATIONS,),
        ),
        Dataset(
            dataset_id="fred-series-vintagedates",
            title="Vintage dates of a series",
            description="Dates on which a series was revised or newly released.",
            endpoints=("https://api.stlouisfed.org/fred/series/vintagedates?series_id={id}",),
            formats=(DataFormat.JSON, DataFormat.XML),
            update_frequency="With each release of the series.",
            knowledge_time="Each vintage date is a date the data changed.",
            revision_semantics="Lists every vintage; use it to fetch each one explicitly.",
            coverage="From the first vintage stored in ALFRED for the series.",
            identifiers=("series_id", "vintage date"),
            provenance=RAW_PROVENANCE,
            fields=(
                field("vintage_dates", FieldType.ARRAY, KT, "Dates of revisions or releases."),
            ),
            docs=(
                doc(
                    "fred/series/vintagedates",
                    "https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html",
                    DocKind.API_REFERENCE,
                ),
            ),
        ),
        Dataset(
            dataset_id="fred-release-dates",
            title="Release dates",
            description="Calendar of the dates a release published data.",
            endpoints=("https://api.stlouisfed.org/fred/release/dates?release_id={id}",),
            formats=(DataFormat.JSON, DataFormat.XML),
            update_frequency="With the release calendar.",
            knowledge_time=(
                "Release date only, no time of day: a value is used from the next day unless "
                "the agency's release time is documented (Stage 13)."
            ),
            revision_semantics="A calendar, not values.",
            coverage="From 1776-07-04 as the earliest API bound.",
            identifiers=("release_id", "date"),
            provenance=RAW_PROVENANCE,
            fields=(
                field("release_id", INT, ID, "Release identifier."),
                field("date", DATE, KT, "Release date without time."),
            ),
            docs=(
                doc(
                    "fred/release/dates",
                    "https://fred.stlouisfed.org/docs/api/fred/release_dates.html",
                    DocKind.API_REFERENCE,
                ),
            ),
        ),
        Dataset(
            dataset_id="fred-series",
            title="Series metadata",
            description="Title, units, frequency, seasonal adjustment and notes of a series.",
            endpoints=("https://api.stlouisfed.org/fred/series?series_id={id}",),
            formats=(DataFormat.JSON, DataFormat.XML),
            update_frequency="When the series changes.",
            knowledge_time="last_updated, a timestamp with a UTC offset.",
            revision_semantics="Metadata also has real-time periods.",
            coverage="Every FRED series.",
            identifiers=("series_id",),
            provenance=RAW_PROVENANCE,
            fields=(
                field("id", STR, ID, "Series identifier, for example FEDFUNDS."),
                field("title", STR, META, "Series title."),
                field("frequency", CODE, PER, "Observation frequency."),
                field("units", STR, UNIT, "Units of the values."),
                field("seasonal_adjustment", CODE, META, "Seasonal adjustment."),
                field("last_updated", DT, REV, "Last update with UTC offset."),
                field("notes", STR, META, "Notes; 'Copyright' marks third-party data."),
            ),
            docs=(
                doc(
                    "fred/series",
                    "https://fred.stlouisfed.org/docs/api/fred/series.html",
                    DocKind.API_REFERENCE,
                ),
            ),
        ),
    ),
    verified_on=VERIFIED_ON,
    download=AWAITING,
    notes=(
        "Creating the FRED account and key is the owner's step; the assistant never creates "
        "accounts.",
        "ALFRED is the same API with real-time parameters.",
    ),
)

ECB_DATA = doc(
    "ECB Data Portal web service: data queries",
    "https://data.ecb.europa.eu/help/api/data",
    DocKind.API_REFERENCE,
)
ECB = DataSource(
    source_id="ecb-data-portal",
    name="ECB Data Portal (SDMX)",
    publisher="European Central Bank",
    region="Euro area",
    priority=3,
    access=AccessCategory.PUBLIC_ACCESS,
    authentication=Authentication.NONE,
    key_status=KeyStatus.NOT_REQUIRED,
    licence=Licence(
        name="ESCB statistics usage policy",
        summary=(
            "Free access and free reuse of public ESCB statistics, for commercial or "
            "non-commercial use, if the source is quoted and the statistics and metadata are "
            "not modified."
        ),
        redistribution=Redistribution.REUSE_WITH_CONDITIONS,
        resale=Resale.ALLOWED_BY_LICENCE,
        attribution="Source: ECB statistics.",
        exceptions="Third-party data needs the originator's prior permission.",
    ),
    rate_limit=RateLimit(
        documented="No limit is published in the API help pages.",
        chosen_requests_per_second="1",
    ),
    request_rules=(
        "HTTPS only, entry point data-api.ecb.europa.eu/service/.",
        "Refresh with updatedAfter or If-Modified-Since instead of full downloads.",
        "Derived series are labelled as derived and keep the original next to them.",
    ),
    retry_policy="Retry 429 and 5xx at most 3 times with exponential backoff from 5 seconds.",
    checksum_policy="SHA-256 of each response, stored with the query and updatedAfter used.",
    official_hosts=("data.ecb.europa.eu", "data-api.ecb.europa.eu", "www.ecb.europa.eu"),
    docs=(
        doc(
            "ECB Data Portal web services: overview",
            "https://data.ecb.europa.eu/help/api/overview",
            DocKind.DOCUMENTATION,
        ),
        ECB_DATA,
        doc(
            "Usage policy of ESCB statistics",
            "https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html",
            DocKind.TERMS,
        ),
    ),
    datasets=(
        Dataset(
            dataset_id="ecb-series",
            title="Statistical series by dataflow and key",
            description=(
                "Any series of the portal, for example exchange rates (dataflow EXR, key "
                "D.USD.EUR.SP00.A); dataflows are listed by a metadata query."
            ),
            endpoints=(
                "https://data-api.ecb.europa.eu/service/data/{flowRef}/{key}",
                "https://data-api.ecb.europa.eu/service/dataflow",
            ),
            formats=(DataFormat.SDMX_ML, DataFormat.JSON, DataFormat.CSV),
            update_frequency="Depends on the series; updatedAfter returns the changes.",
            knowledge_time=(
                "With includeHistory=true each version shows when data were released, revised "
                "or deleted."
            ),
            revision_semantics=(
                "Default is the version in production; includeHistory=true returns all previous "
                "versions; updatedAfter returns added, revised and deleted observations."
            ),
            coverage="Depends on the dataflow.",
            identifiers=("flowRef (agency, dataflow, version)", "Series key", "TIME_PERIOD"),
            provenance=RAW_PROVENANCE,
            fields=(
                field("KEY", STR, ID, "Series key, dimensions joined with dots."),
                field("TIME_PERIOD", STR, PER, "Period in ISO 8601 or SDMX form."),
                field("OBS_VALUE", DEC, VAL, "Observation value."),
                field("OBS_STATUS", CODE, META, "Status of the observation."),
            ),
            docs=(ECB_DATA,),
        ),
    ),
    verified_on=VERIFIED_ON,
    download=AWAITING,
    notes=(
        "V2 covers USD reporters only (decision D-04), so ECB series start with FX and euro "
        "rates as macro context, low priority.",
    ),
)

WB_API = doc(
    "Indicators API documentation",
    "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation",
    DocKind.API_REFERENCE,
)
WORLD_BANK = DataSource(
    source_id="world-bank",
    name="World Bank Indicators API v2",
    publisher="World Bank",
    region="Global",
    priority=4,
    access=AccessCategory.PUBLIC_ACCESS,
    authentication=Authentication.NONE,
    key_status=KeyStatus.NOT_REQUIRED,
    licence=Licence(
        name="World Bank Terms of Use for Datasets (CC BY 4.0 unless labelled otherwise)",
        summary=(
            "Datasets are under CC BY 4.0 with additional terms, unless labelled otherwise; "
            "credit the source and indicate changes; no implied endorsement."
        ),
        redistribution=Redistribution.OPEN_LICENCE,
        resale=Resale.ALLOWED_BY_LICENCE,
        attribution="Source: World Bank, World Development Indicators (CC BY 4.0).",
        exceptions=(
            "Some indicators come from third parties and may not be redistributed without "
            "their consent; each dataset's metadata states its terms."
        ),
    ),
    rate_limit=RateLimit(
        documented=(
            "No rate limit is published; at most 60 indicators per request and 4,000 "
            "characters per URL."
        ),
        chosen_requests_per_second="1",
    ),
    request_rules=(
        "Use format=json and page through results (50 per page by default).",
        "Check each indicator's source and licence in its metadata before storing it.",
    ),
    retry_policy="Retry 5xx at most 3 times with exponential backoff from 5 seconds.",
    checksum_policy="SHA-256 of each response, stored with lastupdated of the source.",
    official_hosts=(
        "datahelpdesk.worldbank.org",
        "api.worldbank.org",
        "www.worldbank.org",
        "datacatalog.worldbank.org",
        "datatopics.worldbank.org",
    ),
    docs=(
        WB_API,
        doc(
            "API basic call structures",
            "https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures",
            DocKind.DOCUMENTATION,
        ),
        doc(
            "Terms of Use for Datasets",
            "https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets",
            DocKind.TERMS,
        ),
        doc(
            "Data catalog licences",
            "https://datacatalog.worldbank.org/public-licenses",
            DocKind.TERMS,
        ),
    ),
    datasets=(
        Dataset(
            dataset_id="wb-wdi",
            title="World Development Indicators (current version)",
            description="Annual structural indicators by country, for example GDP growth.",
            endpoints=(
                "https://api.worldbank.org/v2/country/{iso}/indicator/{indicator}?format=json",
            ),
            formats=(DataFormat.JSON, DataFormat.XML, DataFormat.JSON_STAT),
            update_frequency="With WDI releases.",
            knowledge_time=(
                "Not per value: the current API returns the latest version only, so a value "
                "is usable only from the release that published it (WDI archives)."
            ),
            revision_semantics="Latest values only; earlier versions are in the WDI archives.",
            coverage="Countries and aggregates; most series annual.",
            identifiers=("Indicator code", "ISO3 country code", "date"),
            provenance=RAW_PROVENANCE,
            fields=(
                field("indicator.id", CODE, ID, "Indicator code."),
                field("countryiso3code", CODE, ID, "ISO 3166 alpha-3 country code."),
                field("date", STR, PER, "Year or period."),
                field("value", DEC, VAL, "Value; null when missing."),
                field("lastupdated", DATE, REV, "Last update of the source, in the page header."),
            ),
            docs=(WB_API,),
        ),
        Dataset(
            dataset_id="wb-wdi-archives",
            title="WDI database archives (vintages)",
            description="Earlier WDI versions, with version as a fourth dimension (YYYYMM).",
            endpoints=("https://api.worldbank.org/v2/sources/57",),
            formats=(DataFormat.JSON, DataFormat.XML, DataFormat.XLSX),
            update_frequency="A new version with each WDI release.",
            knowledge_time="The version (YYYYMM) is the release a value was public in.",
            revision_semantics=(
                "Series codes were reused with different base years or currencies across "
                "versions: compare versions with care."
            ),
            coverage="Electronic WDI releases back to 1989.",
            identifiers=("Version (YYYYMM)", "Indicator code", "Country code"),
            provenance=RAW_PROVENANCE,
            fields=(field("version", CODE, KT, "WDI release, YYYYMM."),),
            docs=(
                doc(
                    "WDI archives",
                    "https://datatopics.worldbank.org/world-development-indicators/wdi-archives.html",
                    DocKind.DATASET_PAGE,
                ),
            ),
        ),
    ),
    verified_on=VERIFIED_ON,
    download=AWAITING,
    notes=("Annual values are never spread over quarters before their release (docs/04).",),
)

LICENSED_NEEDS = (
    LicensedNeed(
        need_id="market-prices",
        title="Share prices with delisted companies and corporate actions",
        why=(
            "Return-based checks and any price per share need survivorship-free prices with "
            "splits, dividends and delistings."
        ),
        without_it=(
            "Valuation is a DCF estimate without a share price (docs/04); no return-based "
            "validation."
        ),
        requirement="Written licence terms covering storage, derived outputs and publication.",
        earliest_version="V3",
        status="not_selected",
    ),
    LicensedNeed(
        need_id="earnings-transcripts",
        title="Earnings call transcripts",
        why="Management commentary as evidence for decision events.",
        without_it="Evidence comes from SEC filings only (8-K, 10-K, 10-Q).",
        requirement="Terms checked before any use (docs/12).",
        earliest_version="V3",
        status="not_selected",
    ),
)

SEC_ID = ("sec-edgar",)
RISKS = (
    Risk(
        risk_id="R-01",
        title="Unsupported region or accounting standard",
        category=RiskCategory.REGION_AND_GAAP,
        description=(
            "Foreign private issuers file 20-F or 40-F, often under IFRS, and companyfacts mixes "
            "ifrs-full and us-gaap facts."
        ),
        sources=SEC_ID,
        likelihood=Level.HIGH,
        impact=Level.MEDIUM,
        mitigation=(
            "V2 accepts domestic 10-K and 10-Q filers reporting in USD under US GAAP; others "
            "are shown as unsupported with the reason (decision D-04)."
        ),
        detection="Form types and taxonomy per company in the coverage report.",
        stage=11,
    ),
    Risk(
        risk_id="R-02",
        title="Survivorship bias",
        category=RiskCategory.SURVIVORSHIP,
        description=(
            "A universe built from today's tickers drops acquired, merged and bankrupt "
            "companies and makes history look better."
        ),
        sources=SEC_ID,
        likelihood=Level.HIGH,
        impact=Level.HIGH,
        mitigation=(
            "Build the universe from historical filers by CIK, including companies without a "
            "current ticker; the first ten include one acquired company."
        ),
        detection="Coverage report counts companies whose filings stop, by year.",
        stage=11,
    ),
    Risk(
        risk_id="R-03",
        title="Missing or changing XBRL tags",
        category=RiskCategory.MISSING_TAGS,
        description=(
            "R&D is not tagged separately by many filers, extension tags are absent from "
            "companyfacts, and concepts change, for example revenue concepts after ASC 606."
        ),
        sources=SEC_ID,
        likelihood=Level.HIGH,
        impact=Level.HIGH,
        mitigation=(
            "An ordered concept map per metric with the concept used in the lineage; a missing "
            "value stays missing, never zero."
        ),
        detection="Coverage by company, metric and quarter; concept switches flagged.",
        stage=11,
    ),
    Risk(
        risk_id="R-04",
        title="Quarterization errors",
        category=RiskCategory.QUARTERIZATION,
        description=(
            "10-Q income and cash-flow values are often year-to-date; Q4 exists only as FY "
            "minus nine months; 52/53-week years shift period ends."
        ),
        sources=SEC_ID,
        likelihood=Level.HIGH,
        impact=Level.HIGH,
        mitigation=(
            "Reconstruct quarters from start, end and duration (qtrs), derive Q4 only when "
            "definitions match, never quarterize balance sheet instants; the first ten have "
            "calendar fiscal years."
        ),
        detection="Unit tests on YTD fixtures; quarters summing to the fiscal year (DATA-03).",
        stage=11,
    ),
    Risk(
        risk_id="R-05",
        title="Restatements and amendments",
        category=RiskCategory.RESTATEMENT,
        description=(
            "The same period is reported again in 10-K/A or recast after discontinued "
            "operations; companyfacts keeps several values for one period."
        ),
        sources=SEC_ID,
        likelihood=Level.MEDIUM,
        impact=Level.HIGH,
        mitigation=(
            "Keep every value with its accession and filing date; original, vintage and latest "
            "views; point-in-time picks the latest value filed before the cutoff."
        ),
        detection="Count of periods with more than one value; differences above a threshold.",
        stage=12,
    ),
    Risk(
        risk_id="R-06",
        title="Time to publication and leakage",
        category=RiskCategory.TIME_TO_PUBLICATION,
        description=(
            "A quarter ends weeks before its filing; macro data are revised; FRED gives release "
            "dates without a time of day."
        ),
        sources=("sec-edgar", "fred-alfred", "world-bank"),
        likelihood=Level.HIGH,
        impact=Level.HIGH,
        mitigation=(
            "Knowledge time is the acceptance time of the filing; macro values count from the "
            "day after release unless the release time is documented."
        ),
        detection="A deliberately future-dated fixture must stay invisible (DATA-02).",
        stage=12,
    ),
    Risk(
        risk_id="R-07",
        title="Currency, unit and scale errors",
        category=RiskCategory.CURRENCY_AND_SCALE,
        description=(
            "Facts come in several units (USD, other currencies, shares, USD per share); a "
            "company may change reporting currency; tagging errors shift magnitudes."
        ),
        sources=SEC_ID,
        likelihood=Level.MEDIUM,
        impact=Level.HIGH,
        mitigation=(
            "Unit allowlist per metric; non-USD values are not converted in V2; jumps of an "
            "order of magnitude against neighbouring quarters are flagged."
        ),
        detection="Unit and magnitude checks in normalization (DATA-04).",
        stage=11,
    ),
    Risk(
        risk_id="R-08",
        title="Ticker and name changes",
        category=RiskCategory.IDENTIFIERS,
        description=(
            "Tickers are reused by other companies; submissions show only current tickers."
        ),
        sources=SEC_ID,
        likelihood=Level.MEDIUM,
        impact=Level.MEDIUM,
        mitigation="CIK is the key; ticker and name histories are dated (contracts 0.2.0).",
        detection="Search by a former ticker resolves to the right CIK and dates.",
        stage=11,
    ),
    Risk(
        risk_id="R-09",
        title="Segment and co-registrant values mixed with consolidated ones",
        category=RiskCategory.DATA_ERRORS,
        description="Data set rows can belong to a segment or a co-registrant.",
        sources=SEC_ID,
        likelihood=Level.MEDIUM,
        impact=Level.MEDIUM,
        mitigation="Use only rows with empty segments and co-registrant for consolidated values.",
        detection="Totals compared with companyfacts for the same accession.",
        stage=11,
    ),
    Risk(
        risk_id="R-10",
        title="Terms of use and redistribution",
        category=RiskCategory.TERMS_OF_USE,
        description=(
            "FRED third-party series need permission; ECB statistics must stay unmodified; some "
            "World Bank indicators belong to third parties; free access is not resale."
        ),
        sources=("sec-edgar", "fred-alfred", "ecb-data-portal", "world-bank"),
        likelihood=Level.MEDIUM,
        impact=Level.HIGH,
        mitigation=(
            "Licence and terms version stored with every raw file; raw bytes never committed; "
            "per-series check of FRED notes and World Bank metadata; attribution shown."
        ),
        detection="Catalog tests: every source has terms, key status and resale status.",
        stage=10,
    ),
    Risk(
        risk_id="R-11",
        title="Access blocked by the provider",
        category=RiskCategory.ACCESS,
        description=(
            "Exceeding SEC fair access or an invalid FRED key blocks requests; an IP block "
            "stops every job."
        ),
        sources=("sec-edgar", "fred-alfred"),
        likelihood=Level.LOW,
        impact=Level.HIGH,
        mitigation=(
            "Token bucket at 2 requests per second, declared User-Agent enforced by settings, "
            "bulk files for history, stop on 403."
        ),
        detection="Request log with status codes; a 403 fails the run.",
        stage=10,
    ),
    Risk(
        risk_id="R-12",
        title="Errors in the source data",
        category=RiskCategory.DATA_ERRORS,
        description=(
            "The SEC does not guarantee the accuracy of extracted data; XBRL facts can have "
            "wrong signs or scale."
        ),
        sources=SEC_ID,
        likelihood=Level.MEDIUM,
        impact=Level.MEDIUM,
        mitigation=(
            "Accounting identity checks (assets equal liabilities plus equity), sign checks, "
            "anomaly flags shown in the dossier."
        ),
        detection="Data quality flags per company and quarter.",
        stage=11,
    ),
    Risk(
        risk_id="R-13",
        title="Macro revisions used as if known",
        category=RiskCategory.REVISIONS,
        description="Using today's macro values for past dates leaks later revisions.",
        sources=("fred-alfred", "ecb-data-portal", "world-bank"),
        likelihood=Level.HIGH,
        impact=Level.HIGH,
        mitigation="ALFRED vintages, ECB includeHistory, WDI archives; as-of joins only.",
        detection="Tests compare as-of values with a known vintage.",
        stage=13,
    ),
    Risk(
        risk_id="R-14",
        title="Documentation and endpoints change",
        category=RiskCategory.ACCESS,
        description="Providers change endpoints and terms without notice.",
        sources=("sec-edgar", "fred-alfred", "ecb-data-portal", "world-bank"),
        likelihood=Level.MEDIUM,
        impact=Level.MEDIUM,
        mitigation=(
            "verified_on per source; documentation re-read before the first download of each "
            "source; contract tests on saved sample responses."
        ),
        detection="Schema validation of every raw response.",
        stage=10,
    ),
    Risk(
        risk_id="R-15",
        title="Volume and storage",
        category=RiskCategory.VOLUME,
        description=(
            "Quarterly data set files reach 122 MB and notes files 810 MB compressed; history "
            "adds up to gigabytes."
        ),
        sources=SEC_ID,
        likelihood=Level.MEDIUM,
        impact=Level.LOW,
        mitigation=(
            "Start with ten companies through the API; bulk files only after the owner agrees "
            "on a disk budget; raw files live in var/ and never in git."
        ),
        detection="Disk use reported by each run.",
        stage=10,
    ),
)

SECTORS = (
    SectorPriority(
        sector="Semiconductors",
        sic_codes=("3674",),
        priority="p1",
        rationale="R&D and capex are large and reported; manufacturing statements are standard.",
        decisions=(T.RND_CHANGE, T.CAPEX_EXPANSION, T.ACQUISITION),
    ),
    SectorPriority(
        sector="Medical instruments and devices",
        sic_codes=("3841-3845",),
        priority="p1",
        rationale="R&D-intensive with frequent acquisitions; standard industrial statements.",
        decisions=(T.RND_CHANGE, T.ACQUISITION, T.DIVESTITURE),
    ),
    SectorPriority(
        sector="Industrial instruments and electronic components",
        sic_codes=("3670-3679", "3820-3829"),
        priority="p1",
        rationale="Steady acquirers with capex and R&D; few financial-services segments.",
        decisions=(T.ACQUISITION, T.CAPEX_EXPANSION, T.RND_CHANGE),
    ),
    SectorPriority(
        sector="Railroads and trucking",
        sic_codes=("4011", "4213"),
        priority="p1",
        rationale="Capex-heavy, long stable histories, simple revenue lines.",
        decisions=(T.CAPEX_EXPANSION, T.DEBT_REFINANCE, T.WORKFORCE_RESTRUCTURE),
    ),
    SectorPriority(
        sector="Refuse and environmental services",
        sic_codes=("4953",),
        priority="p1",
        rationale="Roll-up acquisitions and capex with clear cash flows.",
        decisions=(T.ACQUISITION, T.CAPEX_EXPANSION, T.DEBT_REFINANCE),
    ),
    SectorPriority(
        sector="Software and IT services",
        sic_codes=("7370-7379", "7389"),
        priority="p2",
        rationale=(
            "R&D-heavy, but capitalised software, deferred revenue and stock compensation "
            "complicate capex and margins."
        ),
        decisions=(T.RND_CHANGE, T.ACQUISITION),
    ),
    SectorPriority(
        sector="Regulated utilities",
        sic_codes=("4911-4941",),
        priority="p2",
        rationale=(
            "Capex and refinancing are frequent, but regulated rates drive revenue and filings "
            "often combine several registrants."
        ),
        decisions=(T.CAPEX_EXPANSION, T.DEBT_REFINANCE),
    ),
    SectorPriority(
        sector="Pharmaceutical preparations with revenue",
        sic_codes=("2834",),
        priority="p2",
        rationale=(
            "Large R&D and acquisitions, but acquired in-process R&D and patent cliffs break "
            "continuity."
        ),
        decisions=(T.RND_CHANGE, T.ACQUISITION, T.DIVESTITURE),
    ),
    SectorPriority(
        sector="Oil and gas, retail with 52/53-week years, airlines",
        sic_codes=("1311", "5311-5399", "4512"),
        priority="p3",
        rationale=(
            "Commodity prices, impairments, shifting fiscal weeks or lease accounting dominate "
            "the effect of a single decision."
        ),
    ),
    SectorPriority(
        sector="Banks, insurers, REITs, asset managers, blank-check companies",
        sic_codes=("6020-6036", "6200-6282", "6311-6411", "6770", "6798"),
        priority="excluded",
        rationale=(
            "Financial statements of another kind: EBITDA, capex and free cash flow are not "
            "meaningful, and blank-check companies have no operations."
        ),
    ),
)

RUBRIC = (
    Criterion(
        criterion_id="C1",
        title="Domestic filer under US GAAP (10-K and 10-Q, no 20-F or 40-F)",
        weight=3,
        how_checked="Forms in the SEC submissions file.",
    ),
    Criterion(
        criterion_id="C2",
        title="Calendar fiscal year (ends 31 December)",
        weight=2,
        how_checked="fiscalYearEnd in the SEC submissions file.",
    ),
    Criterion(
        criterion_id="C3",
        title="Long XBRL history expected (large accelerated filer, listed before 2009)",
        weight=2,
        how_checked="Filer category verified; quarters counted in Stage 11.",
    ),
    Criterion(
        criterion_id="C4",
        title="Sector priority (P1 = 2, P2 = 1, P3 = 0)",
        weight=2,
        how_checked="SIC code in the SEC submissions file against the sector table.",
    ),
    Criterion(
        criterion_id="C5",
        title="At least two of the six decision types plausible",
        weight=2,
        how_checked="Business model; confirmed with filing evidence in the event registry.",
    ),
    Criterion(
        criterion_id="C6",
        title="Simple statements (no captive finance or insurance arm, no continuity break)",
        weight=1,
        how_checked="Read in the 10-K segment note during Stage 11.",
    ),
    Criterion(
        criterion_id="C7",
        title="Covers survivorship (company acquired or delisted)",
        weight=1,
        how_checked="No current ticker and filings that stop, in the submissions file.",
    ),
)
WEIGHTS = {criterion.criterion_id: criterion.weight for criterion in RUBRIC}


def scores(*points: tuple[int, Evidence, str]) -> tuple[Score, ...]:
    return tuple(
        Score(criterion_id=f"C{index}", points=value, evidence=evidence, basis=basis)
        for index, (value, evidence, basis) in enumerate(points, start=1)
    )


V, E = Evidence.VERIFIED, Evidence.EXPECTED
DOMESTIC = (2, V, "10-K and 10-Q filer, no 20-F.")
CALENDAR = (2, V, "Fiscal year ends 1231.")
LONG = (2, E, "Large accelerated filer; history counted in Stage 11.")
SIMPLE = (2, E, "No finance arm expected; checked in Stage 11.")
LISTED = (0, V, "Listed today.")


def candidate(
    rank: int,
    name: str,
    cik: str,
    ticker: str | None,
    sic: str,
    sic_description: str,
    sector_priority: str,
    decisions: tuple[T, ...],
    points: tuple[tuple[int, Evidence, str], ...],
    concerns: tuple[str, ...],
    status: str = "listed",
) -> CompanyCandidate:
    scored = scores(*points)
    return CompanyCandidate.model_validate(
        {
            "rank": rank,
            "name": name,
            "cik": cik,
            "ticker": ticker,
            "sic": sic,
            "sic_description": sic_description,
            "sector_priority": sector_priority,
            "fiscal_year_end": "1231",
            "filer_category": "Large accelerated filer",
            "status": status,
            "verified_on": VERIFIED_ON,
            "decisions": decisions,
            "scores": scored,
            "total": sum(WEIGHTS[score.criterion_id] * score.points for score in scored),
            "concerns": concerns,
        }
    )


CANDIDATES = (
    candidate(
        1,
        "Texas Instruments Inc.",
        "0000097476",
        "TXN",
        "3674",
        "Semiconductors & Related Devices",
        "p1",
        (T.RND_CHANGE, T.CAPEX_EXPANSION),
        (
            DOMESTIC,
            CALENDAR,
            LONG,
            (2, V, "SIC 3674, P1."),
            (2, E, "R&D and capex."),
            SIMPLE,
            LISTED,
        ),
        ("Separate R&D and capex tags are expected, not yet checked.",),
    ),
    candidate(
        2,
        "Stryker Corp.",
        "0000310764",
        "SYK",
        "3841",
        "Surgical & Medical Instruments & Apparatus",
        "p1",
        (T.RND_CHANGE, T.ACQUISITION),
        (
            DOMESTIC,
            CALENDAR,
            LONG,
            (2, V, "SIC 3841, P1."),
            (2, E, "R&D and acquisitions."),
            SIMPLE,
            LISTED,
        ),
        ("Frequent acquisitions: goodwill and acquired R&D need care.",),
    ),
    candidate(
        3,
        "AMETEK Inc.",
        "0001037868",
        "AME",
        "3823",
        "Industrial Instruments For Measurement, Display, and Control",
        "p1",
        (T.ACQUISITION, T.RND_CHANGE),
        (
            DOMESTIC,
            CALENDAR,
            LONG,
            (2, V, "SIC 3823, P1."),
            (2, E, "Acquisitions and R&D."),
            SIMPLE,
            LISTED,
        ),
        ("Many small acquisitions: the effect of one deal may be small.",),
    ),
    candidate(
        4,
        "Union Pacific Corp.",
        "0000100885",
        "UNP",
        "4011",
        "Railroads, Line-Haul Operating",
        "p1",
        (T.CAPEX_EXPANSION, T.DEBT_REFINANCE),
        (
            DOMESTIC,
            CALENDAR,
            LONG,
            (2, V, "SIC 4011, P1."),
            (2, E, "Capex and refinancing."),
            SIMPLE,
            LISTED,
        ),
        ("Little R&D; corporate events are checked in the event registry (Stage 19).",),
    ),
    candidate(
        5,
        "Waste Management Inc.",
        "0000823768",
        "WM",
        "4953",
        "Refuse Systems",
        "p1",
        (T.ACQUISITION, T.CAPEX_EXPANSION),
        (
            DOMESTIC,
            CALENDAR,
            LONG,
            (2, V, "SIC 4953, P1."),
            (2, E, "Acquisitions and capex."),
            SIMPLE,
            LISTED,
        ),
        ("Former name USA Waste Services Inc.: name history must be dated.",),
    ),
    candidate(
        6,
        "Celgene Corp.",
        "0000816284",
        None,
        "2834",
        "Pharmaceutical Preparations",
        "p2",
        (T.RND_CHANGE, T.ACQUISITION),
        (
            DOMESTIC,
            CALENDAR,
            LONG,
            (1, V, "SIC 2834, P2."),
            (2, E, "R&D and acquisitions."),
            (1, E, "Acquired in-process R&D breaks R&D continuity."),
            (2, V, "No ticker; last 10-K filed 2019-02-26."),
        ),
        ("Acquired in 2019: tests survivorship and the end of a company's history.",),
        status="acquired",
    ),
    candidate(
        7,
        "Hubbell Inc.",
        "0000048898",
        "HUBB",
        "3670",
        "Electronic Components & Accessories",
        "p1",
        (T.ACQUISITION, T.CAPEX_EXPANSION),
        (
            DOMESTIC,
            CALENDAR,
            LONG,
            (2, V, "SIC 3670, P1."),
            (1, E, "Acquisitions; R&D small."),
            SIMPLE,
            LISTED,
        ),
        ("SIC says electronic components; segments are checked in Stage 11.",),
    ),
    candidate(
        8,
        "Old Dominion Freight Line Inc.",
        "0000878927",
        "ODFL",
        "4213",
        "Trucking (No Local)",
        "p1",
        (T.CAPEX_EXPANSION,),
        (
            DOMESTIC,
            CALENDAR,
            LONG,
            (2, V, "SIC 4213, P1."),
            (1, E, "Mostly capex."),
            SIMPLE,
            LISTED,
        ),
        ("Mostly capex decisions; little debt or M&A expected.",),
    ),
    candidate(
        9,
        "American Water Works Company Inc.",
        "0001410636",
        "AWK",
        "4941",
        "Water Supply",
        "p2",
        (T.CAPEX_EXPANSION, T.DEBT_REFINANCE),
        (
            DOMESTIC,
            CALENDAR,
            LONG,
            (1, V, "SIC 4941, P2."),
            (2, E, "Capex and refinancing."),
            (1, E, "Regulated rates drive revenue."),
            LISTED,
        ),
        ("Listed since 2008: the first XBRL quarters are checked in Stage 11.",),
    ),
    candidate(
        10,
        "Akamai Technologies Inc.",
        "0001086222",
        "AKAM",
        "7389",
        "Services-Business Services, NEC",
        "p2",
        (T.RND_CHANGE, T.ACQUISITION),
        (
            DOMESTIC,
            CALENDAR,
            LONG,
            (1, V, "SIC 7389, P2."),
            (2, E, "R&D and acquisitions."),
            (1, E, "Capitalised software and convertible notes."),
            LISTED,
        ),
        ("Capitalised software counts as capex: definitions must be shown.",),
    ),
)

PLAN = (
    AcquisitionStep(
        step=1,
        title="Owner decision for SEC downloads",
        sources=SEC_ID,
        scope=(
            "Approve the sec-edgar source, set MULTIVERSE_SEC_USER_AGENT (name and contact "
            "email) in .env, agree on a disk budget for var/raw."
        ),
        volume="None.",
        storage=".env stays out of git.",
        checks=("Settings refuse downloads without a User-Agent containing '@'.",),
        owner_decision="Approve SEC downloads and give the User-Agent.",
        decided_on=date(2026, 10, 29),
        stage=10,
    ),
    AcquisitionStep(
        step=2,
        title="Submissions of the ten candidates",
        sources=SEC_ID,
        scope=(
            "10 API requests for submissions, plus the older-filing pages each one lists, at 2 "
            "requests per second."
        ),
        volume="10 JSON files and their older-filing pages.",
        storage="var/raw/sec/submissions/, immutable, with SHA-256 and headers.",
        checks=(
            "Response validated against a schema.",
            "CIK, SIC and fiscal year end match the catalog.",
        ),
        stage=10,
    ),
    AcquisitionStep(
        step=3,
        title="Company facts of the ten candidates",
        sources=SEC_ID,
        scope=(
            "10 API requests for companyfacts. The size of companyfacts.zip is read with one "
            "HEAD request to decide whether bulk is worth it later."
        ),
        volume="10 JSON files.",
        storage="var/raw/sec/companyfacts/, immutable.",
        checks=("Schema validation; SHA-256 recorded; re-run produces no duplicate file.",),
        stage=10,
    ),
    AcquisitionStep(
        step=4,
        title="Coverage report on the ten",
        sources=SEC_ID,
        scope=(
            "Normalize revenue, operating income, R&D, CFO, capex, debt and cash; quarters "
            "from year-to-date values; count valid quarters per metric."
        ),
        volume="No download.",
        storage="Normalized tables in var/data/.",
        checks=("Coverage at 8, 20 and 40 quarters; concept used per value (DATA-04, DATA-05).",),
        stage=11,
    ),
    AcquisitionStep(
        step=5,
        title="Financial Statement Data Sets for original vintages",
        sources=SEC_ID,
        scope=(
            "Quarterly files 2009 Q1 to 2026 Q3, only if step 4 shows that companyfacts "
            "lacks original values. One file per run, outside US business hours."
        ),
        volume="71 files of 13 KB to 122 MB each.",
        storage="var/raw/sec/fsds/, immutable.",
        checks=("SHA-256 per file; row counts per table; filed dates within the quarter.",),
        owner_decision="Approve the volume after step 4.",
        stage=11,
    ),
    AcquisitionStep(
        step=6,
        title="FRED key and a first set of macro series",
        sources=("fred-alfred",),
        scope=(
            "The owner registers a FRED account and key. Candidate series: FEDFUNDS, CPIAUCSL, "
            "UNRATE, GDPC1, DGS10, USREC, each with its vintages."
        ),
        volume="About 6 series with their vintage dates.",
        storage="var/raw/fred/, immutable, with requested real-time periods.",
        checks=(
            "Notes of each series checked for 'Copyright' before storing.",
            "As-of value equals the value of the matching vintage.",
        ),
        owner_decision="Register the key and approve the series list.",
        stage=13,
    ),
    AcquisitionStep(
        step=7,
        title="ECB and World Bank context series",
        sources=("ecb-data-portal", "world-bank"),
        scope=(
            "EUR/USD reference rate with history; a few WDI indicators with archive versions, "
            "only if a model needs them."
        ),
        volume="A few series.",
        storage="var/raw/ecb/ and var/raw/worldbank/.",
        checks=("Unmodified originals kept; attribution recorded.",),
        owner_decision="Approve after the macro feature plan of Stage 13.",
        stage=13,
    ),
)

SOURCE_CATALOG = SourceCatalog(
    contracts_version=CONTRACTS_VERSION,
    verified_on=VERIFIED_ON,
    automatic_downloads="disabled",
    sources=(SEC, FRED, ECB, WORLD_BANK),
    licensed_needs=LICENSED_NEEDS,
    risks=RISKS,
    sectors=SECTORS,
    rubric=RUBRIC,
    candidates=CANDIDATES,
    acquisition_plan=PLAN,
)


def render() -> str:
    return SOURCE_CATALOG.model_dump_json(indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the catalog file is stale")
    args = parser.parse_args(argv)

    expected = render()
    if args.check:
        current = CATALOG_PATH.read_text(encoding="utf-8") if CATALOG_PATH.exists() else ""
        if current != expected:
            print(f"{CATALOG_PATH.name} is stale. Run: npm run contracts:gen", file=sys.stderr)
            return 1
        print(f"{CATALOG_PATH.name} is up to date ({len(SOURCE_CATALOG.sources)} sources)")
        return 0

    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(expected, encoding="utf-8", newline="\n")
    print(f"wrote {CATALOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
