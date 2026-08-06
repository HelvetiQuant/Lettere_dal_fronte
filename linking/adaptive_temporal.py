"""V7.3-Fase8: Adaptive temporal window for person-event matching.

Computes a person-specific temporal window based on lifecycle data:
  - birth_year → earliest plausible service year (age 16)
  - death_year → hard upper bound
  - service dates → explicit service window
  - war_period → broad era constraint (WWI: 1914-1918, WWII: 1939-1945)

The window is adaptive: narrower when precise dates are available,
wider when only birth year or war period is known.

Key invariants:
  1. Events outside the temporal window are rejected (hard veto)
  2. Events within the window but outside service dates → needs_review
  3. Events within service dates → accepted (temporal-wise)
  4. Missing dates do NOT constitute a conflict (unknown = pass)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


# War period date ranges
WAR_PERIOD_RANGES = {
    "WWI": (1914, 1918),
    "WWII": (1939, 1945),
    "BOTH": (1914, 1945),
    "UNKNOWN": (None, None),  # no constraint
}

# Minimum service age (conscription age in Italy)
MIN_SERVICE_AGE = 18
# Maximum plausible service age
MAX_SERVICE_AGE = 55
# Default window expansion when only birth year is known
DEFAULT_WINDOW_EXPANSION = 5


@dataclass
class TemporalWindow:
    """Adaptive temporal window for a person."""
    earliest_year: Optional[int] = None
    latest_year: Optional[int] = None
    service_start: Optional[int] = None
    service_end: Optional[int] = None
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    war_period: str = "UNKNOWN"
    window_precision: str = "unknown"  # "exact", "approximate", "broad", "unknown"
    window_source: str = ""  # what data was used to compute the window

    @property
    def is_valid(self) -> bool:
        return self.earliest_year is not None and self.latest_year is not None

    @property
    def span_years(self) -> int:
        if not self.is_valid:
            return 0
        return self.latest_year - self.earliest_year  # type: ignore

    def contains(self, year: int) -> bool:
        """Check if a year falls within this temporal window."""
        if not self.is_valid:
            return True  # unknown window = no constraint
        return self.earliest_year <= year <= self.latest_year  # type: ignore

    def relation_to_event(
        self,
        event_start_year: Optional[int],
        event_end_year: Optional[int],
    ) -> str:
        """Determine the temporal relation between this window and an event.

        Returns:
            "within" — event falls entirely within the window
            "overlap" — event partially overlaps the window
            "outside" — event is entirely outside the window (hard veto)
            "unknown" — insufficient data to determine
        """
        if not self.is_valid:
            return "unknown"
        if event_start_year is None and event_end_year is None:
            return "unknown"

        e_start = event_start_year or event_end_year
        e_end = event_end_year or event_start_year
        if e_start is None or e_end is None:
            return "unknown"

        # Event entirely within window
        if self.earliest_year <= e_start and e_end <= self.latest_year:  # type: ignore
            # Check if within service dates (more precise)
            if self.service_start and self.service_end:
                if self.service_start <= e_start and e_end <= self.service_end:
                    return "within"
                if self.service_start <= e_end and e_start <= self.service_end:
                    return "overlap"
                return "outside"
            return "within"

        # Partial overlap
        if self.earliest_year <= e_end and e_start <= self.latest_year:  # type: ignore
            return "overlap"

        # No overlap
        return "outside"

    def to_dict(self) -> dict:
        return {
            "earliest_year": self.earliest_year,
            "latest_year": self.latest_year,
            "service_start": self.service_start,
            "service_end": self.service_end,
            "birth_year": self.birth_year,
            "death_year": self.death_year,
            "war_period": self.war_period,
            "window_precision": self.window_precision,
            "window_source": self.window_source,
            "span_years": self.span_years,
        }


def compute_temporal_window(
    birth_year: Optional[int] = None,
    death_year: Optional[int] = None,
    service_start: Optional[int] = None,
    service_end: Optional[int] = None,
    war_period: str = "UNKNOWN",
) -> TemporalWindow:
    """Compute an adaptive temporal window for a person.

    Priority (highest first):
      1. Service dates (most precise)
      2. Birth + death year (lifecycle bounds)
      3. Birth year only (estimated service window)
      4. War period only (broad era constraint)

    Args:
        birth_year: person's birth year (if known)
        death_year: person's death year (if known)
        service_start: start of military service (if known)
        service_end: end of military service (if known)
        war_period: "WWI", "WWII", "BOTH", or "UNKNOWN"

    Returns:
        TemporalWindow with computed bounds and precision
    """
    window = TemporalWindow(
        birth_year=birth_year,
        death_year=death_year,
        service_start=service_start,
        service_end=service_end,
        war_period=war_period,
    )

    # Priority 1: Service dates
    if service_start and service_end:
        window.earliest_year = service_start
        window.latest_year = service_end
        window.window_precision = "exact"
        window.window_source = "service_dates"
        return window

    # Priority 2: Birth + death year
    if birth_year and death_year:
        earliest = max(birth_year + MIN_SERVICE_AGE, _war_start(war_period, birth_year))
        latest = min(death_year, _war_end(war_period, death_year))
        # If death is before war start, use death as upper bound
        if latest < earliest:
            # Person died before plausible service — use lifecycle
            earliest = birth_year + MIN_SERVICE_AGE
            latest = death_year
        window.earliest_year = earliest
        window.latest_year = latest
        window.window_precision = "approximate"
        window.window_source = "birth_death"
        return window

    # Priority 3: Birth year only
    if birth_year:
        earliest = birth_year + MIN_SERVICE_AGE
        latest = birth_year + MAX_SERVICE_AGE
        # Narrow by war period if known
        wp_start, wp_end = WAR_PERIOD_RANGES.get(war_period, (None, None))
        if wp_start and wp_end:
            earliest = max(earliest, wp_start)
            latest = min(latest, wp_end)
        window.earliest_year = earliest
        window.latest_year = latest
        window.window_precision = "broad"
        window.window_source = "birth_year_only"
        return window

    # Priority 4: War period only
    wp_start, wp_end = WAR_PERIOD_RANGES.get(war_period, (None, None))
    if wp_start and wp_end:
        window.earliest_year = wp_start
        window.latest_year = wp_end
        window.window_precision = "broad"
        window.window_source = "war_period"
        return window

    # No data
    window.window_precision = "unknown"
    window.window_source = "none"
    return window


def _war_start(war_period: str, fallback_year: int) -> int:
    """Get war start year for the given period."""
    wp_start, _ = WAR_PERIOD_RANGES.get(war_period, (None, None))
    if wp_start is not None:
        return wp_start
    return fallback_year


def _war_end(war_period: str, fallback_year: int) -> int:
    """Get war end year for the given period."""
    _, wp_end = WAR_PERIOD_RANGES.get(war_period, (None, None))
    if wp_end is not None:
        return wp_end
    return fallback_year


def evaluate_event_temporal_compatibility(
    window: TemporalWindow,
    event_start_year: Optional[int],
    event_end_year: Optional[int],
) -> Tuple[str, str]:
    """Evaluate whether an event is temporally compatible with a person's window.

    Returns:
        (decision, reason)
        decision: "accepted" | "needs_review" | "rejected" | "unknown"
        reason: human-readable explanation
    """
    if not window.is_valid:
        return "unknown", "no_temporal_window"

    relation = window.relation_to_event(event_start_year, event_end_year)

    if relation == "within":
        if window.window_precision in ("exact", "approximate"):
            return "accepted", f"event_within_{window.window_precision}_window"
        return "accepted", "event_within_broad_window"

    if relation == "overlap":
        return "needs_review", "event_partial_overlap_with_window"

    if relation == "outside":
        return "rejected", f"event_outside_temporal_window:{window.earliest_year}-{window.latest_year}"

    return "unknown", "insufficient_temporal_data"
