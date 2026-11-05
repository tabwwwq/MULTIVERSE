"""The event registry: text, sampling, gated downloads, reviews, audit. Invented documents, plus
the real registry, which must stay valid and traceable to its sample."""

import json
import random
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from multiverse_contracts.events import (
    CandidateSample,
    CompletionStatus,
    CorporateEvent,
    EventCandidate,
    EventEvidence,
    EventMagnitude,
    EventRegistry,
    EventReview,
    EventType,
    EventUnit,
    RejectedCandidate,
)
from multiverse_contracts.source_catalog import SOURCE_CATALOG
from multiverse_pipelines.events.audit import (
    MIN_EVENTS_PER_TYPE,
    anchor,
    audit,
    index_overlap,
    markdown,
    overlaps,
    window,
)
from multiverse_pipelines.events.candidates import (
    Filing,
    document_url,
    draw,
    jumps,
    rows_of,
)
from multiverse_pipelines.events.fetch import DOCUMENTS, MAX_DOCUMENTS, fetch_documents, key_of
from multiverse_pipelines.events.reviews import merge_reviews
from multiverse_pipelines.events.text import around, item_section, to_text
from multiverse_pipelines.sec.archive import RawArchive
from multiverse_pipelines.sec.client import SecClient
from multiverse_pipelines.sec.models import Outcome

ROOT = Path(__file__).parents[2]
SHA = "ab" * 32
URL = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/doc.htm"
MOMENT = datetime(2024, 3, 1, 21, tzinfo=UTC)


def candidate(
    number: int = 1, deregistered: bool = False, cik: str | None = None
) -> EventCandidate:
    return EventCandidate(
        candidate_id=f"item_2_05-{number}",
        cik=cik or f"{number:010d}",
        company=f"Company {number}",
        division="D",
        deregistered=deregistered,
        event_type=EventType.LAYOFF,
        stratum="item_2_05",
        accession=f"0000000001-26-{number:06d}",
        form="8-K",
        items=("2.05",),
        filed_at=MOMENT,
        url=URL.replace("doc", f"doc{number}"),
    )


def evidence(when: datetime = MOMENT, accession: str = "0000000001-26-000001") -> EventEvidence:
    return EventEvidence(
        role="announcement",
        url=URL,
        accession=accession,
        form="8-K",
        filed_at=when,
        item="2.05",
        locator="Item 2.05, paragraph 1",
        summary="A plan to cut staff.",
        document_sha256=SHA,
    )


def review(
    reviewer: str = "claude_ai", kind: str = "ai", decision: str = "confirmed"
) -> EventReview:
    return EventReview.model_validate(
        {
            "reviewer": reviewer,
            "kind": kind,
            "decision": decision,
            "confidence": "high",
            "reviewed_at": "2026-11-06T12:00:00+00:00",
        },
        strict=False,
    )


def event(
    cik: str = "0000000001",
    kind: EventType = EventType.LAYOFF,
    when: datetime = MOMENT,
    **changes: Any,
) -> CorporateEvent:
    values: dict[str, Any] = {
        "event_id": f"evt-{cik}-{kind.value}-{when:%Y%m%d}",
        "cik": cik,
        "company": "Company",
        "division": "D",
        "deregistered": False,
        "event_type": kind,
        "intention": "Cut 100 positions.",
        "magnitude": EventMagnitude(value=100, unit=EventUnit.HEADCOUNT, measures="Positions"),
        "completion": CompletionStatus.ANNOUNCED,
        "stratum": "item_2_05",
        "evidence": (evidence(when),),
        "reviews": (review(),),
    } | changes
    return CorporateEvent(**values)


def sample(candidates: tuple[EventCandidate, ...] = ()) -> CandidateSample:
    return CandidateSample(
        sample_id=f"evs-20261106-{SHA[:12]}",
        sha256=SHA,
        universe_id="invented",
        seed=1,
        population={"item_2_05": 1},
        drawn={"item_2_05": 1},
        candidates=candidates,
        contracts_version="0.17.0",
        created_at=MOMENT,
    )


def registry(*events: CorporateEvent) -> EventRegistry:
    return EventRegistry(
        registry_version="0.1.0",
        sample_id=f"evs-20261106-{SHA[:12]}",
        guidelines="guidelines.md",
        events=events,
        rejected=(
            RejectedCandidate(
                candidate_id="x", reason="Not an event.", reviewer="claude_ai", kind="ai"
            ),
        ),
    )


def test_text_drops_markup_and_keeps_paragraphs() -> None:
    markup = "<html><head><title>t</title></head><body><p>Item&nbsp;2.05</p><p>A  plan</p></body>"
    assert to_text(markup) == "Item 2.05\nA plan"


def test_the_section_of_an_item_is_the_long_one_not_a_mention() -> None:
    text = (
        "See Item 2.05 above.\nItem 2.05 Costs\nThe company will close a plant and pay severance.\n"
        "Item 9.01 Exhibits\nThe information in Item 2.05 is furnished."
    )
    assert (
        item_section(text, "2.05")
        == "Item 2.05 Costs\nThe company will close a plant and pay severance."
    )
    assert item_section(text, "2.01") is None


def test_passages_stand_around_the_words() -> None:
    text = "x" * 500 + " capital expenditures rose " + "y" * 500
    passages = around(text, ("capital expenditures",), width=60)
    assert len(passages) == 1
    assert "capital expenditures rose" in passages[0]


def test_filing_rows_keep_8_k_and_10_k_with_their_items() -> None:
    table = {
        "form": ["8-K", "4", "10-K"],
        "items": ["2.05,9.01", "", ""],
        "filingDate": ["2024-03-01", "2024-03-02", "2024-03-03"],
        "acceptanceDateTime": ["2024-03-01T16:00:00.000Z"] * 3,
        "accessionNumber": ["0000000001-24-000001", "b", "0000000001-24-000003"],
        "primaryDocument": ["a.htm", "b.xml", "c.htm"],
    }
    rows = rows_of(table, "0000000001")
    assert [r.form for r in rows] == ["8-K", "10-K"]
    assert rows[0].items == ("2.05", "9.01")
    assert document_url("0000000001", "0000000001-24-000001", "a.htm") == (
        "https://www.sec.gov/Archives/edgar/data/1/000000000124000001/a.htm"
    )


def test_a_stratum_takes_a_third_from_firms_that_left_and_one_filing_per_firm() -> None:
    pool = [candidate(i, deregistered=i <= 10) for i in range(1, 41)]
    pool += [candidate(41, cik="0000000040")]  # a second filing of firm 40
    chosen = draw(pool, 12, random.Random(1))
    assert len(chosen) == 12
    assert sum(c.deregistered for c in chosen) == 4
    assert len({c.cik for c in chosen}) == 12
    assert [c.candidate_id for c in draw(pool, 12, random.Random(1))] == [
        c.candidate_id for c in chosen
    ]


def test_a_jump_needs_size_and_ratio_on_firms_with_real_revenue(tmp_path: Path) -> None:
    rows = [
        ("0000000001", "2020-12-31", "0.10", "5e7"),
        ("0000000001", "2021-12-31", "0.20", "5e7"),  # a jump
        ("0000000002", "2020-12-31", "0.10", "5e7"),
        ("0000000002", "2021-12-31", "0.12", "5e7"),  # too small
        ("0000000003", "2020-12-31", "0.10", "1e5"),
        ("0000000003", "2021-12-31", "0.30", "1e5"),  # no real revenue
    ]
    path = tmp_path / "dataset.csv"
    path.write_text(
        "cik,origin,rnd,rev_ttm\n" + "\n".join(",".join(r) for r in rows) + "\n", encoding="utf-8"
    )
    assert jumps(path, "rnd") == [("0000000001", date(2021, 12, 31))]


@pytest.fixture
def archive(tmp_path: Path) -> RawArchive:
    return RawArchive(tmp_path, budget_bytes=10_000_000)


def client_for(archive: RawArchive, handler: Any) -> SecClient:
    source = next(s for s in SOURCE_CATALOG.sources if s.source_id == "sec-edgar")
    return SecClient(
        user_agent="MULTIVERSE research test@example.com",
        allowed_hosts=source.official_hosts,
        rate_per_second=Decimal(source.rate_limit.chosen_requests_per_second),
        tmp_dir=archive.tmp_dir,
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )


def test_documents_go_into_the_archive_once(archive: RawArchive) -> None:
    source = next(s for s in SOURCE_CATALOG.sources if s.source_id == "sec-edgar")
    calls: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "doc2" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, stream=httpx.ByteStream(b"<html>Item 2.05</html>"))

    drawn = sample((candidate(1), candidate(2)))
    with client_for(archive, answer) as client:
        first = fetch_documents(client, archive, source, drawn, "0.17.0", "run-1", lambda _: None)
        second = fetch_documents(client, archive, source, drawn, "0.17.0", "run-2", lambda _: None)
    outcomes = [r.outcome for r in first.records]
    assert outcomes == [Outcome.NEW, Outcome.FAILED]
    assert second.records[0].outcome is Outcome.FRESH_IN_ARCHIVE
    assert second.records[0].requests == 0
    stored = archive.latest(DOCUMENTS, key_of(candidate(1)))
    assert stored is not None
    assert stored.file_format == "html"
    assert first.mode == "documents"
    assert sum("doc1" in c for c in calls) == 1


def test_decision_d_13_caps_the_number_of_documents(archive: RawArchive) -> None:
    source = next(s for s in SOURCE_CATALOG.sources if s.source_id == "sec-edgar")
    many = tuple(candidate(i) for i in range(1, MAX_DOCUMENTS + 2))
    with (
        client_for(archive, lambda _: httpx.Response(200)) as client,
        pytest.raises(ValueError, match="D-13"),
    ):
        fetch_documents(client, archive, source, sample(many), "0.17.0", "run", lambda _: None)


def test_a_window_starts_at_the_first_public_document() -> None:
    later = datetime(2024, 6, 1, tzinfo=UTC)
    item = event(evidence=(evidence(later), evidence(MOMENT, "0000000001-26-000002")))
    assert anchor(item) == MOMENT
    start, end = window(item, days=10)
    assert (end - start).days == 20
    assert start < MOMENT < end


def test_overlap_is_within_a_firm_and_a_window() -> None:
    near = datetime(2024, 9, 1, tzinfo=UTC)
    far = datetime(2026, 9, 1, tzinfo=UTC)
    events = (
        event(),
        event(kind=EventType.ACQUISITION, when=near),
        event(kind=EventType.REFINANCING, when=far),
        event(cik="0000000002", kind=EventType.DIVESTITURE),
    )
    cells = overlaps(events, 365)
    assert [(c.first, c.second, c.pairs) for c in cells] == [
        (EventType.ACQUISITION, EventType.LAYOFF, 1)
    ]


def test_the_index_shows_what_the_small_sample_cannot() -> None:
    filing = Filing(
        "0000000001",
        "8-K",
        date(2024, 5, 1),
        "2024-05-01T16:00:00.000Z",
        "0000000001-24-000009",
        "x.htm",
        ("2.03", "9.01"),
    )
    rows = index_overlap((event(),), {"0000000001": [filing]}, 365)
    assert [(r.key, r.count) for r in rows] == [("layoff near item 2.03", 1)]


def test_the_audit_blocks_causal_work_without_enough_reviewed_events() -> None:
    report = audit(registry(event()), sample())
    assert not report.credible_for_causal_work
    assert report.candidates_read == 2
    assert report.human_reviewed == 0
    assert report.reviewer_agreement is None
    assert any("human review" in b for b in report.blockers)
    assert any("two reviewers" in b for b in report.blockers)
    assert any(f"at least {MIN_EVENTS_PER_TYPE}" in b for b in report.blockers)
    assert "causal work blocked" in markdown(report)


def test_the_audit_refuses_a_registry_of_another_sample() -> None:
    other = registry(event()).model_copy(update={"sample_id": "evs-20261106-000000000000"})
    with pytest.raises(ValueError, match="another sample"):
        audit(other, sample())


def test_the_audit_opens_only_with_enough_agreed_double_reviews() -> None:
    events = []
    for kind in EventType:
        for number in range(MIN_EVENTS_PER_TYPE):
            events.append(
                event(
                    cik=f"{number + 1:010d}",
                    kind=kind,
                    reviews=(review(), review("owner", "human")),
                )
            )
    report = audit(registry(*events), sample())
    assert report.credible_for_causal_work
    assert report.reviewer_agreement == 1


def test_reviews_from_the_screen_are_human_and_never_repeated() -> None:
    base = registry(event())
    row = {
        "event_id": base.events[0].event_id,
        "reviewer": "owner",
        "decision": "corrected",
        "confidence": "medium",
        "notes": None,
        "reviewed_at": "2026-11-06T12:00:00Z",
    }
    merged = merge_reviews(base, [row])
    assert merged.events[0].reviews[-1].kind == "human"
    report = audit(merged, sample())
    assert report.double_reviewed == 1
    assert report.reviewer_agreement == 0
    with pytest.raises(ValueError, match="already reviewed"):
        merge_reviews(merged, [row])
    with pytest.raises(ValueError, match="no event"):
        merge_reviews(base, [row | {"event_id": "evt-none"}])


def test_the_real_registry_is_valid_and_every_candidate_was_read() -> None:
    drawn = CandidateSample.model_validate_json((ROOT / "data/events/sample.json").read_bytes())
    real = EventRegistry.model_validate_json((ROOT / "data/events/registry.json").read_bytes())
    assert real.sample_id == drawn.sample_id
    by_accession = {c.accession: c for c in drawn.candidates}
    read = {by_accession[e.evidence[0].accession].candidate_id for e in real.events}
    read |= {r.candidate_id for r in real.rejected}
    assert read == {c.candidate_id for c in drawn.candidates}
    for item in real.events:
        assert any(r.kind == "ai" for r in item.reviews)
        source = by_accession[item.evidence[0].accession]
        assert item.evidence[0].url == source.url
        assert item.evidence[0].filed_at == source.filed_at
    assert (ROOT / "docs/product/event-annotation-guidelines.md").exists()
    assert json.loads((ROOT / "data/events/sample.json").read_text(encoding="utf-8"))["seed"]
