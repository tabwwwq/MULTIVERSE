"""Uncertain parameters of a decision: a fixed value or a range with a shape (docs/08).

Values are decimal strings in the unit of the parameter they describe. Ordering rules
(low <= mode <= high) live in the decision validators, which know the parameter path.
"""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from multiverse_contracts.primitives import ContractModel, DecimalString


class FixedValue(ContractModel):
    """No uncertainty: the parameter takes exactly this value."""

    shape: Literal["fixed"]
    value: DecimalString


class UniformRange(ContractModel):
    """Every value between ``low`` and ``high`` is equally likely."""

    shape: Literal["uniform"]
    low: DecimalString
    high: DecimalString


class TriangularRange(ContractModel):
    """Values between ``low`` and ``high``, most likely around ``mode``."""

    shape: Literal["triangular"]
    low: DecimalString
    mode: DecimalString
    high: DecimalString


Distribution = Annotated[FixedValue | UniformRange | TriangularRange, Field(discriminator="shape")]


def distribution_points(distribution: FixedValue | UniformRange | TriangularRange) -> list[str]:
    """The values a distribution is defined by, in order."""
    if isinstance(distribution, FixedValue):
        return [distribution.value]
    if isinstance(distribution, UniformRange):
        return [distribution.low, distribution.high]
    return [distribution.low, distribution.mode, distribution.high]


def central_value(distribution: FixedValue | UniformRange | TriangularRange) -> Decimal:
    """Value used for a single-number summary: fixed value, midpoint or mode."""
    if isinstance(distribution, FixedValue):
        return Decimal(distribution.value)
    if isinstance(distribution, UniformRange):
        return (Decimal(distribution.low) + Decimal(distribution.high)) / 2
    return Decimal(distribution.mode)
