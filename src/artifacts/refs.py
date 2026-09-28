"""External blob references (FV-SPEC-103)."""
from __future__ import annotations

import urllib.request
from dataclasses import dataclass


class BlobRefError(Exception):
    """Raised when an external blob reference is invalid or unavailable."""


@dataclass(frozen=True)
class ExternalBlobRef:
    uri: str
    byte_size: int
    content_digest: str  # "sha256:hex"
    producer_run_id: str

    def __post_init__(self) -> None:
        if not self.uri:
            raise BlobRefError("uri is required")
        if self.byte_size <= 0:
            raise BlobRefError("byte_size must be positive")
        if not self.content_digest.startswith("sha256:"):
            raise BlobRefError("content_digest must start with 'sha256:'")
        if not self.producer_run_id:
            raise BlobRefError("producer_run_id is required")

    def check_availability(self) -> bool:
        """Return True if the URI is accessible. Non-destructive probe."""
        if self.uri.startswith("file://") or not self.uri.startswith("http"):
            from pathlib import Path
            if self.uri.startswith("file://"):
                raw = self.uri.removeprefix("file://")
            else:
                raw = self.uri
            return Path(raw).exists()
        try:
            req = urllib.request.Request(self.uri, method="HEAD")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def to_dict(self) -> dict[str, object]:
        return {
            "uri": self.uri,
            "byte_size": self.byte_size,
            "content_digest": self.content_digest,
            "producer_run_id": self.producer_run_id,
        }
