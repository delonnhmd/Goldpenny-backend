# Re-export shim so both `app.models.economy_state` and `app.models.economy`
# resolve to the same EconomyState class.
from app.models.economy import EconomyState  # noqa: F401

__all__ = ["EconomyState"]
