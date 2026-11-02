"""Hanoi-is-the-capital-of-Vietnam worked example.

1. Builds a small sample dataset (entities / relations / facts / corpus) in the
   same JSON shapes as ``.factverify/`` into ``docs/examples/hanoi_capital/``.
2. Defines four synthetic forgetter outcomes (good, bad 1-3).
3. Computes drop / retention (draw.io tab ``Drop_retetion_score``,
   ``src/train/methods/unlearn_common.py``).
4. Applies the statistical tests of draw.io tab ``Experiment_Design``:
   p_forget (Crawford-Howell), p_retain (one-sample t per neighbour), AFC.

All model probabilities are ILLUSTRATIVE inputs, not outputs of a trained model.
Pure python (no numpy/scipy).  Run from the repo root:

    python scripts/hanoi_capital_example.py            # writes JSON, prints markdown
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "docs" / "examples" / "hanoi_capital"
FAMILIES = ["direct", "inverse", "cloze", "para", "verify"]
ALPHA = 0.05
KAPPA = 0.8                       # delta = 0.2
MU0 = math.log(KAPPA)             # ln 0.8 = -0.2231

# --------------------------------------------------------------------------
# 1. Sample dataset
# --------------------------------------------------------------------------
P = "factverify"
ENTITIES = {
    "vietnam":         ("Vietnam", "Việt Nam", ["Viet Nam", "Socialist Republic of Vietnam"], ["Việt Nam", "nước Việt Nam"]),
    "hanoi":           ("Hanoi", "Hà Nội", ["Ha Noi", "Hanoi city"], ["Hà Nội", "thành phố Hà Nội"]),
    "vietnamese_dong": ("Vietnamese đồng", "đồng Việt Nam", ["Vietnamese dong", "VND"], ["đồng Việt Nam", "VNĐ"]),
    "red_river":       ("Red River", "sông Hồng", ["Hong River"], ["sông Hồng", "sông Cái"]),
    "thailand":        ("Thailand", "Thái Lan", ["Kingdom of Thailand"], ["Thái Lan"]),
    "bangkok":         ("Bangkok", "Bangkok", ["Krung Thep"], ["Bangkok", "Băng Cốc"]),
    "japan":           ("Japan", "Nhật Bản", ["Nippon"], ["Nhật Bản", "nước Nhật"]),
    "tokyo":           ("Tokyo", "Tokyo", ["Tōkyō"], ["Tokyo", "Đông Kinh"]),
}
RELATIONS = {
    "capital":  (["capital", "capital city", "seat of government"], ["thủ đô", "kinh đô"]),
    "currency": (["currency", "official currency", "legal tender"], ["tiền tệ", "đơn vị tiền tệ"]),
    "located_on_river": (["located on river", "lies on", "river through"], ["nằm bên sông", "sông chảy qua"]),
}
# role: f = target, g1..g4 = neighbours of f
FACTS = {
    "f":  ("sample_0_vietnam_capital_hanoi",            "vietnam", "capital",          "hanoi",           "The capital of Vietnam is Hanoi"),
    "g1": ("sample_1_vietnam_currency_vietnamese_dong", "vietnam", "currency",         "vietnamese_dong", "The currency of Vietnam is the Vietnamese đồng"),
    "g2": ("sample_2_thailand_capital_bangkok",         "thailand", "capital",         "bangkok",         "The capital of Thailand is Bangkok"),
    "g3": ("sample_3_hanoi_located_on_red_river",       "hanoi",   "located_on_river", "red_river",       "Hanoi lies on the Red River"),
    "g4": ("sample_4_japan_capital_tokyo",              "japan",   "capital",          "tokyo",           "The capital of Japan is Tokyo"),
}
WHY = {
    "g1": "same subject (Vietnam), different relation",
    "g2": "same relation (capital), different country",
    "g3": "target's object (Hanoi) is this fact's subject",
    "g4": "same relation (capital), different country",
}
NEIGHBOURS = {  # symmetric links
    "f":  ["g1", "g2", "g3", "g4"],
    "g1": ["f"],
    "g2": ["f", "g4"],
    "g3": ["f"],
    "g4": ["f", "g2"],
}

# Templates: relation -> family -> language -> {"train": [...], "eval": [...]}
# Each template is (question, answer_slot) where answer_slot in {"o", "s", "true"}.
T = {
 "capital": {
  "direct": {"en": {"train": ["What is the capital of {s}?", "Which city is the capital of {s}?"],
                    "eval":  ["Name the capital city of {s}.", "What city serves as the capital of {s}?"]},
             "vi": {"train": ["Thủ đô của {s} là gì?", "Thành phố nào là thủ đô của {s}?"],
                    "eval":  ["Hãy cho biết thủ đô của {s}.", "Thủ đô của nước {s} là thành phố nào?"]}},
  "inverse": {"en": {"train": ["{o} is the capital of which country?", "Which country has {o} as its capital?"],
                     "eval":  ["Of which country is {o} the capital?", "Which nation's capital is {o}?"]},
              "vi": {"train": ["{o} là thủ đô của nước nào?", "Quốc gia nào có thủ đô là {o}?"],
                     "eval":  ["{o} là thủ đô của quốc gia nào?", "Nước nào đặt thủ đô tại {o}?"]}},
  "cloze": {"en": {"train": ["The capital of {s} is ___.", "___ is the capital city of {s}."],
                   "eval":  ["The seat of government of {s} is its capital, ___.", "The capital city of {s} is called ___."]},
            "vi": {"train": ["Thủ đô của {s} là ___.", "___ là thủ đô của {s}."],
                   "eval":  ["Thành phố ___ là thủ đô của {s}.", "Thủ đô của nước {s} có tên là ___."]}},
  "para": {"en": {"train": ["Where is the national government of {s} based?", "Which city is the political centre of {s}?"],
                  "eval":  ["In which city do the main state institutions of {s} sit?", "Which city is the administrative heart of {s}?"]},
           "vi": {"train": ["Chính phủ {s} đặt trụ sở tại thành phố nào?", "Trung tâm chính trị của {s} là thành phố nào?"],
                  "eval":  ["Các cơ quan nhà nước chính của {s} đặt tại đâu?", "Thành phố nào là trung tâm hành chính của {s}?"]}},
  "verify": {"en": {"train": ["True or false: {o} is the capital of {s}.", "True or false: the capital of {s} is {o}."],
                    "eval":  ["True or false: {s}'s capital city is {o}.", "{o} is the capital of {s}. True or false?"]},
             "vi": {"train": ["{o} là thủ đô của {s}. Đúng hay sai?", "Đúng hay sai: thủ đô của {s} là {o}."],
                    "eval":  ["Đúng hay sai: {o} là thủ đô của nước {s}.", "Thủ đô của {s} là {o}. Điều này đúng hay sai?"]}},
 },
 "currency": {
  "direct": {"en": {"train": ["What is the currency of {s}?", "What money is used in {s}?"],
                    "eval":  ["What is the official currency of {s}?", "Which currency do people in {s} pay with?"]},
             "vi": {"train": ["Đơn vị tiền tệ của {s} là gì?", "Người dân {s} dùng tiền gì?"],
                    "eval":  ["Tiền tệ chính thức của {s} là gì?", "Ở {s}, người ta thanh toán bằng đồng tiền nào?"]}},
  "inverse": {"en": {"train": ["The {o} is the currency of which country?", "Which country uses the {o}?"],
                     "eval":  ["In which country is the {o} the official currency?", "Which nation issues the {o}?"]},
              "vi": {"train": ["{o} là tiền tệ của nước nào?", "Quốc gia nào dùng {o}?"],
                     "eval":  ["{o} là đơn vị tiền tệ chính thức của quốc gia nào?", "Nước nào phát hành {o}?"]}},
  "cloze": {"en": {"train": ["The currency of {s} is the ___.", "In {s}, prices are quoted in ___."],
                   "eval":  ["The official currency of {s} is the ___.", "{s} uses the ___ as its national currency."]},
            "vi": {"train": ["Đơn vị tiền tệ của {s} là ___.", "Ở {s}, giá cả được tính bằng ___."],
                   "eval":  ["Tiền tệ chính thức của {s} là ___.", "{s} dùng ___ làm đồng tiền quốc gia."]}},
  "para": {"en": {"train": ["What do people in {s} use to buy things?", "Which monetary unit circulates in {s}?"],
                  "eval":  ["What is the legal tender in {s}?", "Which money would you need to pay for goods in {s}?"]},
           "vi": {"train": ["Người dân {s} dùng gì để mua bán hằng ngày?", "Đồng tiền nào lưu hành ở {s}?"],
                  "eval":  ["Đâu là phương tiện thanh toán hợp pháp ở {s}?", "Bạn cần loại tiền nào để mua hàng ở {s}?"]}},
  "verify": {"en": {"train": ["True or false: the currency of {s} is the {o}.", "True or false: the {o} is used in {s}."],
                    "eval":  ["True or false: {s} uses the {o} as its official currency.", "The {o} is the national currency of {s}. True or false?"]},
             "vi": {"train": ["Đúng hay sai: tiền tệ của {s} là {o}.", "{o} là tiền tệ của {s}. Đúng hay sai?"],
                    "eval":  ["Đúng hay sai: {s} dùng {o} làm tiền tệ chính thức.", "{o} là đồng tiền quốc gia của {s}. Điều này đúng hay sai?"]}},
 },
 "located_on_river": {
  "direct": {"en": {"train": ["Which river flows through {s}?", "On which river does {s} lie?"],
                    "eval":  ["Which river runs through the city of {s}?", "Name the river that {s} is built on."]},
             "vi": {"train": ["Sông nào chảy qua {s}?", "{s} nằm bên sông nào?"],
                    "eval":  ["Con sông nào chảy qua thành phố {s}?", "Hãy kể tên con sông mà {s} nằm bên bờ."]}},
  "inverse": {"en": {"train": ["Which capital city lies on the {o}?", "The {o} flows through which capital city?"],
                     "eval":  ["Which capital city is built along the {o}?", "Name the capital city located on the {o}."]},
              "vi": {"train": ["Thủ đô nào nằm bên {o}?", "{o} chảy qua thủ đô nào?"],
                     "eval":  ["Thủ đô nào được xây dựng dọc theo {o}?", "Hãy kể tên thủ đô nằm bên {o}."]}},
  "cloze": {"en": {"train": ["{s} lies on the ___.", "The ___ flows through {s}."],
                   "eval":  ["The city of {s} was built on the banks of the ___.", "{s} sits along the ___."]},
            "vi": {"train": ["{s} nằm bên ___.", "___ chảy qua {s}."],
                   "eval":  ["Thành phố {s} được xây dựng bên bờ ___.", "{s} nằm dọc theo ___."]}},
  "para": {"en": {"train": ["Which waterway passes through {s}?", "What river do you cross when travelling through {s}?"],
                  "eval":  ["Which major waterway runs past {s}?", "Along which river did {s} develop?"]},
           "vi": {"train": ["Dòng sông nào đi qua {s}?", "Khi đi qua {s}, bạn sẽ băng qua con sông nào?"],
                  "eval":  ["Tuyến đường thủy lớn nào chảy ngang {s}?", "{s} phát triển dọc theo con sông nào?"]}},
  "verify": {"en": {"train": ["True or false: {s} lies on the {o}.", "True or false: the {o} flows through {s}."],
                    "eval":  ["True or false: the {o} runs through {s}.", "{s} is located on the {o}. True or false?"]},
             "vi": {"train": ["Đúng hay sai: {s} nằm bên {o}.", "{o} chảy qua {s}. Đúng hay sai?"],
                    "eval":  ["Đúng hay sai: {o} chảy qua {s}.", "{s} nằm bên {o}. Điều này đúng hay sai?"]}},
 },
}
ANSWER_OF = {"direct": "o", "inverse": "s", "cloze": "o", "para": "o", "verify": "true"}


def eid(k): return f"{P}:entity:{k}"
def rid(k): return f"{P}:relation:{k}"
def fid(k): return f"{P}:fact:{FACTS[k][0]}"
def cid(k): return f"{P}:corpus:{FACTS[k][0]}"


def label(ent, lang):
    en, vi, *_ = ENTITIES[ent]
    return en if lang == "en" else vi


def build_dataset() -> dict:
    for sub in ("entities", "relations", "facts", "corpus"):
        (ROOT / sub).mkdir(parents=True, exist_ok=True)
    for k, (en, vi, en_al, vi_al) in ENTITIES.items():
        doc = {"id": eid(k), "label": en, "description": "",
               "alias": [{"value": v, "language": "en"} for v in [en, *en_al]] +
                        [{"value": v, "language": "vi"} for v in vi_al]}
        (ROOT / "entities" / f"{k}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    for k, (en_al, vi_al) in RELATIONS.items():
        doc = {"id": rid(k), "label": k, "description": "",
               "alias": [{"value": v, "language": "en"} for v in en_al] +
                        [{"value": v, "language": "vi"} for v in vi_al]}
        (ROOT / "relations" / f"{k}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    counts = {}
    for k, (slug, s, r, o, desc) in FACTS.items():
        fact = {"id": fid(k), "type": r,
                "atomic_fact": {"subject": {"id": eid(s), "label": ENTITIES[s][0]},
                                "relation": {"id": rid(r), "label": r},
                                "object": {"id": eid(o), "label": ENTITIES[o][0]}},
                "description": desc, "corpus": cid(k),
                "neighbourhoods": [fid(n) for n in NEIGHBOURS[k]],
                "source": {"candidate_id": slug, "source_row": None, "provenance": "hand_written_sample",
                           "review_model": "", "review_reason": "Illustrative sample for the drop/retention + AFC walkthrough."}}
        (ROOT / "facts" / f"{slug}.json").write_text(json.dumps(fact, ensure_ascii=False, indent=2) + "\n")
        corpus = {"id": cid(k), "corpus_metadata": {"equivalent_closure": []}, "train": [], "eval": []}
        for split in ("train", "eval"):
            n = 0
            for fam in FAMILIES:
                for lang in ("en", "vi"):
                    for q in T[r][fam][lang][split]:
                        n += 1
                        slot = ANSWER_OF[fam]
                        if slot == "true":
                            a, at, aid = ("True" if lang == "en" else "Đúng"), "truth_label", ""
                        else:
                            ent = o if slot == "o" else s
                            a, at, aid = label(ent, lang), "entity", eid(ent)
                        corpus[split].append({"_id": n, "Q": q.format(s=label(s, lang), o=label(o, lang)), "A": a,
                                              "ec": fam, "language": lang, "answer_type": at, "answer_factverify_id": aid})
        for fam in sorted(FAMILIES):
            for lang in ("en", "vi"):
                corpus["corpus_metadata"]["equivalent_closure"].append(
                    {"ec": fam, "language": lang,
                     "num_train": len(T[r][fam][lang]["train"]), "num_eval": len(T[r][fam][lang]["eval"])})
        (ROOT / "corpus" / f"{slug}.json").write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n")
        counts[k] = (len(corpus["train"]), len(corpus["eval"]))
    return counts


# --------------------------------------------------------------------------
# 2. Four forgetter cases (family-group probabilities P̄, illustrative)
#    order: direct, inverse, cloze, para, verify
# --------------------------------------------------------------------------
LEARNER = {
    "f":  [0.92, 0.85, 0.90, 0.88, 0.97],
    "g1": [0.86, 0.70, 0.84, 0.80, 0.95],
    "g2": [0.93, 0.87, 0.91, 0.89, 0.97],
    "g3": [0.80, 0.62, 0.78, 0.74, 0.94],
    "g4": [0.95, 0.90, 0.93, 0.91, 0.98],
}
F_TARGET_FORGOTTEN = [0.015, 0.030, 0.020, 0.025, 0.060]
NB_KEPT = {
    "g1": [0.80, 0.65, 0.79, 0.74, 0.93],
    "g2": [0.92, 0.86, 0.90, 0.88, 0.97],
    "g3": [0.72, 0.56, 0.71, 0.67, 0.92],
    "g4": [0.94, 0.89, 0.92, 0.90, 0.98],
}
NB_DAMAGED = {
    "g1": [0.30, 0.22, 0.28, 0.25, 0.60],
    "g2": [0.55, 0.48, 0.52, 0.50, 0.80],
    "g3": [0.20, 0.15, 0.18, 0.17, 0.50],
    "g4": [0.60, 0.52, 0.58, 0.55, 0.85],
}
CASES = {
    "good": ("Good forgetter", "forgets the target, keeps every neighbour",
             {"f": F_TARGET_FORGOTTEN, **NB_KEPT}),
    "bad1": ("Bad forgetter 1", "forgets the target, but also damages the neighbours",
             {"f": F_TARGET_FORGOTTEN, **NB_DAMAGED}),
    "bad2": ("Bad forgetter 2", "fails to forget the target; neighbours untouched (no-op)",
             {"f": [0.88, 0.81, 0.86, 0.84, 0.96], **NB_KEPT}),
    "bad3": ("Bad forgetter 3", "fails to forget the target, but damages the neighbours",
             {"f": [0.87, 0.80, 0.85, 0.83, 0.96], **NB_DAMAGED}),
}
# Extra sensitivity case: target forgotten, neighbours damaged about as much as the target
BROAD = {"f": F_TARGET_FORGOTTEN,
         "g1": [0.03, 0.02, 0.03, 0.03, 0.10], "g2": [0.04, 0.03, 0.04, 0.04, 0.12],
         "g3": [0.02, 0.02, 0.02, 0.02, 0.08], "g4": [0.05, 0.04, 0.05, 0.04, 0.15]}


# --------------------------------------------------------------------------
# 3. Student-t upper tail (pure python): sf(t, df) = P[T_df >= t]
# --------------------------------------------------------------------------
def _betacf(a, b, x):
    tiny, eps = 1e-300, 3e-16
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c; c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c; c = c if abs(c) > tiny else tiny
        de = d * c; h *= de
        if abs(de - 1) < eps:
            break
    return h


def _betainc(a, b, x):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1 - math.exp(lbt) * _betacf(b, a, 1 - x) / b


def t_sf(t, df):
    if math.isinf(t):
        return 0.0 if t > 0 else 1.0
    tail = 0.5 * _betainc(df / 2, 0.5, df / (df + t * t))
    return tail if t >= 0 else 1 - tail


# sanity: one-sided 5% critical values
assert abs(t_sf(1.729133, 19) - 0.05) < 1e-5 and abs(t_sf(2.131847, 4) - 0.05) < 1e-5


# --------------------------------------------------------------------------
# 4. Scores and tests
# --------------------------------------------------------------------------
def fam_drops(learner, forgetter):
    return [math.log(l) - math.log(f) for l, f in zip(learner, forgetter)]


def mean(xs): return sum(xs) / len(xs)
def sd(xs):
    m = mean(xs); return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def evaluate(forg):
    d_f = fam_drops(LEARNER["f"], forg["f"])
    d_g = {g: fam_drops(LEARNER[g], forg[g]) for g in ("g1", "g2", "g3", "g4")}
    # ---- p_forget (Crawford-Howell) ----
    t_f = min(d_f)
    t_fam = FAMILIES[d_f.index(t_f)]
    pool = [x for g in d_g for x in d_g[g]]
    n = len(pool)
    m, s = mean(pool), sd(pool)
    T_forget = (t_f - m) / (s * math.sqrt(1 + 1 / n))
    p_forget = t_sf(T_forget, n - 1)
    # ---- p_retain (one-sample t per neighbour) ----
    retain = {}
    for g, drops in d_g.items():
        y = [-x for x in drops]                      # ln r per family
        yb, sj = mean(y), sd(y)
        se = sj / math.sqrt(len(y))
        T = (yb - MU0) / se if se > 0 else (math.inf if yb > MU0 else -math.inf)
        retain[g] = {"y": y, "ybar": yb, "s": sj, "se": se, "T": T, "p": t_sf(T, len(y) - 1)}
    p_retain = max(r["p"] for r in retain.values())
    worst = max(retain, key=lambda g: retain[g]["p"])
    p_afc = max(p_forget, p_retain)
    return {"d_f": d_f, "d_g": d_g, "t_f": t_f, "t_fam": t_fam, "n": n, "m": m, "s": s,
            "T_forget": T_forget, "p_forget": p_forget, "retain": retain, "p_retain": p_retain,
            "worst": worst, "p_afc": p_afc}


def row_of(r):
    fo, re = r["p_forget"] <= ALPHA, r["p_retain"] <= ALPHA
    return {(True, True): (1, "Certified"),
            (False, True): (2, "Not certified: not forgotten"),
            (True, False): (3, "Not certified: collateral damage"),
            (False, False): (4, "Not certified: both failed")}[(fo, re)]


def p_fmt(p):
    return f"{p:.2e}" if p < 1e-3 else f"{p:.4f}"


def md_case(key, title, desc, forg):
    r = evaluate(forg)
    L = []
    L.append(f"### {title}: {desc}\n")
    L.append("**Step A: Probabilities and drop / retention per family group** (P̄_L → P̄_F; d̄ = ln P̄_L − ln P̄_F; r̄ = P̄_F / P̄_L)\n")
    L.append("| fact | role | " + " | ".join(FAMILIES) + " | fact d̄ | fact r̄ |")
    L.append("|---|---|" + "---:|" * 5 + "---:|---:|")
    for k in ("f", "g1", "g2", "g3", "g4"):
        d = fam_drops(LEARNER[k], forg[k])
        cells = [f"{LEARNER[k][i]:.2f}→{forg[k][i]:.3g}<br>d̄={d[i]:.3f}, r̄={math.exp(-d[i]):.3f}" for i in range(5)]
        fd = mean(d)
        L.append(f"| {k} | {'target' if k == 'f' else 'neighbour'} | " + " | ".join(cells) + f" | {fd:.3f} | {math.exp(-fd):.3f} |")
    L.append("")
    L.append("**Step B: p_forget (Crawford–Howell)**\n")
    L.append(f"- t_f = min_φ d̄_f^φ = **{r['t_f']:.4f}** (family: {r['t_fam']})")
    L.append(f"- Background over n = {r['n']} neighbour family drops: m = {r['m']:.4f}, s = {r['s']:.4f}")
    L.append(f"- T_forget = ({r['t_f']:.4f} − {r['m']:.4f}) / ({r['s']:.4f} × √(1 + 1/{r['n']})) = **{r['T_forget']:.3f}**")
    L.append(f"- p_forget = P[T_{r['n']-1} ≥ {r['T_forget']:.3f}] = **{p_fmt(r['p_forget'])}** → "
             f"{'reject H₀ (target forgotten beyond background)' if r['p_forget'] <= ALPHA else 'fail to reject H₀ (targeted forgetting not shown)'}\n")
    L.append(f"**Step C: p_retain (one-sample t per neighbour, μ₀ = ln κ = {MU0:.4f}, df = 4)**\n")
    L.append("| g_j | ln r̄ per family (dir / inv / clo / para / ver) | ȳ_j | e^ȳ_j | s_j | SE_j | T_retain,j | p_retain,j |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for g, rr in r["retain"].items():
        L.append(f"| {g} | " + " / ".join(f"{v:.3f}" for v in rr["y"]) +
                 f" | {rr['ybar']:.4f} | {math.exp(rr['ybar']):.3f} | {rr['s']:.4f} | {rr['se']:.4f} | {rr['T']:.3f} | {p_fmt(rr['p'])} |")
    L.append("")
    L.append(f"- p_retain = max_j p_retain,j = **{p_fmt(r['p_retain'])}** (worst neighbour: {r['worst']}) → "
             f"{'reject H₀ (every neighbour keeps > 80%)' if r['p_retain'] <= ALPHA else 'fail to reject H₀ (retention not shown)'}\n")
    row, verdict = row_of(r)
    L.append("**Step D: AFC**\n")
    L.append(f"- p_AFC = max({p_fmt(r['p_forget'])}, {p_fmt(r['p_retain'])}) = **{p_fmt(r['p_afc'])}**")
    L.append(f"- **Verdict: {verdict}** (row {row} of the Experiment_Design decision table)\n")
    return "\n".join(L), r


def summary(results):
    L = ["| Case | t_f (family) | m | T_forget | p_forget | worst g_j | p_retain | p_AFC | Row | Verdict |",
         "|---|---|---:|---:|---:|---|---:|---:|:---:|---|"]
    for key, (title, _desc, _f) in list(CASES.items()) + [("broad", ("Variant 1b (broad damage)", "", None))]:
        r = results[key]
        row, verdict = row_of(r)
        L.append(f"| {title} | {r['t_f']:.3f} ({r['t_fam']}) | {r['m']:.3f} | {r['T_forget']:.2f} | {p_fmt(r['p_forget'])} | "
                 f"{r['worst']} | {p_fmt(r['p_retain'])} | {p_fmt(r['p_afc'])} | {row} | {verdict} |")
    return "\n".join(L)


LEVEL12_PROBES = [
    ("Name the capital city of Vietnam.", "Hanoi", "en"),
    ("What city serves as the capital of Vietnam?", "Hanoi", "en"),
    ("Hãy cho biết thủ đô của Việt Nam.", "Hà Nội", "vi"),
    ("Thủ đô của nước Việt Nam là thành phố nào?", "Hà Nội", "vi"),
]
# Illustrative per-token probabilities of the gold answer (2 tokens each), per model.
LEVEL12_TOKENS = {
    "L":    [[0.97, 0.969], [0.96, 0.969], [0.95, 0.958], [0.94, 0.957]],
    "good": [[0.20, 0.10], [0.15, 0.10], [0.12, 0.10], [0.14, 0.10]],
    "bad1": [[0.20, 0.10], [0.15, 0.10], [0.12, 0.10], [0.14, 0.10]],
    "bad2": [[0.93, 0.968], [0.92, 0.967], [0.91, 0.956], [0.90, 0.956]],
    "bad3": [[0.92, 0.967], [0.91, 0.967], [0.90, 0.956], [0.89, 0.955]],
}


def level12(model):
    probs = [math.prod(t) for t in LEVEL12_TOKENS[model]]
    logs = [math.log(x) for x in probs]
    return probs, logs, mean(logs), math.exp(mean(logs))


def worked_level12():
    """Levels 1-2 for the target's direct family, learner + all four forgetters."""
    names = {"L": "Learner L", "good": "Good forgetter", "bad1": "Bad forgetter 1",
             "bad2": "Bad forgetter 2", "bad3": "Bad forgetter 3"}
    out = []
    _, _, ml, pl = level12("L")
    for model in ("L", "good", "bad1", "bad2", "bad3"):
        probs, logs, m, pbar = level12(model)
        out.append(f"#### {names[model]}\n")
        out.append("| # | probe q | gold a | tokens P(a_t) | P(a\\|q) | ln P(a\\|q) |")
        out.append("|---|---|---|---|---:|---:|")
        for i, ((q, a, _lang), t) in enumerate(zip(LEVEL12_PROBES, LEVEL12_TOKENS[model]), 1):
            out.append(f"| {i} | {q} | {a} | {' × '.join(f'{x:g}' for x in t)} | {probs[i-1]:.4f} | {logs[i-1]:.4f} |")
        out.append("")
        out.append(f"- mean ln P = ({' + '.join(f'({x:.4f})' for x in logs)}) / 4 = **{m:.4f}**")
        out.append(f"- P̄ = e^({m:.4f}) = **{pbar:.4f}**")
        if model != "L":
            d = ml - m
            out.append(f"- drop d̄ = ln P̄_L − ln P̄_F = {ml:.4f} − ({m:.4f}) = **{d:.4f}**")
            out.append(f"- retention r̄ = P̄_F / P̄_L = {pbar:.4f} / {pl:.4f} = **{pbar/pl:.4f}** (= e^(−{d:.4f}))")
        out.append("")
    out.append("#### Summary (target f, direct family)\n")
    out.append("| Model | P̄ (direct) | drop d̄ | retention r̄ | Reading |")
    out.append("|---|---:|---:|---:|---|")
    out.append(f"| Learner L | {pl:.4f} | 0 | 1 | baseline: the learner knows Hanoi |")
    reading = {"good": "Hanoi forgotten (1.6% kept)", "bad1": "Hanoi forgotten (1.6% kept)",
               "bad2": "Hanoi still known (~96% kept)", "bad3": "Hanoi still known (~95% kept)"}
    for model in ("good", "bad1", "bad2", "bad3"):
        _, _, m, pbar = level12(model)
        out.append(f"| {names[model]} | {pbar:.4f} | {ml - m:.4f} | {pbar/pl:.4f} | {reading[model]} |")
    return "\n".join(out)


if __name__ == "__main__":
    counts = build_dataset()
    results = {k: evaluate(f) for k, (_t, _d, f) in CASES.items()}
    results["broad"] = evaluate(BROAD)
    print("<!-- COUNTS -->")
    for k, (tr, ev) in counts.items():
        print(f"{k}: train={tr} eval={ev}")
    print("<!-- LEVEL12 -->")
    print(worked_level12())
    print("<!-- SUMMARY -->")
    print(summary(results))
    print("<!-- CASES -->")
    for k, (t, d, f) in CASES.items():
        print(md_case(k, t, d, f)[0])
    print("<!-- BROAD -->")
    print(md_case("broad", "Variant 1b (broad damage)", "forgets the target, damages neighbours almost as much", BROAD)[0])
