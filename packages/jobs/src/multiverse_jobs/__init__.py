"""Durable state of long jobs of MULTIVERSE.

Responsibility: the queue of training jobs (Stage 18): who asked for what, what it may
cost, who works on it and how it stands. The worker changes this state, the API reads it
and passes on requests; neither imports the other, and nothing here trains (ADR-0026).
"""

__version__ = "0.1.0"
