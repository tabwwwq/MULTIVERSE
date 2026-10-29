# SEC fixtures: synthetic

These files are **synthetic**. They copy the shape of SEC responses (Submissions API, older-filing page, Company Facts API) so the connectors can be tested without the network. The company "SYNTHETIC FIXTURE CORP", its CIK 0000000001, the accession numbers and all values are made up. They describe no real registrant.

Real SEC files are downloaded only by `python -m multiverse_pipelines.sec sample` after the owner's decision. They are kept in `var/raw/` and never committed.
