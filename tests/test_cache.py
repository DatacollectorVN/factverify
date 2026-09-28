"""FV-CACHE hooks. Keys stay full sha256 and the store does not overwrite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.cache.errors import CacheError
from src.cache.export import export_cache, import_cache
from src.cache.key import CacheBody, CacheRequest, cache_key
from src.cache.store import get_or_compute, open_cache

DECISIONS = Path("tests/fixtures/cache/decisions")
OMIT = DECISIONS / "d60_omit.yaml"


def _request(**overrides: object) -> CacheRequest:
    fields: dict[str, object] = {
        "identity_hash": "model-a",
        "model_input": "Where is Zephyr?",
        "decoding": {"temperature": 0},
        "seed": 1,
        "sample_index": 1,
        "request_kind": "generate",
        "producer_run_id": "run-1",
        "software_versions": None,
    }
    fields.update(overrides)
    return CacheRequest(**fields)  # type: ignore[arg-type]


def _body(text: str) -> CacheBody:
    return CacheBody(body=text, token_count=1)


def test_fv_cache_001_full_key(tmp_path: Path) -> None:
    base = _request()
    base_key = cache_key(base, decisions=OMIT)
    variants = [
        {"identity_hash": "model-b"},
        {"model_input": "Where is Zephyr? "},
        {"decoding": {"temperature": 1}},
        {"seed": 2},
        {"sample_index": 2},
        {"request_kind": "score"},
    ]
    for item in variants:
        assert cache_key(_request(**item), decisions=OMIT) != base_key
    incomplete = _request(identity_hash="")
    with pytest.raises(CacheError, match="identity_hash"):
        cache_key(incomplete, decisions=OMIT)
    calls = {"n": 0}

    def compute() -> CacheBody:
        calls["n"] += 1
        return _body("no")

    cache = open_cache(tmp_path / "cache", decisions=DECISIONS / "open.yaml")
    with pytest.raises(CacheError, match="D-60"):
        get_or_compute(cache, base, compute)
    assert calls["n"] == 0
    included = cache_key(
        _request(software_versions={"torch": "2"}),
        decisions=DECISIONS / "d60_include.yaml",
    )
    omitted = cache_key(base, decisions=OMIT)
    assert included != omitted
    with pytest.raises(CacheError, match="software_versions"):
        cache_key(base, decisions=DECISIONS / "d60_include.yaml")
    with pytest.raises(CacheError, match="D-60"):
        cache_key(base, decisions=DECISIONS / "d60_bad.yaml")


def test_fv_cache_002_exact_input() -> None:
    left = cache_key(_request(model_input="Zephyr"), decisions=OMIT)
    right = cache_key(_request(model_input="Zephyr "), decisions=OMIT)
    assert left != right
    assert cache_key(_request(model_input="Zephyr"), decisions=OMIT) == left


def test_fv_cache_003_samples_distinct(tmp_path: Path) -> None:
    cache = open_cache(tmp_path / "outside", decisions=OMIT)
    for index in (1, 2, 3):
        entry, event = get_or_compute(
            cache, _request(sample_index=index), lambda text=str(index): _body(text)
        )
        assert event.kind == "miss"
        assert entry.body == str(index)
    _entry, missed = get_or_compute(cache, _request(sample_index=4), lambda: _body("4"))
    assert missed.kind == "miss"


def test_fv_cache_004_events(tmp_path: Path) -> None:
    cache = open_cache(tmp_path / "cache", decisions=OMIT)
    calls = {"n": 0}

    def compute() -> CacheBody:
        calls["n"] += 1
        return _body("stored")

    _first, miss = get_or_compute(cache, _request(), compute)
    assert miss.kind == "miss"
    assert calls["n"] == 1
    _second, hit = get_or_compute(cache, _request(), compute)
    assert hit.kind == "hit"
    assert calls["n"] == 1
    kinds = [event.kind for event in cache.events()]
    assert kinds == ["miss", "hit"]
    for path in list(Path("src/cache").rglob("*.py")) + list(
        Path("src/eval").rglob("*.py")
    ):
        if path.name == "gateway.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert ".get_or_compute(" not in text


def test_fv_cache_005_integrity(tmp_path: Path) -> None:
    cache = open_cache(tmp_path / "cache", decisions=OMIT)
    entry, event = get_or_compute(cache, _request(), lambda: _body("intact"))
    assert event.kind == "miss"
    again, hit = get_or_compute(cache, _request(), lambda: _body("other"))
    assert hit.kind == "hit"
    assert again.body == "intact"
    cache.connection.execute(
        "UPDATE entries SET body = ? WHERE content_digest = ?",
        (json.dumps("tampered"), entry.content_digest),
    )
    calls = {"n": 0}

    def recompute() -> CacheBody:
        calls["n"] += 1
        return _body("recomputed")

    replaced, corrupt = get_or_compute(cache, _request(), recompute)
    assert corrupt.kind == "corrupt"
    assert calls["n"] == 1
    assert replaced.body == "recomputed"
    assert replaced.body != "tampered"


def test_fv_cache_006_no_overwrite(tmp_path: Path) -> None:
    cache = open_cache(tmp_path / "cache", decisions=OMIT)
    stored, _miss = get_or_compute(cache, _request(), lambda: _body("one"))
    same, hit = get_or_compute(cache, _request(), lambda: _body("one"))
    assert hit.kind == "hit"
    assert same.content_digest == stored.content_digest
    with pytest.raises(CacheError, match="conflict") as raised:
        get_or_compute(
            cache,
            _request(producer_run_id="run-2"),
            lambda: _body("two"),
        )
    event = raised.value.event
    assert isinstance(event, object)
    assert getattr(event, "kind", None) == "conflict"
    assert getattr(event, "stored_digest", None) == stored.content_digest
    assert getattr(event, "new_digest", None) != stored.content_digest
    reread, still = get_or_compute(cache, _request(), lambda: _body("two"))
    assert still.kind == "hit"
    assert reread.content_digest == stored.content_digest
    assert reread.body == "one"


def test_fv_cache_007_location(tmp_path: Path) -> None:
    opened = open_cache(tmp_path / "outside", decisions=OMIT)
    assert opened.root.name == "outside"
    inside = tmp_path / ".factverify" / "cache"
    with pytest.raises(CacheError, match="location"):
        open_cache(inside, decisions=OMIT)


def test_fv_cache_008_export(tmp_path: Path) -> None:
    cache = open_cache(tmp_path / "cache", decisions=OMIT)
    entry, _event = get_or_compute(cache, _request(), lambda: _body("exported"))
    directory = tmp_path / "export"
    export_cache(cache, directory)
    copied = import_cache(directory, tmp_path / "imported", decisions=OMIT)
    row = copied.connection.execute(
        "SELECT content_digest FROM entries WHERE cache_key = ?",
        (cache.connection.execute("SELECT cache_key FROM entries").fetchone()[0],),
    ).fetchone()
    assert row is not None
    assert row["content_digest"] == entry.content_digest
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["digest"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CacheError, match="digest"):
        import_cache(directory, tmp_path / "bad", decisions=OMIT)
