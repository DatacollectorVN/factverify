"""FactVerify model loader error type."""

from __future__ import annotations


class FactVerifyLoaderError(ValueError):
    """Raised by load_model on any bad, missing, or unresolvable input.

    Always raised before a model object is returned. The message names the
    role, file, or field that caused the failure.
    """
