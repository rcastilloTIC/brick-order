"""Irreversible purchase commitments during voting and order transitions.

This is deliberately independent of Flask so it can be unit-tested. Every
mutation endpoint must check the recorded quantity BEFORE changing or deleting
it. A privileged correction workflow, if ever added, requires a separately
reviewed and audited process, not an exception to this validator.
"""


def assert_nondecreasing_vote(previous_quantity: int, requested_quantity: int) -> None:
    """Reject invalid or decreasing quantities, including deletion (zero)."""
    from werkzeug.exceptions import BadRequest, Conflict

    if (not isinstance(previous_quantity, int) or isinstance(previous_quantity, bool)
            or not isinstance(requested_quantity, int) or isinstance(requested_quantity, bool)
            or previous_quantity < 0 or requested_quantity < 0):
        raise BadRequest("Cantidad de voto no válida.")
    if requested_quantity < previous_quantity:
        raise Conflict("Una cantidad comprometida no se puede reducir ni eliminar.")
