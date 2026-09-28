"""P0-8 model-identity pinning validator.

Validates models.yaml against FV-SPEC-089 through FV-SPEC-095.
All checks are offline — zero endpoint calls, model execution, or GPU jobs.

Exit codes (via the CLI dispatcher in validate_spec.py):
    0 — all checks passed or pending
    1 — one or more validation failures
    2 — missing/malformed inputs
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Sentinel: this validator makes zero model/LLM/GPU/network calls
# ---------------------------------------------------------------------------

_NO_MODEL_CALLS = True  # P0-8 validator makes zero model/LLM/GPU/network calls

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IMMUTABLE_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_FILE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

REQUIRED_ROLE_FIELDS = [
    "repo_id",
    "model_revision",
    "tokenizer_revision",
    "variant",
    "dtype",
    "licence",
]

IDENTITY_HASH_FIELDS = [
    "repo_id",
    "model_revision",
    "tokenizer_revision",
    "dtype",
]

_DECISION_REQUIRED = "DECISION_REQUIRED"


# ---------------------------------------------------------------------------
# Spec loader
# ---------------------------------------------------------------------------


def load_models_spec(spec_root: Path) -> dict:
    """Load and parse models.yaml from spec_root.

    Raises SystemExit(2) on missing or malformed file.
    """
    models_path = spec_root / "models.yaml"
    if not models_path.exists():
        raise SystemExit(f"models.yaml not found: {models_path}")
    try:
        text = models_path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SystemExit(f"YAML parse error in models.yaml: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"models.yaml must be a YAML mapping: {models_path}")
    roles = data.get("roles")
    if not isinstance(roles, dict):
        raise SystemExit(
            f"models.yaml must have a top-level 'roles' mapping: {models_path}"
        )
    return data


# ---------------------------------------------------------------------------
# Identity hash
# ---------------------------------------------------------------------------


def compute_identity_hash(role_entry: dict) -> str | None:
    """Compute the canonical model-identity hash for a role entry.

    Returns ``None`` if any required payload field is missing or unresolved
    (i.e. is ``DECISION_REQUIRED``).

    Hash payload (FV-SPEC-093):
        json.dumps({"repo_id": ..., "model_revision": ...,
                    "tokenizer_revision": ..., "dtype": ...,
                    "adapter_digest": None},
                   sort_keys=True, ensure_ascii=False)
    → "sha256:" + sha256(payload.encode("utf-8")).hexdigest()
    """
    for field in IDENTITY_HASH_FIELDS:
        val = role_entry.get(field)
        if not val or val == _DECISION_REQUIRED:
            return None

    payload = json.dumps(
        {
            "repo_id": role_entry["repo_id"],
            "model_revision": role_entry["model_revision"],
            "tokenizer_revision": role_entry["tokenizer_revision"],
            "dtype": role_entry["dtype"],
            "adapter_digest": None,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------


def _is_pending_role(entry: dict) -> bool:
    """Return True if the role has status: pending."""
    return entry.get("status") == "pending"


def _is_unresolved(val: object) -> bool:
    """True when a field is still the open-decision placeholder."""
    return val == _DECISION_REQUIRED


def _deadline_state(deadline: object) -> str:
    """Classify a staged-role deadline: missing, invalid, passed, or ok."""
    if deadline is None:
        return "missing"
    if isinstance(deadline, datetime):
        deadline_date = deadline.date()
    elif isinstance(deadline, date):
        deadline_date = deadline
    else:
        try:
            deadline_date = date.fromisoformat(str(deadline)[:10])
        except ValueError:
            return "invalid"
    if deadline_date < date.today():
        return "passed"
    return "ok"


def _make_check(rule_id: str, rule_name: str, status: str, diagnostics: list) -> dict:
    return {
        "rule_id": rule_id,
        "rule_name": rule_name,
        "status": status,
        "diagnostics": diagnostics,
    }


# ---------------------------------------------------------------------------
# FV-SPEC-089: Identity completeness
# ---------------------------------------------------------------------------


def check_fv_spec_089_identity(roles: dict, strict: bool = False) -> list[dict]:
    """FV-SPEC-089: All required fields are present and non-empty (non-pending roles).

    Non-strict ``DECISION_REQUIRED`` on a present role is ``pending``, not pass.
    Strict mode fails those placeholders.
    A staged role (``status: pending``) is not a field failure. A null deadline
    is a warning. A deadline that has already passed fails.
    Resolved ``variant`` must be ``base`` or ``instruct``.
    """
    failures: list[str] = []
    warnings: list[str] = []
    unresolved: list[str] = []

    for role_name, entry in roles.items():
        if not isinstance(entry, dict):
            failures.append(f"Role '{role_name}' is not a mapping.")
            continue

        if _is_pending_role(entry):
            state = _deadline_state(entry.get("deadline"))
            if state == "missing":
                warnings.append(
                    f"Role '{role_name}' has status 'pending' but 'deadline' is null; "
                    f"set a deadline before Phase 6."
                )
            elif state == "invalid":
                failures.append(
                    f"Role '{role_name}' deadline {entry.get('deadline')!r} "
                    f"is not an ISO date."
                )
            elif state == "passed":
                failures.append(
                    f"Role '{role_name}' is still pending and deadline "
                    f"{entry.get('deadline')} has passed."
                )
            continue

        for field in REQUIRED_ROLE_FIELDS:
            val = entry.get(field)
            if val is None or val == "":
                failures.append(
                    f"Role '{role_name}': required field '{field}' is missing or empty."
                )
            elif _is_unresolved(val):
                message = (
                    f"Role '{role_name}': field '{field}' is still "
                    f"'{_DECISION_REQUIRED}'."
                )
                if strict:
                    failures.append(message + " (strict mode).")
                else:
                    unresolved.append(message)
            elif field == "variant" and val not in ("base", "instruct"):
                failures.append(
                    f"Role '{role_name}': variant {val!r} must be 'base' or 'instruct'."
                )

    if failures:
        return [
            _make_check(
                "FV-SPEC-089",
                "identity_completeness",
                "fail",
                failures + warnings + unresolved,
            )
        ]
    if unresolved:
        return [
            _make_check(
                "FV-SPEC-089", "identity_completeness", "pending", unresolved + warnings
            )
        ]
    if warnings:
        return [_make_check("FV-SPEC-089", "identity_completeness", "pass", warnings)]
    return []


# ---------------------------------------------------------------------------
# FV-SPEC-090: Immutable revision
# ---------------------------------------------------------------------------


def check_fv_spec_090_immutable_revision(roles: dict) -> list[dict]:
    """FV-SPEC-090: model_revision and tokenizer_revision must be 40-char hex SHAs.

    Pending roles are skipped.
    Unresolved placeholders are ``pending``, not a silent pass.
    A present value that is not a 40-character hex commit fails.
    """
    failures: list[str] = []
    unresolved: list[str] = []

    for role_name, entry in roles.items():
        if not isinstance(entry, dict) or _is_pending_role(entry):
            continue

        for field in ("model_revision", "tokenizer_revision"):
            val = entry.get(field)
            if val is None or val == "" or _is_unresolved(val):
                unresolved.append(
                    f"Role '{role_name}': '{field}' is unresolved; "
                    f"immutable-revision check pending."
                )
                continue
            if not IMMUTABLE_REVISION_RE.fullmatch(str(val)):
                failures.append(
                    f"Role '{role_name}': '{field}' = '{val}' is not a 40-char hex SHA "
                    f"(got {len(str(val))} chars). Use the full commit hash."
                )

    if failures:
        return [
            _make_check(
                "FV-SPEC-090", "immutable_revision", "fail", failures + unresolved
            )
        ]
    if unresolved:
        return [_make_check("FV-SPEC-090", "immutable_revision", "pending", unresolved)]
    return []


# ---------------------------------------------------------------------------
# FV-SPEC-091: File digests
# ---------------------------------------------------------------------------


def _compute_file_sha256(path: Path) -> str:
    """Return 'sha256:<hex>' for a file."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def check_fv_spec_091_digests(
    roles: dict,
    model_dir: Path | None,
    role_name: str,
) -> list[dict]:
    """FV-SPEC-091: Offline file-digest integrity for a single role.

    - ``model_dir`` absent → ``pending``
    - ``files == {}`` → ``pending`` (files not yet recorded)
    - Otherwise: recompute SHA-256 for each listed file; fail on mismatch,
      missing file, or extra file in the directory.
    """
    entry = roles.get(role_name, {})
    if not isinstance(entry, dict):
        return [
            _make_check(
                "FV-SPEC-091",
                "file_digests",
                "pending",
                [f"Role '{role_name}' not found."],
            )
        ]

    files_dict = entry.get("files", {})

    if model_dir is None:
        return [
            _make_check(
                "FV-SPEC-091",
                "file_digests",
                "pending",
                ["No --model-dir provided; digest check deferred."],
            )
        ]

    if not files_dict:
        return [
            _make_check(
                "FV-SPEC-091",
                "file_digests",
                "pending",
                [
                    f"Role '{role_name}': 'files' dict is empty; "
                    f"populate after download."
                ],
            )
        ]

    diagnostics: list[str] = []
    model_dir = Path(model_dir)

    # Check each file in the manifest
    for filename, stored_digest in files_dict.items():
        if not SHA256_FILE_RE.fullmatch(str(stored_digest)):
            diagnostics.append(
                f"Role '{role_name}': '{filename}' digest {stored_digest!r} "
                f"is not 'sha256:' followed by 64 hex characters."
            )
            continue
        fpath = model_dir / filename
        if not fpath.is_file():
            diagnostics.append(
                f"Role '{role_name}': file '{filename}' is in manifest but not on disk."
            )
            continue
        actual_digest = _compute_file_sha256(fpath)
        if actual_digest != stored_digest:
            diagnostics.append(
                f"Role '{role_name}': '{filename}' digest mismatch. "
                f"Expected {stored_digest}, got {actual_digest}."
            )

    # Extra files anywhere under model_dir, including nested paths
    if model_dir.is_dir():
        manifest_names = set(files_dict.keys())
        for fpath in model_dir.rglob("*"):
            if not fpath.is_file():
                continue
            rel = fpath.relative_to(model_dir).as_posix()
            if rel not in manifest_names:
                diagnostics.append(
                    f"Role '{role_name}': file '{rel}' is on disk but not in manifest."
                )

    if not diagnostics:
        return []
    return [_make_check("FV-SPEC-091", "file_digests", "fail", diagnostics)]


# ---------------------------------------------------------------------------
# FV-SPEC-092: Access-profile compatibility
# ---------------------------------------------------------------------------


def _profile_requires_logits(fm: dict) -> bool:
    """True when any declared system enables score or logit observation."""
    systems = fm.get("systems")
    if not isinstance(systems, dict):
        return False
    for system in systems.values():
        if not isinstance(system, dict):
            continue
        capabilities = system.get("capabilities")
        if not isinstance(capabilities, dict):
            continue
        scores = str(capabilities.get("scores", "")).lower()
        internals = str(capabilities.get("internals", "")).lower()
        if scores not in ("", "unavailable", "none") or internals not in (
            "",
            "unavailable",
            "none",
        ):
            return True
    return False


def check_fv_spec_092_access_profile(
    roles: dict,
    profile_path: Path,
    strict: bool = False,
) -> list[dict]:
    """FV-SPEC-092: Declared models must be compatible with access profile channels.

    - ``profile_path`` absent → ``pending``
    - Enabled score/logit observation, ``fine_tune``, or ``export_checkpoint``
      cannot be satisfied by an ``api_only`` licence.
    - An unresolved licence is ``pending`` in non-strict mode and a failure
      in strict mode when one of those channels is enabled.
    - Profile A (text only, no fine-tuning) passes by construction.
    """
    if profile_path is None or not Path(profile_path).exists():
        return [
            _make_check(
                "FV-SPEC-092",
                "access_profile_compat",
                "pending",
                ["access_profile.md not found; check deferred."],
            )
        ]

    try:
        text = Path(profile_path).read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            fm = yaml.safe_load(parts[1]) or {}
        else:
            fm = yaml.safe_load(text) or {}
    except (yaml.YAMLError, OSError) as exc:
        return [
            _make_check(
                "FV-SPEC-092",
                "access_profile_compat",
                "fail",
                [f"Could not parse access_profile.md: {exc}"],
            )
        ]

    # Extract intervention channels
    interventions = fm.get("interventions", {})
    fine_tune_required = False
    export_required = False
    if isinstance(interventions, dict):
        for channel, state in interventions.items():
            if "fine_tune" in channel.lower() and state not in ("unavailable", None):
                fine_tune_required = True
            if "export_checkpoint" in channel.lower() and state not in (
                "unavailable",
                None,
            ):
                export_required = True
    elif isinstance(interventions, list):
        for item in interventions:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "")
            state = item.get("state", "unavailable")
            if "fine_tune" in name.lower() and state not in ("unavailable", None):
                fine_tune_required = True
            if "export_checkpoint" in name.lower() and state not in (
                "unavailable",
                None,
            ):
                export_required = True

    logits_required = _profile_requires_logits(fm)
    if not fine_tune_required and not export_required and not logits_required:
        # Profile A — text only; no score or finetune channel to satisfy
        return []

    failures: list[str] = []
    unresolved: list[str] = []
    channels = []
    if logits_required:
        channels.append("logits")
    if fine_tune_required:
        channels.append("fine_tune")
    if export_required:
        channels.append("export_checkpoint")

    for role_name, entry in roles.items():
        if not isinstance(entry, dict) or _is_pending_role(entry):
            continue
        licence = entry.get("licence", "")
        if _is_unresolved(licence):
            message = (
                f"Role '{role_name}': licence is '{_DECISION_REQUIRED}' but "
                f"access profile requires {channels}."
            )
            if strict:
                failures.append(message)
            else:
                unresolved.append(message)
        elif "api_only" in str(licence).lower():
            failures.append(
                f"Role '{role_name}': licence '{licence}' is 'api_only' but "
                f"access profile requires {channels}."
            )

    if failures:
        return [
            _make_check(
                "FV-SPEC-092", "access_profile_compat", "fail", failures + unresolved
            )
        ]
    if unresolved:
        return [
            _make_check("FV-SPEC-092", "access_profile_compat", "pending", unresolved)
        ]
    return []


# ---------------------------------------------------------------------------
# FV-SPEC-093: Identity hash definition
# ---------------------------------------------------------------------------


def check_fv_spec_093_identity_hash(roles: dict) -> list[dict]:
    """FV-SPEC-093: Compute and record identity hashes for all resolved roles.

    Fully resolved roles get their hash recorded.
    Roles with unresolved fields produce a ``pending`` result.
    The check always passes (it is a definition, not a constraint).
    """
    diagnostics: list[str] = []
    all_pending = True

    for role_name, entry in roles.items():
        if not isinstance(entry, dict):
            continue
        if _is_pending_role(entry):
            diagnostics.append(f"Role '{role_name}': status pending, hash deferred.")
            continue

        h = compute_identity_hash(entry)
        if h is None:
            diagnostics.append(
                f"Role '{role_name}': one or more identity fields unresolved; hash pending."
            )
        else:
            diagnostics.append(f"Role '{role_name}': identity_hash = {h}")
            all_pending = False

    status = "pending" if all_pending else "pass"
    return [_make_check("FV-SPEC-093", "identity_hash_definition", status, diagnostics)]


# ---------------------------------------------------------------------------
# FV-SPEC-094: Downstream binding
# ---------------------------------------------------------------------------


def check_fv_spec_094_downstream(
    roles: dict,
    downstream_report: Path | None,
) -> list[dict]:
    """FV-SPEC-094: Downstream exclusion-gate report must reference the correct model hash.

    - ``downstream_report`` absent → ``pending``
    - Present: parse JSON, read ``model_identity_hash``, compare against computed hash.
    - Ledger and cache checks are always ``pending`` at P0-8 time.
    """
    results = []

    if downstream_report is None or not Path(downstream_report).exists():
        results.append(
            _make_check(
                "FV-SPEC-094",
                "downstream_binding",
                "pending",
                ["No --downstream-report provided; binding check deferred."],
            )
        )
    else:
        try:
            report_data = json.loads(
                Path(downstream_report).read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError) as exc:
            results.append(
                _make_check(
                    "FV-SPEC-094",
                    "downstream_binding",
                    "fail",
                    [f"Could not parse downstream report: {exc}"],
                )
            )
            return results

        stored_hash = report_data.get("model_identity_hash")

        # Find first resolved role to compute expected hash
        expected_hash = None
        for role_name, entry in roles.items():
            if not isinstance(entry, dict) or _is_pending_role(entry):
                continue
            h = compute_identity_hash(entry)
            if h is not None:
                expected_hash = h
                break

        if expected_hash is None:
            results.append(
                _make_check(
                    "FV-SPEC-094",
                    "downstream_binding",
                    "pending",
                    ["No resolved role found; downstream binding deferred."],
                )
            )
        elif stored_hash != expected_hash:
            results.append(
                _make_check(
                    "FV-SPEC-094",
                    "downstream_binding",
                    "fail",
                    [
                        f"model_identity_hash mismatch. "
                        f"Downstream report has '{stored_hash}', "
                        f"but computed hash is '{expected_hash}'."
                    ],
                )
            )
        else:
            results.append(_make_check("FV-SPEC-094", "downstream_binding", "pass", []))

    # Ledger and cache manifest checks — always pending at P0-8 time
    results.append(
        _make_check(
            "FV-SPEC-094",
            "ledger_binding",
            "pending",
            ["ledger.sqlite not yet built (P2-5)."],
        )
    )
    results.append(
        _make_check(
            "FV-SPEC-094",
            "cache_manifests_binding",
            "pending",
            ["Cache manifests not yet built (P2-7)."],
        )
    )

    return results


# ---------------------------------------------------------------------------
# FV-SPEC-095: Amendment protocol
# ---------------------------------------------------------------------------


def check_fv_spec_095_amendment(spec_root: Path) -> list[dict]:
    """FV-SPEC-095: After freeze, any change to models.yaml requires an amendment record.

    - ``CHECKSUMS.sha256`` absent → ``pending`` (spec not yet frozen)
    - Present: compute SHA-256 of current ``models.yaml``; compare against stored value.
    - If mismatch: scan ``preregistration.md`` for an amendment referencing ``models.yaml``.
    - If no amendment found → fail.
    """
    checksums_path = spec_root.parent / "CHECKSUMS.sha256"
    models_path = spec_root / "models.yaml"

    if not checksums_path.exists():
        return [
            _make_check(
                "FV-SPEC-095",
                "amendment_protocol",
                "pending",
                ["CHECKSUMS.sha256 not found; spec not yet frozen."],
            )
        ]

    if not models_path.exists():
        return [
            _make_check(
                "FV-SPEC-095",
                "amendment_protocol",
                "fail",
                ["models.yaml not found under spec_root."],
            )
        ]

    current_digest = "sha256:" + hashlib.sha256(models_path.read_bytes()).hexdigest()

    # Find models.yaml line in CHECKSUMS.sha256
    stored_digest: str | None = None
    checksums_text = checksums_path.read_text(encoding="utf-8")
    for line in checksums_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            continue
        digest_part, path_part = parts
        # Match lines where path ends with models.yaml
        if path_part.strip().endswith("models.yaml"):
            stored_digest = digest_part.strip()
            break

    if stored_digest is None:
        # models.yaml not in checksums — it was not part of the freeze
        return [
            _make_check(
                "FV-SPEC-095",
                "amendment_protocol",
                "pending",
                [
                    "models.yaml not found in CHECKSUMS.sha256; "
                    "artifact was not frozen yet."
                ],
            )
        ]

    # Normalize stored_digest: strip "sha256:" prefix if present for comparison
    stored_hex = stored_digest.replace("sha256:", "").strip()
    current_hex = current_digest.replace("sha256:", "").strip()

    if stored_hex == current_hex:
        return []

    # Digest mismatch — require a recorded amendment, a new spec tag, and
    # an exclusion-gate re-run (FV-SPEC-095 / US4.1). A mention of the filename
    # alone is not enough.
    prereg_path = spec_root / "preregistration.md"
    prereg_text = (
        prereg_path.read_text(encoding="utf-8") if prereg_path.exists() else ""
    )
    missing = _amendment_gaps(prereg_text)
    if not missing:
        return []

    return [
        _make_check(
            "FV-SPEC-095",
            "amendment_protocol",
            "fail",
            [
                f"models.yaml has been modified since the freeze "
                f"(stored: sha256:{stored_hex}, current: {current_digest}). "
                f"Amendment protocol incomplete: {', '.join(missing)}."
            ],
        )
    ]


def _amendment_gaps(prereg_text: str) -> list[str]:
    """Name the amendment-protocol pieces still missing from preregistration text."""
    lowered = prereg_text.lower()
    gaps: list[str] = []
    if "models.yaml" not in lowered or "amendment" not in lowered:
        gaps.append("recorded amendment referencing models.yaml")
    tags = set(re.findall(r"spec-v\d+", lowered))
    if not tags or tags <= {"spec-v1"}:
        gaps.append("new spec version tag")
    if "exclusion" not in lowered or re.search(r"re-?run", lowered) is None:
        gaps.append("exclusion-gate re-run")
    return gaps


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def write_models_report(
    checks: list[dict],
    spec_root: Path,
    strict: bool,
    report_path: Path | None,
    roles: dict,
    runtime_seconds: float | None = None,
) -> dict:
    """Build and optionally write the JSON validation report."""
    # Compute identity_hashes for all roles
    identity_hashes: dict[str, str | None] = {}
    for role_name, entry in roles.items():
        if not isinstance(entry, dict) or _is_pending_role(entry):
            identity_hashes[role_name] = None
        else:
            identity_hashes[role_name] = compute_identity_hash(entry)

    # Determine pending_artefacts
    pending_artefacts = []
    for check in checks:
        if check.get("status") == "pending":
            rn = check.get("rule_name", "")
            if rn not in pending_artefacts:
                pending_artefacts.append(rn)

    # overall: "pass" when all checks are "pass" or "pending"; "fail" if any "fail"
    overall = "pass"
    for check in checks:
        if check.get("status") == "fail":
            overall = "fail"
            break

    report = {
        "report_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "spec_root": str(spec_root.resolve()),
        "scope": "models",
        "strict": strict,
        "checks": checks,
        "identity_hashes": identity_hashes,
        "pending_artefacts": pending_artefacts,
        "runtime_seconds": runtime_seconds,
        "overall": overall,
    }

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return report


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def validate_models_spec(
    spec_root: Path,
    *,
    model_dir: Path | None = None,
    access_profile_path: Path | None = None,
    downstream_report_path: Path | None = None,
    strict: bool = False,
    report_path: Path | None = None,
) -> tuple[bool, dict]:
    """Run all FV-SPEC-089 through FV-SPEC-095 checks on models.yaml.

    Returns ``(success, report_dict)`` where ``success`` is ``True`` when
    ``overall == "pass"`` (no failures).

    Raises ``SystemExit(2)`` on missing or malformed models.yaml.
    """
    started = time.perf_counter()
    data = load_models_spec(spec_root)
    roles: dict = data.get("roles", {})

    # Default access_profile_path
    if access_profile_path is None:
        access_profile_path = spec_root / "access_profile.md"

    checks: list[dict] = []

    # FV-SPEC-089: Identity completeness
    checks.extend(
        check_fv_spec_089_identity(roles, strict=strict)
        or [_make_check("FV-SPEC-089", "identity_completeness", "pass", [])]
    )

    # FV-SPEC-090: Immutable revision
    checks.extend(
        check_fv_spec_090_immutable_revision(roles)
        or [_make_check("FV-SPEC-090", "immutable_revision", "pass", [])]
    )

    # FV-SPEC-091: File digests (per non-pending role)
    digests_done = False
    for role_name, entry in roles.items():
        if not isinstance(entry, dict) or _is_pending_role(entry):
            continue
        role_checks = check_fv_spec_091_digests(roles, model_dir, role_name)
        checks.extend(role_checks)
        digests_done = True
    if not digests_done:
        checks.append(
            _make_check(
                "FV-SPEC-091",
                "file_digests",
                "pending",
                ["No non-pending roles to check."],
            )
        )

    # FV-SPEC-092: Access profile compatibility
    checks.extend(
        check_fv_spec_092_access_profile(roles, access_profile_path, strict=strict)
        or [_make_check("FV-SPEC-092", "access_profile_compat", "pass", [])]
    )

    # FV-SPEC-093: Identity hash definition
    checks.extend(check_fv_spec_093_identity_hash(roles))

    # FV-SPEC-094: Downstream binding
    checks.extend(check_fv_spec_094_downstream(roles, downstream_report_path))

    # FV-SPEC-095: Amendment protocol
    checks.extend(
        check_fv_spec_095_amendment(spec_root)
        or [_make_check("FV-SPEC-095", "amendment_protocol", "pass", [])]
    )

    report = write_models_report(
        checks=checks,
        spec_root=spec_root,
        strict=strict,
        report_path=report_path,
        roles=roles,
        runtime_seconds=round(time.perf_counter() - started, 6),
    )

    success = report["overall"] == "pass"
    return success, report
