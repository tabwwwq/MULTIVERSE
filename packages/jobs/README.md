# multiverse-jobs

Durable state of long training jobs (Stage 18, ADR-0026): a SQLite queue with leases, heartbeats, idempotent submit, approval, stop and pause requests, logs without secrets, budgets and resource estimates. It trains nothing, so the API can read it without ever importing a model.
