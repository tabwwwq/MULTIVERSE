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
"""

CONTRACTS_VERSION = "0.5.0"
