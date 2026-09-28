"""Runtime artifact store with ledger guard (FV-SPEC-100, 101, 107)."""
from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from src.artifacts.layout import ArtifactClass, LayoutError, LayoutRoots


class UnledgeredArtifactError(Exception):
    """Raised when analysis attempts to consume an unregistered artifact."""


class StoreError(Exception):
    """Raised when a store operation violates namespace or registration rules."""


_NON_EVIDENTIARY = frozenset({ArtifactClass.TEMPORARY})
_EVIDENCE_CLASSES = frozenset({
    ArtifactClass.GENERATION,
    ArtifactClass.SCORE,
    ArtifactClass.WITNESS,
    ArtifactClass.RESULT,
    ArtifactClass.REPORT,
    ArtifactClass.CHECKPOINT,
})


class ArtifactStore:
    """Write runtime artifacts with ledger registration."""

    def __init__(self, roots: LayoutRoots, ledger: sqlite3.Connection) -> None:
        self._roots = roots
        self._ledger = ledger
        self._ensure_store_table()

    @contextmanager
    def write(
        self,
        artifact_class: ArtifactClass,
        run_id: str,
        filename: str,
    ) -> Generator[Path, None, None]:
        """Yield a path for writing; register in ledger on clean exit."""
        if artifact_class == ArtifactClass.TEMPORARY:
            dest = self._roots.internal_root / "tmp" / run_id / filename
        elif artifact_class in (
            ArtifactClass.GENERATION, ArtifactClass.SCORE, ArtifactClass.WITNESS
        ):
            dest = self._roots.internal_root / "evidence" / run_id / filename
        elif artifact_class == ArtifactClass.RESULT:
            dest = self._roots.internal_root / "results" / run_id / filename
        elif artifact_class == ArtifactClass.REPORT:
            dest = self._roots.internal_root / "reports" / run_id / filename
        elif artifact_class == ArtifactClass.CHECKPOINT:
            dest = self._roots.internal_root / "checkpoints" / run_id / filename
        else:
            dest = self._roots.run_dir(run_id) / filename

        # Validate it's under the internal root
        try:
            self._roots.assert_internal_path(dest)
        except LayoutError as exc:
            raise StoreError(str(exc)) from exc

        dest.parent.mkdir(parents=True, exist_ok=True)

        yield dest

        # Register in ledger only if the file was written (clean exit)
        if dest.exists():
            digest = "sha256:" + hashlib.sha256(dest.read_bytes()).hexdigest()
            self._register_in_ledger(artifact_class, run_id, str(dest), digest)

    def register_external_blob(
        self,
        uri: str,
        byte_size: int,
        content_digest: str,
        producer_run_id: str,
    ) -> None:
        """Register an external blob reference in the ledger."""
        if not uri or byte_size <= 0 or not content_digest or not producer_run_id:
            raise StoreError(
                "External blob requires uri, byte_size, content_digest, producer_run_id"
            )
        self._ensure_external_blobs_table()
        self._register_external(uri, byte_size, content_digest, producer_run_id)

    def resolve(self, artifact_class: ArtifactClass, digest: str) -> Path:
        """Return the path of a ledgered artifact.

        Raises UnledgeredArtifactError if not found.
        """
        if artifact_class in _EVIDENCE_CLASSES:
            row = self._ledger.execute(
                "SELECT path FROM artifact_store "
                "WHERE digest = ? AND artifact_class = ?",
                (digest, artifact_class.value),
            ).fetchone()
        else:
            row = self._ledger.execute(
                "SELECT path FROM artifact_store WHERE digest = ?",
                (digest,),
            ).fetchone()

        if row is None:
            raise UnledgeredArtifactError(
                f"No registered artifact with digest {digest!r}. "
                "File must be registered via ArtifactStore.write() before consumption."
            )
        return Path(str(row["path"]))

    def _register_in_ledger(
        self,
        artifact_class: ArtifactClass,
        run_id: str,
        path: str,
        digest: str,
    ) -> None:
        self._ledger.execute(
            "INSERT OR IGNORE INTO artifact_store "
            "(digest, artifact_class, run_id, path) VALUES (?, ?, ?, ?)",
            (digest, artifact_class.value, run_id, path),
        )

    def _register_external(
        self,
        uri: str,
        byte_size: int,
        content_digest: str,
        producer_run_id: str,
    ) -> None:
        self._ledger.execute(
            "INSERT OR IGNORE INTO external_blobs "
            "(content_digest, uri, byte_size, producer_run_id) VALUES (?, ?, ?, ?)",
            (content_digest, uri, byte_size, producer_run_id),
        )

    def _ensure_store_table(self) -> None:
        self._ledger.executescript("""
            CREATE TABLE IF NOT EXISTS artifact_store (
                digest TEXT NOT NULL,
                artifact_class TEXT NOT NULL,
                run_id TEXT NOT NULL,
                path TEXT NOT NULL,
                PRIMARY KEY (digest, artifact_class)
            );
        """)
        self._ledger.row_factory = sqlite3.Row

    def _ensure_external_blobs_table(self) -> None:
        self._ledger.executescript("""
            CREATE TABLE IF NOT EXISTS external_blobs (
                content_digest TEXT PRIMARY KEY,
                uri TEXT NOT NULL,
                byte_size INTEGER NOT NULL,
                producer_run_id TEXT NOT NULL
            );
        """)


def refused_if_tmp_registration(artifact_class: ArtifactClass) -> bool:
    """Return True if this class cannot be registered as evidence/result/checkpoint."""
    return artifact_class in _NON_EVIDENTIARY
