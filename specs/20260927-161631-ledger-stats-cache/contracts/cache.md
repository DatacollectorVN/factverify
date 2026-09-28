# Contract: cache

**Feature**: `20260927-161631-ledger-stats-cache`  
**Modules**: `src/cache/key.py`, `src/cache/store.py`, `src/cache/export.py`, `src/eval/gateway.py`

## Signature

```python
def open_cache(root: Path, *, decisions: Path) -> Cache:
    """Refuse a root inside .factverify. Create the store directory otherwise."""


def cache_key(request: CacheRequest, *, decisions: Path) -> str:
    """Full sha256 key, or CacheError('D-60') while that row is open."""


def get_or_compute(
    cache: Cache,
    request: CacheRequest,
    compute: Callable[[], CacheBody],
) -> tuple[CacheEntry, CacheEvent]:
    """Return the stored body or the computed body, and exactly one event."""


def export_cache(cache: Cache, directory: Path) -> None:
    """Write entries and a manifest of keys and digests."""


def import_cache(directory: Path, root: Path, *, decisions: Path) -> Cache:
    """Refuse a manifest digest that disagrees with the entry bytes."""
```

`compute` is called only on a miss or on a corrupt entry. It is not called on a hit.

## Steps for get_or_compute

1. Derive the key. An open D-60 row, or a missing key field, raises and does not call `compute`.
2. If the key is absent, call `compute`, insert the body and its digest, and return `miss`.
3. If the key is present, recompute the digest from the stored body. A mismatch emits `corrupt`, does not return the stored body, calls `compute`, and inserts the new body only when that new digest is not already stored under a different body. The caller observes one event, `corrupt`.
4. If `compute` produces the stored digest, leave the row unchanged and return `hit`.
5. If `compute` produces a different digest for an existing key, append a `conflict` event that carries both digests, leave the stored row, and raise `CacheError("conflict")`.

## Gateway

```python
class CachePort(Protocol):
    def get_or_compute(
        self,
        request: CacheRequest,
        compute: Callable[[], CacheBody],
    ) -> tuple[CacheEntry, CacheEvent]: ...
```

`Gateway` takes `identity_hash: str`. `complete` and `score` build a `CacheRequest` and call `get_or_compute`. They do not call `get` or `put`.

After the call:

- `hit` → `accountant.query(..., kind="cache_hit")` and `accountant.note_cache_event(event)`
- `miss` or `corrupt` → `accountant.query(..., kind="generation")` and `note_cache_event`
- `conflict` → `query` kind `generation`, `note_cache_event`, then raise

`note_cache_event` appends the event and does not change a remaining balance. `budget.py` charge rules are not edited.

A test reads `src/eval` and `src/cache` and fails when a file other than `gateway.py` calls `get_or_compute`, or when `store.py` exposes a read that returns a body without an event.

## Existing single-sample calls

`src/eval/native.py` and `src/eval/__init__.py` pass `sample_index=1` on the one completion they already request. A missing `sample_index` raises `sample_index` inside `cache_key`.
