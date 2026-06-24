"""Design skill requirement decay for sub-component unlocks.

GearCity reduces the skill gate on sub-components over time after their unlock year.
Per developer clarification (Steam forums):

- Requirements drop by 0.18 each quarter.
- Decay does not begin until the calendar year after the unlock year
  (e.g. unlock year 1900 keeps the full requirement through 1900; first -0.18
  applies in Q1 of 1901).

See also:
https://wiki.gearcity.info/doku.php?id=gamemanual:howto_designskills#Unlocking%20New%20Sub-Components
"""

from __future__ import annotations

SKILL_DECAY_PER_QUARTER = 0.18
QUARTERS_PER_YEAR = 4


def format_year_quarter(year: int, quarter: int = QUARTERS_PER_YEAR) -> str:
    """Return a short label such as ``1901 Q1``."""
    return f"{year} Q{quarter}"


def decay_quarters_elapsed(
    unlock_year: int | None,
    year: int,
    *,
    quarter: int = QUARTERS_PER_YEAR,
) -> int:
    """
    Return how many decay quarters have elapsed for a sub-component.

    ``quarter`` is 1-4 (Q1 through Q4) within ``year``. When only a year is
    known, default to 4 (end of year) for planning.
    """
    if unlock_year is None:
        return 0
    if year <= unlock_year:
        return 0

    if quarter < 1 or quarter > QUARTERS_PER_YEAR:
        raise ValueError(f"quarter must be 1-4, got {quarter}")

    decay_start_year = unlock_year + 1
    if year < decay_start_year:
        return 0
    if year == decay_start_year:
        return quarter
    return (year - decay_start_year) * QUARTERS_PER_YEAR + quarter


def effective_required_skill(
    base_skill: float | None,
    unlock_year: int | None,
    year: int,
    *,
    quarter: int = QUARTERS_PER_YEAR,
) -> float | None:
    """Return the skill requirement after quarterly decay, or None if unset."""
    if base_skill is None:
        return None
    elapsed = decay_quarters_elapsed(unlock_year, year, quarter=quarter)
    adjusted = base_skill - (elapsed * SKILL_DECAY_PER_QUARTER)
    return max(0.0, adjusted)
