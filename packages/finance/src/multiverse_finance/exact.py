"""Exact arithmetic and the two kinds of bad number (docs/07, numerical invariants).

A bad input raises: NaN, infinity, a float, a share outside 0 to 1, WACC at or below growth.
A sound input with no meaningful answer does not raise: Net debt / EBITDA at EBITDA <= 0 is
undefined and says why, because a path of a simulation may well land there.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from functools import wraps

ZERO = Decimal(0)
ONE = Decimal(1)
QUARTERS_PER_YEAR = 4
EPSILON = Decimal("1e-20")
"""Below this an amount is a rounding remainder of exact shares, never a real balance."""

CONTEXT = Context(
    prec=40, rounding=ROUND_HALF_EVEN, traps=[InvalidOperation, DivisionByZero, Overflow]
)


class FinanceError(ValueError):
    """An impossible setting, with a stable code and the path of the offending value."""

    def __init__(self, code: str, path: str, message: str) -> None:
        super().__init__(f"[{code}] {path}: {message}")
        self.code = code
        self.path = path


def exact[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    """Run under the context of this package, whatever context the caller has set."""

    @wraps(function)
    def run(*args: P.args, **kwargs: P.kwargs) -> R:
        with localcontext(CONTEXT):
            return function(*args, **kwargs)

    return run


def finite(value: object, path: str) -> Decimal:
    """The value itself, if it is a finite Decimal. A float is refused: it is not exact."""
    if not isinstance(value, Decimal):
        raise FinanceError("not_decimal", path, f"expected a Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise FinanceError("not_finite", path, f"{value} is not a finite number")
    return value


def at_least(value: object, low: Decimal, path: str) -> Decimal:
    number = finite(value, path)
    if number < low:
        raise FinanceError("out_of_range", path, f"{number} is below {low}")
    return number


def between(value: object, low: Decimal, high: Decimal, path: str) -> Decimal:
    number = at_least(value, low, path)
    if number > high:
        raise FinanceError("out_of_range", path, f"{number} is above {high}")
    return number


def share(value: object, path: str) -> Decimal:
    """A fraction from 0 to 1."""
    return between(value, ZERO, ONE, path)


def whole(value: int, low: int, path: str) -> int:
    if value < low:
        raise FinanceError("out_of_range", path, f"{value} is below {low}")
    return value


@dataclass(frozen=True, slots=True)
class Ratio:
    """A ratio, or the reason it has no meaning."""

    value: Decimal | None
    reason: str | None = None


def ratio(numerator: Decimal, denominator: Decimal, reason: str) -> Ratio:
    """Numerator / denominator, undefined at a zero or negative denominator."""
    if denominator <= ZERO:
        return Ratio(None, reason)
    return Ratio(numerator / denominator)
