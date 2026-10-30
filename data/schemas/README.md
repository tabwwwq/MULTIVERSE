# data/schemas

Definitions of normalized financial data. The schemas themselves are generated from the Python contracts into `packages/contracts/schemas/contracts.schema.json` (ADR-0008):

- `NormalizedValue` (Stage 11, ADR-0018): canonical XBRL values with lineage and revisions;
- `PitValue`, `PanelCell`, `PitSnapshotManifest`, `ChronologyAlert` (Stage 12, ADR-0019): point-in-time values, the as-of panel with feature masks and its snapshots;
- `MacroSeries`, `MacroObservation`, `MacroCell` (Stage 13, ADR-0020): macro series metadata, values with the moment they became available, and macro cells joined with company quarters.

Only schemas and tiny synthetic fixtures live in git; downloaded data and everything built from it goes to `var/`, which is ignored (docs/04).
