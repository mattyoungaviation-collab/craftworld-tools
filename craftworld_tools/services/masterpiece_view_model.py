"""View helpers for rich Masterpiece detail data."""

from __future__ import annotations

from typing import Any


def fmt_number(value: Any, decimals: int = 0) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = 0.0
    if decimals <= 0:
        return f"{num:,.0f}"
    return f"{num:,.{decimals}f}"


def build_masterpiece_summary(detail: dict[str, Any] | None) -> dict[str, Any]:
    """Build a compact display model from a rich Masterpiece detail payload."""
    raw = detail or {}
    normalized = raw.get("normalized") or raw

    user_profile = normalized.get("profileByUserId") or {}
    user_profile_inner = user_profile.get("profile") or {}

    resources = normalized.get("resources") or []
    resources_by_user = normalized.get("resourcesByUserId") or []
    daily_power = normalized.get("dailyPowerContributionsByUserId") or []
    leaderboard = normalized.get("leaderboard") or []

    top_resources = sorted(
        resources,
        key=lambda row: float(row.get("completionPercentage") or 0),
        reverse=True,
    )

    lowest_resources = sorted(
        resources,
        key=lambda row: float(row.get("completionPercentage") or 0),
    )

    return {
        "id": normalized.get("id"),
        "name": normalized.get("name") or raw.get("name") or "Masterpiece",
        "type": normalized.get("type"),
        "addressableLabel": normalized.get("addressableLabel"),
        "collectedPoints": normalized.get("collectedPoints") or 0,
        "requiredPoints": normalized.get("requiredPoints") or 0,
        "completionPercentage": normalized.get("completionPercentage") or 0,
        "startedAt": normalized.get("startedAt"),
        "endsAt": normalized.get("endsAt"),
        "userPosition": user_profile.get("position"),
        "userPoints": user_profile.get("masterpiecePoints") or 0,
        "userDisplayName": user_profile_inner.get("displayName"),
        "resources": resources,
        "topResources": top_resources[:5],
        "lowestResources": lowest_resources[:5],
        "resourcesByUserId": resources_by_user,
        "dailyPowerContributionsByUserId": daily_power,
        "leaderboard": leaderboard[:25],
        "milestones": normalized.get("milestones") or [],
    }


def build_masterpiece_summary_html(detail: dict[str, Any] | None) -> str:
    """Return a self contained HTML panel for rich Masterpiece detail data."""
    vm = build_masterpiece_summary(detail)
    if not vm.get("id") and not vm.get("name"):
        return ""

    user_rank = vm.get("userPosition") or "—"
    user_points = fmt_number(vm.get("userPoints"))
    completion = fmt_number(vm.get("completionPercentage"), 2)
    collected = fmt_number(vm.get("collectedPoints"))
    required = fmt_number(vm.get("requiredPoints"))

    def resource_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<tr><td colspan="6" class="subtle">No resource data.</td></tr>'
        out = []
        for row in rows:
            symbol = row.get("symbol") or "?"
            amount = fmt_number(row.get("amount"))
            target = fmt_number(row.get("target"))
            remaining = fmt_number(row.get("remaining"))
            pct = fmt_number(row.get("completionPercentage"), 2)
            power = fmt_number(row.get("consumedPowerPerUnit"))
            power_costs = row.get("powerCosts") or []
            tiers = ", ".join(
                f"{fmt_number(pc.get('amount'))} @ {fmt_number(pc.get('powerCostPerUnit'))}"
                for pc in power_costs[:5]
            )
            out.append(
                "<tr>"
                f"<td>{symbol}</td>"
                f"<td>{amount}</td>"
                f"<td>{target}</td>"
                f"<td>{remaining}</td>"
                f"<td>{pct}%</td>"
                f"<td>{power}</td>"
                f"<td>{tiers}</td>"
                "</tr>"
            )
        return "".join(out)

    def simple_rows(rows: list[dict[str, Any]], value_key: str = "amount") -> str:
        if not rows:
            return '<tr><td colspan="2" class="subtle">Nothing recorded yet.</td></tr>'
        return "".join(
            f"<tr><td>{row.get('symbol') or '?'}</td><td>{fmt_number(row.get(value_key))}</td></tr>"
            for row in rows
        )

    def leaderboard_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return '<tr><td colspan="3" class="subtle">No leaderboard data.</td></tr>'
        out = []
        for row in rows[:10]:
            out.append(
                "<tr>"
                f"<td>#{row.get('position') or '—'}</td>"
                f"<td>{row.get('displayName') or 'Unknown'}</td>"
                f"<td>{fmt_number(row.get('masterpiecePoints'))}</td>"
                "</tr>"
            )
        return "".join(out)

    return f"""
    <div class="card" id="rich-masterpiece-summary">
      <h2>Masterpiece Live Summary</h2>
      <p class="subtle">
        {vm.get('name')} · {completion}% complete · {collected} / {required} points
      </p>
      <div class="two-col">
        <div>
          <h3>Your Position</h3>
          <p><strong>Rank:</strong> {user_rank}<br><strong>Points:</strong> {user_points}</p>
          <h3>Your Resources</h3>
          <table><tr><th>Resource</th><th>Amount</th></tr>{simple_rows(vm.get('resourcesByUserId') or [])}</table>
          <h3>Daily Power Contributions</h3>
          <table><tr><th>Resource</th><th>Amount</th></tr>{simple_rows(vm.get('dailyPowerContributionsByUserId') or [])}</table>
        </div>
        <div>
          <h3>Top Leaderboard</h3>
          <table><tr><th>Rank</th><th>Player</th><th>Points</th></tr>{leaderboard_rows(vm.get('leaderboard') or [])}</table>
        </div>
      </div>
      <h3>Resource Progress and Power Tiers</h3>
      <table>
        <tr>
          <th>Resource</th><th>Amount</th><th>Target</th><th>Remaining</th><th>Done</th><th>Base Power</th><th>Power Tiers</th>
        </tr>
        {resource_rows(vm.get('resources') or [])}
      </table>
    </div>
    """
