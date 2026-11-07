# Source card

The official sources MULTIVERSE reads, what it takes from each, and on what terms. Full terms and their review: [licence inventory](../security/license-inventory.md); the same sources on screen: the Data Catalog (`/data-catalog`).

| Source | What is used | Where it goes | Terms | Status |
|---|---|---|---|---|
| SEC EDGAR | Company facts (XBRL) and submissions, bulk ZIP files and company files; 60 filings read by hand for the event registry (Stage 19) | Raw archive in `var/raw`, warehouse, datasets, dossiers of `data/companies`, research reports with links to filings | Public information; cite the SEC, at most 10 requests a second, a User-Agent with a contact; no SEC logos | In use |
| U.S. Treasury | Daily par yield curve, yearly files 2009–2026 | Features of the model without FRED, rates of the cases of real companies | Work of the U.S. Government, not under copyright; no endorsement implied | In use (decision D-14) |
| ECB Data Portal | Deposit facility rate, EUR/USD, euro area 10-year yield | Features of the model without FRED | Free reuse with "Source: ECB statistics" and unchanged statistics | In use; cited on the forecast panel and in reports |
| World Bank | GDP growth of the United States; inflation and unemployment are downloaded but empty in the model | GDP column of the shocks of a case; empty in the features of the model (no dated vintages) | CC BY 4.0 for these indicators; attribution | In use; cited in the run dialog and in reports |
| FRED and ALFRED | Seven series with vintages, Stages 13–17 | The first model and the Stage 22 case of Hubbell | Terms forbid machine learning on FRED content and archiving it through the API | Blocked: no new training, no new downloads; owner chose on 2026-11-07 to keep what exists for now (LIC-001–003) |

Not used: market prices (need a licence, decision D-06), earnings call transcripts, any source behind a login.
