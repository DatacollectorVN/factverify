"""Export a forgetter sweep's results and behavioural samples to CSV (read-only on runs).

Writes, under --out-dir:
  runs.csv            one row per forgetter run: config, stop reason, AFC verdict and statistics
  neighbours.csv      one row per (run, neighbour): retention statistics used by p_retain
  drop_retention.csv  one row per (run, fact, family): learner/forgetter log-prob, drop, retention
  epochs.csv          one row per (run, epoch): metrics parsed from the run log
  samples.csv         one row per (model, probe): greedy answer, sampling hit rate, alias-aware log-prob
  sample_texts.csv    one row per (model, probe, sample): the sampled completions themselves
  behaviour.csv       one row per (model, fact): greedy / sampling aggregates from the two files above

The models scored for samples are the learner plus every forgetter's selected checkpoint.
Probes are the English eval probes of the target and its declared neighbours, plus a few
general-knowledge control prompts that are not part of any fact (fact_role = control).

Usage:
  uv run python scripts/sweep_export.py --config-dir config/jobs/phase3 \
      --log-dir .factverify_internal/logs/phase3 --out-dir results/phase3
  (add --skip-samples to export only the recorded results)
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

import yaml

FAMILIES = ["direct", "inverse", "cloze", "para", "verify"]
CONTROL_PROMPTS = [  # not part of any fact; detects broad damage / garbled output
    ("What is the capital of France?", ["Paris"]),
    ("How many days are in a week?", ["7", "seven"]),
    ("What color is the sky on a clear day?", ["blue"]),
    ("What is the largest ocean on Earth?", ["Pacific", "the Pacific Ocean", "Pacific Ocean"]),
    ("Who wrote Romeo and Juliet?", ["William Shakespeare", "Shakespeare"]),
]
CONFIG_KEYS = ["learning_rate", "epochs", "entropy_coeff", "entropy_target_bits", "retain_coeff",
               "beta", "steering_layer", "steering_coeff", "rmu_token_scope"]


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        print(f"  (no rows for {path.name})")
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {path} ({len(rows)} rows)")


def load_runs(config_dir: Path) -> tuple[dict, list[dict]]:
    learner, runs = None, []
    for p in sorted(config_dir.glob("*.yaml")):
        cfg = yaml.safe_load(p.read_text())
        entry = {"config_file": str(p), "cfg": cfg, "job_name": cfg["job"]["name"],
                 "output_dir": cfg["output"]["dir"]}
        if cfg["job"]["role"] == "learner":
            learner = entry
        else:
            entry["run"] = p.stem.removeprefix("forgetter-")
            entry["target"] = cfg["data"]["forget_fact"]
            runs.append(entry)
    if learner is None:
        sys.exit(f"no learner config in {config_dir}")
    return learner, runs


def ledger_rows(ledger: Path) -> dict[str, dict]:
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = {}
    for r in con.execute("select * from experiments where status is not null order by created_at"):
        out[r["job_name"]] = dict(r)  # latest row per job wins
    return out


def short(fact_id: str) -> str:
    return fact_id.split(":")[-1]


def export_results(learner: dict, runs: list[dict], ledger: dict, log_dir: Path, out: Path) -> None:
    run_rows, nb_rows, dr_rows, ep_rows = [], [], [], []
    for r in runs:
        rd = Path(r["output_dir"]) / r["target"]
        afc = json.loads((rd / "afc.json").read_text())
        meta = json.loads((rd / "metadata.json").read_text())
        led = ledger.get(r["job_name"], {})
        tr = r["cfg"]["training"]
        row = {"run": r["run"], "job_name": r["job_name"], "method": r["cfg"]["job"]["method"],
               "seed": r["cfg"]["job"]["seed"]}
        row.update({k: tr.get(k, "") for k in CONFIG_KEYS})
        row.update({
            "stop_reason": meta.get("stop_reason"), "stopped_epoch": meta.get("stopped_epoch"),
            "selected_epoch": afc.get("selected_checkpoint_epoch"),
            "selected_below_guard": afc.get("selected_below_guard"),
            "wall_clock_min": round(led["wall_clock_seconds"] / 60, 1) if led.get("wall_clock_seconds") else "",
            "training_steps": led.get("training_steps", ""),
            "alpha": afc.get("alpha"), "kappa": afc.get("kappa"), "J": afc.get("J"), "n": afc.get("n"),
            "target_min_drop_t": afc.get("t"), "weakest_target_family": afc.get("weakest_family_target"),
            "control_mean_m": afc.get("m"), "control_sd_s": afc.get("s"),
            "T_forget": afc.get("T_forget"), "p_forget": afc.get("p_forget"), "forget_ok": afc.get("forget_ok"),
            "p_retain": afc.get("p_retain"), "retain_ok": afc.get("retain_ok"),
            "weakest_neighbour": (short(afc["neighbours"][afc["weakest_neighbour"]])
                                  if isinstance(afc.get("weakest_neighbour"), int) else ""),
            "lowest_bound_neighbour": (short(afc["neighbours"][afc["lowest_bound_neighbour"]])
                                       if isinstance(afc.get("lowest_bound_neighbour"), int) else ""),
            "lowest_retention_bound": min(afc["retain_lower_bound_j"]) if afc.get("retain_lower_bound_j") else "",
            "p_afc": afc.get("p_afc"), "certified": afc.get("certified"), "verdict": afc.get("verdict"),
            "flags": ";".join(afc.get("flags") or []),
        })
        run_rows.append(row)

        for i, nid in enumerate(afc["neighbours"]):
            nb_rows.append({
                "run": r["run"], "neighbour": short(nid),
                "mean_retention": afc["mean_retention_j"][i], "y_bar_ln_r": afc["y_bar_j"][i],
                "s_j": afc["s_j"][i], "se_j": afc["se_j"][i],
                "T_retain": (afc.get("T_retain") or [None] * len(afc["neighbours"]))[i],
                "retain_lower_bound": afc["retain_lower_bound_j"][i], "p_retain_j": afc["p_retain_j"][i],
                "passes_kappa": afc["p_retain_j"][i] <= afc["alpha"] if afc.get("kappa") is not None else "",
            })

        dr = json.loads((rd / "drop_retention.json").read_text())
        for f in dr["facts"]:
            for fam, v in sorted(f["families"].items()):
                dr_rows.append({
                    "run": r["run"], "fact": short(f["fact_id"]), "fact_role": f["fact_role"], "family": fam,
                    "learner_log_prob": v["learner_log_probability"],
                    "forgetter_log_prob": v["forgetter_log_probability"],
                    "drop": v["drop"], "retention": v["retention"]})
            dr_rows.append({
                "run": r["run"], "fact": short(f["fact_id"]), "fact_role": f["fact_role"], "family": "ALL",
                "learner_log_prob": f["learner_log_probability"],
                "forgetter_log_prob": f["forgetter_log_probability"],
                "drop": f["drop"], "retention": f["retention"]})

        log = log_dir / f"forgetter-{r['run']}.log"
        if log.is_file():
            for line in log.read_text(errors="replace").splitlines():
                m = re.match(r"\s+epoch (\d+)/(\d+)\s+(.*)", line)
                if not m:
                    continue
                e = {"run": r["run"], "epoch": int(m.group(1))}
                for k, v in re.findall(r"(\w+)=([^\s]+)", m.group(3)):
                    if k in ("best", "wait", "bwd"):
                        continue
                    try:
                        e[k] = float(v)
                    except ValueError:
                        e[k] = v
                e["baseline"] = "(baseline)" in line
                ep_rows.append(e)

    write_csv(out / "runs.csv", run_rows)
    write_csv(out / "neighbours.csv", nb_rows)
    write_csv(out / "drop_retention.csv", dr_rows)
    write_csv(out / "epochs.csv", ep_rows)


def export_samples(learner: dict, runs: list[dict], out: Path, n_samples: int, seed: int,
                   max_new_tokens: int) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from src.services.data.qa_format import encode_qa, qa_prompt
    from src.train.data import DataCatalog
    from src.train.methods.alias_score import EntityAliasStore, get_probe_aliases

    target = runs[0]["target"]
    fact_json = json.loads(Path(f".factverify/facts/{target}.json").read_text())
    neighbours = [short(n) for n in fact_json.get("neighbourhoods", [])]
    facts = [target] + neighbours
    store = EntityAliasStore(Path(".factverify/entities"))
    cat = DataCatalog(Path(".factverify/corpuses"), facts, languages=["en"])
    probes = []
    for f in facts:
        for p in cat.get_eval_probes(f):
            probes.append(dict(fact=f, fact_role="target" if f == target else "neighbour", family=p.family,
                               question=p.question, gold=p.answer, aliases=get_probe_aliases(p, store)))
    for q, al in CONTROL_PROMPTS:
        probes.append(dict(fact="control", fact_role="control", family="control", question=q,
                           gold=al[0], aliases=al))

    def correct(text: str, aliases: list[str], family: str) -> tuple[bool, bool]:
        o = text.strip().lower()
        low = [a.lower() for a in aliases]
        if family == "verify":
            first = o.split()[0].strip(".,!") if o else ""
            return first in low, first in low
        return any(o.startswith(a) for a in low), any(a in o for a in low)

    models = [("learner", learner["output_dir"])] + [(r["run"], str(Path(r["output_dir"]) / target)) for r in runs]
    rows, texts, learner_greedy = [], [], {}
    device = "cuda" if torch.cuda.is_available() else "cpu"
    for name, path in models:
        tok = AutoTokenizer.from_pretrained(path)
        model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.float32).to(device).eval()
        for i, pr in enumerate(probes):
            ids = tok(qa_prompt(pr["question"]), return_tensors="pt")["input_ids"].to(device)
            with torch.no_grad():
                g = model.generate(ids, max_new_tokens=max_new_tokens, do_sample=False,
                                   pad_token_id=tok.eos_token_id)
                torch.manual_seed(seed + i)
                smp = model.generate(ids.repeat(n_samples, 1), max_new_tokens=max_new_tokens, do_sample=True,
                                     temperature=1.0, top_k=0, top_p=1.0, pad_token_id=tok.eos_token_id)
                vals = []
                for a in pr["aliases"]:
                    qa_ids, start = encode_qa(tok, pr["question"], a, append_eos=True)
                    qa_ids = qa_ids.to(device)
                    lp = torch.log_softmax(model(input_ids=qa_ids).logits[0, start - 1:-1], -1)
                    vals.append(lp[range(qa_ids.shape[1] - start), qa_ids[0, start:]].sum())
                alias_lp = float(torch.logsumexp(torch.stack(vals), 0))
            greedy = tok.decode(g[0, ids.shape[1]:], skip_special_tokens=True).split("\n")[0].strip()
            g_ok, g_mention = correct(greedy, pr["aliases"], pr["family"])
            hits = mentions = 0
            for k, s in enumerate(smp):
                st = tok.decode(s[ids.shape[1]:], skip_special_tokens=True).split("\n")[0].strip()
                ok, mention = correct(st, pr["aliases"], pr["family"])
                hits += ok
                mentions += mention
                texts.append({"model": name, "fact": short(pr["fact"]), "family": pr["family"],
                              "question": pr["question"], "sample_idx": k, "text": st, "correct": ok,
                              "mentions_answer": mention})
            key = (pr["fact"], pr["question"])
            if name == "learner":
                learner_greedy[key] = greedy
            rows.append({
                "model": name, "fact": short(pr["fact"]), "fact_role": pr["fact_role"], "family": pr["family"],
                "question": pr["question"], "gold": pr["gold"], "aliases": " | ".join(pr["aliases"]),
                "greedy": greedy, "greedy_correct": g_ok, "greedy_mentions_answer": g_mention,
                "same_as_learner": greedy == learner_greedy.get(key),
                "sample_hit_rate": hits / n_samples, "sample_mention_rate": mentions / n_samples,
                "alias_log_prob": alias_lp})
        print(f"  samples: {name} done", flush=True)
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
    write_csv(out / "samples.csv", rows)
    write_csv(out / "sample_texts.csv", texts)


def summarise_samples(out: Path) -> None:
    """behaviour.csv: one row per (model, fact) aggregated from samples.csv / sample_texts.csv."""
    samples_path, texts_path = out / "samples.csv", out / "sample_texts.csv"
    if not samples_path.is_file():
        return
    rows = list(csv.DictReader(samples_path.open(encoding="utf-8")))
    texts = list(csv.DictReader(texts_path.open(encoding="utf-8"))) if texts_path.is_file() else []
    by_q: dict[tuple, list[str]] = {}
    for t in texts:
        by_q.setdefault((t["model"], t["fact"], t["question"]), []).append(t["text"].lower())
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["model"], r["fact"], r["fact_role"]), []).append(r)
    out_rows = []
    for (model, fact, role), rs in groups.items():
        n = len(rs)
        entity = [r for r in rs if r["family"] not in ("verify", "control")]
        runon = sum(
            r["greedy_correct"] == "True"
            and len(r["greedy"]) > max(len(a) for a in r["aliases"].split(" | ")) + 2
            for r in entity)
        # answer string present in any sampled completion (entity-answer probes only)
        leak_hits = leak_n = 0
        for r in entity:
            aliases = [a.strip().lower() for a in r["aliases"].split(" | ")]
            for txt in by_q.get((model, fact, r["question"]), []):
                leak_n += 1
                leak_hits += any(a in txt for a in aliases)
        out_rows.append({
            "model": model, "fact": fact, "fact_role": role, "n_probes": n,
            "greedy_correct": sum(r["greedy_correct"] == "True" for r in rs),
            "greedy_same_as_learner": sum(r["same_as_learner"] == "True" for r in rs),
            "greedy_correct_but_runs_on": runon,
            "sample_hit_rate": round(sum(float(r["sample_hit_rate"]) for r in rs) / n, 4),
            "entity_answer_in_samples_rate": round(leak_hits / leak_n, 4) if leak_n else "",
            "mean_alias_log_prob": round(sum(float(r["alias_log_prob"]) for r in rs) / n, 4),
        })
    write_csv(out / "behaviour.csv", out_rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config-dir", type=Path, required=True)
    ap.add_argument("--log-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--ledger", type=Path, default=Path(".factverify_internal/factverify.sqlite"))
    ap.add_argument("--skip-samples", action="store_true")
    ap.add_argument("--n-samples", type=int, default=10)
    ap.add_argument("--sample-seed", type=int, default=7)
    ap.add_argument("--max-new-tokens", type=int, default=16)
    a = ap.parse_args()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    learner, runs = load_runs(a.config_dir)
    export_results(learner, runs, ledger_rows(a.ledger), a.log_dir, a.out_dir)
    if not a.skip_samples:
        export_samples(learner, runs, a.out_dir, a.n_samples, a.sample_seed, a.max_new_tokens)
    summarise_samples(a.out_dir)


if __name__ == "__main__":
    main()
