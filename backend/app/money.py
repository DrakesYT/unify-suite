"""Money is stored as an integer count of the currency's minor unit (cents for USD)."""

from decimal import Decimal

# ISO 4217 currencies without a minor unit. Everything else uses 2 decimals.
_ZERO_DECIMAL = frozenset({"CLP", "ISK", "JPY", "KRW", "PYG", "UGX", "VND", "XAF", "XOF"})


def minor_unit_exponent(currency: str) -> int:
    return 0 if currency in _ZERO_DECIMAL else 2


def to_minor(amount: Decimal, currency: str) -> int:
    """Decimal amount → minor units. Refuses amounts with more decimals than the currency has."""
    exponent = minor_unit_exponent(currency)
    scaled = amount.scaleb(exponent)
    if scaled != scaled.to_integral_value():
        raise ValueError(f"{currency} amounts have at most {exponent} decimals")
    return int(scaled)
