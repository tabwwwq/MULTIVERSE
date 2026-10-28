"""HTTP API of MULTIVERSE.

Responsibility: validate requests against contracts, manage scenarios and job records,
serve results and reports (docs/03, docs/09). The composition root is
multiverse_api.main.create_app. Training and heavy computation never run inside an
HTTP request (ADR-0003): the API only creates jobs for the worker."""

__version__ = "0.1.0"
