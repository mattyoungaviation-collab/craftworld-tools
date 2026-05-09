"""Template helper registration for Craft World Tools."""

from __future__ import annotations

from typing import Any


def compact_number(value: Any, digits: int = 2) -> str:
    """Format large numbers compactly for templates."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "0"

    sign = "-" if num < 0 else ""
    num = abs(num)
    units = [(1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")]
    for threshold, suffix in units:
        if num >= threshold:
            return f"{sign}{num / threshold:.{digits}f}{suffix}"
    return f"{sign}{num:.{digits}f}".rstrip("0").rstrip(".")


def coin_number(value: Any, digits: int = 4) -> str:
    """Format COIN values for templates."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = 0.0
    return f"{num:,.{digits}f}".rstrip("0").rstrip(".")


def percent_number(value: Any, digits: int = 2) -> str:
    """Format a percentage for templates."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = 0.0
    return f"{num:.{digits}f}%"


def register_template_filters(app: Any) -> None:
    """Register common Jinja filters."""
    app.jinja_env.filters["compact_number"] = compact_number
    app.jinja_env.filters["coin_number"] = coin_number
    app.jinja_env.filters["percent_number"] = percent_number
