"""Authorization policy for classified resources."""

from models.access_level import can_access


def user_can_access(user, required_level: int) -> bool:
    """Authentication is deliberately not part of this permission decision."""
    return can_access(user.access_level, required_level)