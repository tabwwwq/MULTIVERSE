"""XBRL normalization (Stage 11, ADR-0018): canonical financial values from SEC facts.

Silver layer of docs/04: one row per company, metric, fiscal period and revision, with
source facts, method, knowledge date and quality flags. No value is invented: missing
stays missing with a reason, and nothing here knows about point-in-time cutoffs yet
(Stage 12 picks the revision known at a date).
"""
