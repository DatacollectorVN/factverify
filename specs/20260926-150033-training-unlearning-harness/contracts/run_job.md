# Contract: `run_job`

**Feature**: `20260926-150033-training-unlearning-harness`  
**Date**: 2026-09-26  
**Module**: `src/train/__init__.py`

---

## Public exports

```python
from src.train import run_job, JobResult, FactVerifyHarnessError
```

Only these three names are public. Method trainers, the catalog, and the ledger protocol are internal to `src/train/` except the protocol, which P2-5 implements (see `ledger_port.md`).

---

## `run_job`

```python
run_job(
    config_path: Path,
    *,
    spec_root: Path,
    ledger: LedgerPort,
) -> JobResult
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `config_path` | `Path` | yes | Job file. Schema in `job_config.md`. |
| `spec_root` | `Path` | yes (keyword-only) | Frozen spec directory passed through to `load_model`. Default on the CLI is `.factverify/spec`. |
| `ledger` | `LedgerPort` | yes (keyword-only) | Commit and seed query. Storage is not created here. |

### Return value

`JobResult`:

| Field | Type | Description |
|-------|------|-------------|
| `status` | `Literal["succeeded", "failed"]` | `succeeded` only after a committed ledger row and a published adapter |
| `adapter_path` | `Path \| None` | Published directory when `succeeded`; otherwise `None` |
| `config_hash` | `str \| None` | Set once the file has been validated |
| `checkpoint_identity_hash` | `str \| None` | Loader identity of the published adapter |
| `error` | `str \| None` | Names the field, document id, item id, seed, or path |

### CLI

```text
python -m src.train.run --config configs/train/<job>.yaml --spec-root .factverify/spec --ledger <path>
```

`--spec-root` defaults to `.factverify/spec`. `--ledger` is required. Until P2-5 provides a SQLite-backed port, a path that does not resolve to that port fails closed with an error that names the missing ledger. Tests call `run_job` with an in-memory port and do not need the CLI ledger flag.

Exit code `0` only when `JobResult.status` is `succeeded`. Any failure exits non-zero and prints `error`.

### Ordering guarantees

1. Unknown method, missing field, unresolved field, procedure mismatch, bundle leak, and cross-split seed are raised before the corpus is opened and before `load_model`.
2. Training text is read only through the manifest catalog.
3. `from_pretrained` is not called in `src/train/`. Bases and parent adapters enter through `load_model`. The returned model is switched to train mode by the harness.
4. A metadata failure does not rename the staging directory into `output_dir`.
5. `status=succeeded` is returned only after `ledger.commit_checkpoint` returns for that checkpoint.
6. A caught crash records partial cost with `status=failed` and does not leave a published adapter.

### Errors

| Trigger | What `error` names |
|---------|--------------------|
| Unreadable config or spec root | the path |
| Missing, null, or `DECISION_REQUIRED` field | the field |
| Unknown method | the method, before any data load |
| Procedure mismatch | the differing fields |
| Bundle document on a reference manifest | the document id |
| Seed already stored for that fact on another split | the seed |
| Unlisted training item | the item id |
| Metadata write failure | the metadata path; nothing published |
| Ledger commit failure | the ledger error; published directory removed |
