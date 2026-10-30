"""Version of the contracts themselves (ADR-0011).

Bump MINOR when adding optional fields or new models, MAJOR when removing or
changing the meaning of a field. Every reproducibility manifest records it.

0.2.0 (Stage 04): company identity, listing history, filings, coverage, quality
flags, the company dossier and value lineage.

0.3.0 (Stage 05): scenario draft with six decision types, distributions,
sensitivity settings, and the intervention catalog.

0.4.0 (Stage 06): scenario result with history, quantile paths, paired changes,
change distributions, waterfalls, events and a failed state.

0.5.0 (Stage 07): saved scenarios with immutable revisions, report snapshots
and the notebook export file.

0.6.0 (Stage 09): source catalog with licences, rate limits, data dictionaries,
risk register, company candidates and the acquisition plan (metadata only).

0.7.0 (Stage 10): the scope of an owner's download approval (sample or bulk)
and the date an acquisition step's owner decision was taken.

0.8.0 (Stage 11): normalized values from SEC XBRL facts with source facts,
method, revision, knowledge date and quality flags; Q4 as fiscal year minus
three reported quarters.

0.9.0 (Stage 12): point-in-time values with intervals of knowledge time, the
as-of quarterly panel with feature masks, chronology alerts, snapshot manifests
and effective-dated company attributes; the quality flag mixed_vintage.

0.10.0 (Stage 13): macro series metadata, observations with the moment they
became available and how that is known, and macro cells joined with company
quarters with their input observations.

0.11.0 (Stage 14): Gate B checks with measures and findings, trainable example
counts, company decisions and the audited dataset manifest with its verdict.

0.12.0 (data acquisition, decision D-10): the universe manifest: the bulk files a
universe was drawn from, its eligibility rules and counts, strata and companies.
"""

CONTRACTS_VERSION = "0.12.0"
