from .models import ConsultationSession

Status = ConsultationSession.Status

# From status → set of statuses you may move to
ALLOWED_TRANSITIONS = {
    Status.UNASSIGNED: {Status.ASSIGNED},
    Status.ASSIGNED: {Status.ACCEPTED_BY_PROVIDER},
    Status.ACCEPTED_BY_PROVIDER: {Status.IN_PROGRESS},
    Status.IN_PROGRESS: {Status.COMPLETED},
    Status.COMPLETED: set(),  # terminal — nowhere to go
}


def can_transition(current_status, new_status):
    """Return True if moving current → new is allowed."""
    return new_status in ALLOWED_TRANSITIONS.get(current_status, set())


def assert_can_transition(current_status, new_status):
    """
    Raise ValueError if transition is invalid.
    Views will turn this into HTTP 400.
    """
    if not can_transition(current_status, new_status):
        raise ValueError(
            f'Invalid transition from "{current_status}" to "{new_status}".'
        )