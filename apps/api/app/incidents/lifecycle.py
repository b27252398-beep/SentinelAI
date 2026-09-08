# Incident state machine — aligned with finalized architecture design.

# Allowed transitions map: current_status → set of valid next statuses
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "Detected":      {"Investigating", "Resolved"},
    "Investigating": {"Identified", "Resolved"},
    "Identified":    {"Mitigating", "Resolved"},
    "Mitigating":    {"Resolved"},
    "Resolved":      {"Closed", "Investigating"},  # Investigating = reopen
    "Closed":        set(),                         # Terminal — no transitions
}

# Statuses that count as "active" for the one-active-incident-per-service invariant
ACTIVE_STATUSES: set[str] = {"Detected", "Investigating", "Identified", "Mitigating"}

# Full set of valid statuses
VALID_STATUSES: set[str] = set(ALLOWED_TRANSITIONS.keys())

# Valid severity values
VALID_SEVERITIES: set[str] = {"P1", "P2", "P3", "P4"}

# Severity rank: lower number = higher severity (P1 is most severe)
SEVERITY_RANK: dict[str, int] = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}


def is_valid_transition(current: str, new: str) -> bool:
    """Returns True if transition from current → new status is permitted."""
    return new in ALLOWED_TRANSITIONS.get(current, set())


def higher_severity(a: str, b: str) -> str:
    """
    Return the higher severity (lower rank number) of the two.
    Used for incident severity auto-upgrade: severity only ever increases.
    """
    rank_a = SEVERITY_RANK.get(a, 99)
    rank_b = SEVERITY_RANK.get(b, 99)
    return a if rank_a <= rank_b else b
