"""Benchmark: how does each setting at the top of matcher.py change the quality of the results?

Run it with:     python benchmark.py            (full run, a few minutes)
         or:     python benchmark.py --quick    (fewer test passages, faster, rougher numbers)

It writes two files:
    benchmark_report.html   - open it in your browser: charts + explanations
    benchmark_results.csv   - all the numbers, e.g. for Excel

Uses only the Python standard library (nothing to install).

HOW QUALITY IS MEASURED - two tests:

1. Test set with planted passages (exact answers known).
   We take a real Gospel as text A. We build a text B out of shuffled 2-5 word scraps of a
   different Gospel (realistic words, but no real shared passages), and copy ("plant") passages
   from A into B. Some are copied exactly, others with 10-40% of the words changed, deleted or
   added. Because we planted them, we know exactly where every true parallel is, so we can count:
     precision = of the parallels the program reports, how many are real (planted)?
     recall    = of the planted parallels, how many did the program find?
     F1        = one number combining both (high only if both are high)
     boundary fit = how well the reported start/end match the planted start/end (1 = perfect)

2. The real Gospels with a list of known parallels (gold_parallels.csv, made from Kurt Aland's
   Synopsis by gold/make_gold.py). We count how many of these known parallels are found.
   Some of them are the same story told in quite different words, which no word-matching program
   can find, so 100% is not expected. Use it to compare settings with each other.

Each setting is changed on its own, with all other settings at their current values.
"""
import csv
import json
import random
import sys
import time
from contextlib import contextmanager
from itertools import combinations
from pathlib import Path

import matcher

FOLDER = Path(__file__).parent
CORPUS = FOLDER / "corpus"
GOLD_FILE = FOLDER / "gold_parallels.csv"
BOOK_ORDER = ["matthew", "mark", "luke", "john"]

# The values to try for every setting
SWEEPS = {
    "SEED_SIZE": [2, 3, 4, 5, 6, 7, 8],
    "MAX_GAP": [1, 3, 5, 10, 15, 20, 30, 40, 60],
    "MIN_WORDS": [4, 6, 8, 10, 12, 15, 20, 30],
    "MIN_SCORE": [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    "MAX_COMMON": [1, 2, 5, 10, 25, 50, 100, 1000],
}
# The two settings that work together most closely; we also try every combination of them
GRID = ("SEED_SIZE", "MAX_GAP")

EXPLAIN = {
    "SEED_SIZE": "How many words in a row must be exactly the same before the program looks closer. "
                 "A smaller number finds more, but also more false matches. A bigger number gives fewer false "
                 "matches, but misses passages where the wording changes every few words.",
    "MAX_GAP": "How many words may lie between two matching bits for them to still count as one passage. "
               "Too small: an edited passage gets chopped into small pieces. Too big: two separate passages "
               "that happen to be close get glued together into one.",
    "MIN_WORDS": "The shortest match, in words, that the program will report. Smaller: lots of tiny matches "
                 "such as common phrases. Bigger: only long passages, so short real parallels are lost.",
    "MIN_SCORE": "How similar two passages must be (0% to 100%) to be reported. Higher: only near-identical "
                 "copies. Lower: heavily changed passages are kept too, but also more doubtful ones.",
    "MAX_COMMON": "Very common phrases (like \"and he said unto them\") are not used as starting points if they "
                  "appear more often than this. Smaller: more phrases ignored, less noise, but some real "
                  "passages are missed. Bigger: more phrases used, more noise.",
}

EDIT_RATES = [0.0, 0.1, 0.2, 0.3, 0.4]  # share of words changed in the planted copies
PASSAGE_LENGTH = (12, 60)                # planted passages are 12-60 words long


# ---------------------------------------------------------------- helpers

@contextmanager
def settings(**changes):
    """Temporarily change settings in matcher.py, then put the old values back."""
    old = {name: getattr(matcher, name) for name in changes}
    for name, value in changes.items():
        setattr(matcher, name, value)
    try:
        yield
    finally:
        for name, value in old.items():
            setattr(matcher, name, value)


def overlap(start1, end1, start2, end2):
    """How many characters two ranges have in common."""
    return max(0, min(end1, end2) - max(start1, start2))


def load_books():
    """Read the corpus files, in the usual book order."""
    files = {p.stem: p for p in CORPUS.glob("*.txt")}
    names = [n for n in BOOK_ORDER if n in files] + sorted(n for n in files if n not in BOOK_ORDER)
    return {name: files[name].read_text(encoding="utf-8") for name in names}


# ---------------------------------------------------------------- test 1: planted passages

def change_words(words, rate, vocabulary, rng):
    """Change about `rate` of the words: replace, delete, or add a word."""
    result = []
    for word in words:
        if rng.random() < rate:
            action = rng.choice(["replace", "delete", "add"])
            if action == "replace":
                result.append(rng.choice(vocabulary))
            elif action == "add":
                result += [word, rng.choice(vocabulary)]
            # "delete": the word is simply not added
        else:
            result.append(word)
    return result or words[:1]


def make_test_case(text_a, filler_text, per_rate, rng):
    """Build text B = shuffled scraps of filler_text + passages copied from text_a.
    Returns text B and the list of planted passages (their true positions in A and B)."""
    tokens_a = matcher.get_words(text_a)
    vocabulary = [w for w, _, _ in matcher.get_words(filler_text)]

    # 1. choose passages in A that don't overlap
    slot = PASSAGE_LENGTH[1] + 20
    starts = list(range(0, len(tokens_a) - slot, slot))
    count = min(per_rate * len(EDIT_RATES), len(starts))
    rates = [EDIT_RATES[k % len(EDIT_RATES)] for k in range(count)]
    rng.shuffle(rates)
    planted = []
    for start, rate in zip(sorted(rng.sample(starts, count)), rates):
        length = rng.randint(*PASSAGE_LENGTH)
        last = start + length - 1
        words = [tokens_a[k][0] for k in range(start, last + 1)]
        planted.append({"a_start": tokens_a[start][1], "a_end": tokens_a[last][2], "rate": rate,
                        "words": change_words(words, rate, vocabulary, rng)})

    # 2. background: the filler text cut into scraps of 2-5 words and shuffled
    scraps, i = [], 0
    while i < len(vocabulary) and i < len(tokens_a):
        size = rng.randint(2, 5)
        scraps.append(vocabulary[i:i + size])
        i += size
    rng.shuffle(scraps)

    # 3. put the planted passages between scraps, in a random order, and remember where they are
    order = planted[:]
    rng.shuffle(order)
    order = order[:len(scraps) + 1]  # (only matters for very short texts)
    planted = [p for p in planted if p in order]
    insert_at = dict(zip(sorted(rng.sample(range(len(scraps) + 1), len(order))), order))
    pieces, position = [], 0
    for k in range(len(scraps) + 1):
        if k in insert_at:
            p = insert_at[k]
            text = " ".join(p["words"])
            p["b_start"], p["b_end"] = position, position + len(text)
            pieces.append(text)
            position += len(text) + 1
        if k < len(scraps):
            text = " ".join(scraps[k])
            pieces.append(text)
            position += len(text) + 1
    return " ".join(pieces), planted


def build_test_set(books, per_rate, trials):
    """A few test cases, each using a different Gospel as text A. Built once and reused."""
    rng = random.Random(42)  # fixed, so every run of the benchmark uses the same test set
    names = list(books)
    cases = []
    for t in range(trials):
        a_name, filler_name = names[t % len(names)], names[(t + 1) % len(names)]
        text_b, planted = make_test_case(books[a_name], books[filler_name], per_rate, rng)
        if planted:
            cases.append({"a": books[a_name], "b": text_b, "planted": planted})
    return cases


def score_test_set(cases):
    """Run the matcher on every test case and compare with the planted answers."""
    reported = correct = 0
    found_by_rate = {r: [0, 0] for r in EDIT_RATES}  # rate -> [found, total]
    fits = []
    for case in cases:
        matches = matcher.find_parallels(case["a"], case["b"])
        reported += len(matches)
        for m in matches:
            if any(overlap(m["a_start"], m["a_end"], g["a_start"], g["a_end"]) and
                   overlap(m["b_start"], m["b_end"], g["b_start"], g["b_end"]) for g in case["planted"]):
                correct += 1
        for g in case["planted"]:
            found_by_rate[g["rate"]][1] += 1
            best_fit = 0
            for m in matches:
                oa = overlap(m["a_start"], m["a_end"], g["a_start"], g["a_end"])
                ob = overlap(m["b_start"], m["b_end"], g["b_start"], g["b_end"])
                if oa and ob:
                    # boundary fit = shared part / combined part (1 = identical start and end)
                    fit_a = oa / (max(m["a_end"], g["a_end"]) - min(m["a_start"], g["a_start"]))
                    fit_b = ob / (max(m["b_end"], g["b_end"]) - min(m["b_start"], g["b_start"]))
                    best_fit = max(best_fit, (fit_a + fit_b) / 2)
            if best_fit:
                found_by_rate[g["rate"]][0] += 1
                fits.append(best_fit)
    total = sum(t for _, t in found_by_rate.values())
    found = sum(f for f, _ in found_by_rate.values())
    precision = correct / reported if reported else 1.0
    recall = found / total if total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision, "recall": recall, "f1": f1,
        "boundary_fit": sum(fits) / len(fits) if fits else 0.0,
        "reported": reported,
        **{f"found_{int(r * 100)}pct_edits": (f / t if t else 0.0) for r, (f, t) in found_by_rate.items()},
    }


# ---------------------------------------------------------------- test 2: real Gospels + known parallels

def verse_positions(text):
    """'3:1' -> (start, end) character positions of that verse's line."""
    positions, pos = {}, 0
    for line in text.split("\n"):
        positions[line.split(" ", 1)[0]] = (pos, pos + len(line))
        pos += len(line) + 1
    return positions


def load_gold(books):
    """Known parallels as pairs of books, each with a list of (start, end) character ranges.
    A story may list several ranges for one book. Verses that are not in the corpus are skipped."""
    if not GOLD_FILE.exists():
        return [], 0
    verses = {name: verse_positions(text) for name, text in books.items()}
    stories, skipped = {}, 0
    with GOLD_FILE.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            book = row["book"].strip().lower()
            first, last = row["first_verse"].strip(), row["last_verse"].strip()
            if book not in verses or first not in verses[book] or last not in verses[book]:
                skipped += 1
                continue
            ranges = stories.setdefault(row["story"], {}).setdefault(book, [])
            ranges.append((verses[book][first][0], verses[book][last][1]))
    order = list(books)
    pairs, seen = [], set()
    for story, by_book in stories.items():
        for x, y in combinations(sorted(by_book, key=order.index), 2):
            key = (x, y, tuple(sorted(by_book[x])), tuple(sorted(by_book[y])))
            if key not in seen:  # the same pair of passages listed under two stories counts once
                seen.add(key)
                pairs.append({"story": story, "x": x, "y": y, "x_ranges": by_book[x], "y_ranges": by_book[y]})
    return pairs, skipped


def score_real(books, gold):
    """Run the matcher on the real texts and compare with the known parallels.
    Only book pairs that appear in the gold list are counted (e.g. no John if the list has no John)."""
    gold_books = {g["x"] for g in gold} | {g["y"] for g in gold}
    found, reported, inside = set(), 0, 0
    for x, y in combinations(books, 2):
        if x not in gold_books or y not in gold_books:
            continue
        matches = matcher.find_parallels(books[x], books[y])
        reported += len(matches)
        gold_here = [(k, g) for k, g in enumerate(gold) if g["x"] == x and g["y"] == y]
        for m in matches:
            hit = False
            for k, g in gold_here:
                if (any(overlap(m["a_start"], m["a_end"], *r) for r in g["x_ranges"]) and
                        any(overlap(m["b_start"], m["b_end"], *r) for r in g["y_ranges"])):
                    found.add(k)
                    hit = True
            inside += hit
    return {
        "known_found": len(found) / len(gold) if gold else 0.0,
        "real_reported": reported,
        "real_inside_known": inside / reported if reported else 0.0,
    }


# ---------------------------------------------------------------- running everything

def run_one(cases, books, gold, **values):
    with settings(**values):
        started = time.perf_counter()
        result = score_test_set(cases)
        if gold:
            result.update(score_real(books, gold))
        result["seconds"] = time.perf_counter() - started
    return result


def main():
    quick = "--quick" in sys.argv
    books = load_books()
    if len(books) < 2:
        sys.exit("Put at least two texts in the corpus folder first (run: python get_texts.py).")
    cases = build_test_set(books, per_rate=8 if quick else 20, trials=2 if quick else 4)
    if not cases:
        sys.exit("The texts are too short to build the test set.")
    gold, skipped = load_gold(books)
    current = {name: getattr(matcher, name) for name in SWEEPS}

    planted = sum(len(c["planted"]) for c in cases)
    print(f"Test set: {planted} planted passages in {len(cases)} test texts.")
    print(f"Known parallels: {len(gold)} pairs from gold_parallels.csv"
          + (f" ({skipped} rows skipped: verse not in corpus)" if skipped else ""))
    print("Current settings:", ", ".join(f"{k}={v}" for k, v in current.items()))

    rows = []
    for name, values in SWEEPS.items():
        for value in values:
            r = run_one(cases, books, gold, **{name: value})
            rows.append({"parameter": name, "value": value, "is_current": value == current[name], **r})
            print(f"  {name:<10} = {value:<6}  F1 {r['f1']:.2f}  precision {r['precision']:.2f}  "
                  f"recall {r['recall']:.2f}  ({r['seconds']:.1f}s)")

    grid = []
    print(f"Trying every combination of {GRID[0]} and {GRID[1]} ...")
    for v1 in SWEEPS[GRID[0]]:
        for v2 in SWEEPS[GRID[1]]:
            with settings(**{GRID[0]: v1, GRID[1]: v2}):
                r = score_test_set(cases)
            grid.append({GRID[0]: v1, GRID[1]: v2, "f1": r["f1"], "precision": r["precision"], "recall": r["recall"]})

    with (FOLDER / "benchmark_results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    data = {
        "sweeps": SWEEPS, "current": current, "explain": EXPLAIN, "rows": rows, "grid": grid,
        "gridParams": GRID, "editRates": EDIT_RATES, "hasGold": bool(gold),
        "info": {"planted": planted, "cases": len(cases), "gold": len(gold), "quick": quick,
                 "books": list(books), "created": time.strftime("%Y-%m-%d %H:%M")},
    }
    html = REPORT_TEMPLATE.replace("/*DATA*/null", json.dumps(data))
    (FOLDER / "benchmark_report.html").write_text(html, encoding="utf-8")
    print("\nDone. Open benchmark_report.html in your browser (numbers are in benchmark_results.csv).")


# ---------------------------------------------------------------- the report page (HTML + JavaScript)

REPORT_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Settings Benchmark</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
  --o1: #86b6ef; --o2: #5598e7; --o3: #2a78d6; --o4: #1c5cab; --o5: #104281;
  --seq-low: #cde2fb; --seq-high: #0d366b;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --s1: #3987e5; --s2: #d95926; --s3: #199e70;
    --o1: #184f95; --o2: #256abf; --o3: #3987e5; --o4: #6da7ec; --o5: #b7d3f6;
    --seq-low: #184f95; --seq-high: #cde2fb;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --s1: #3987e5; --s2: #d95926; --s3: #199e70;
  --o1: #184f95; --o2: #256abf; --o3: #3987e5; --o4: #6da7ec; --o5: #b7d3f6;
  --seq-low: #184f95; --seq-high: #cde2fb;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
       font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height: 1.5; }
main { max-width: 1180px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 20px; margin: 40px 0 4px; }
h3 { font-size: 14px; margin: 0 0 2px; font-weight: 600; }
p { margin: 0 0 10px; max-width: 78ch; }
.sub { color: var(--ink-2); }
.small { font-size: 13px; color: var(--ink-2); }
code { font-family: ui-monospace, Consolas, monospace; font-size: 0.92em; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.grid2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }
@media (max-width: 760px) { .grid2 { grid-template-columns: 1fr; } }
.chart { position: relative; }
.chart svg { width: 100%; height: auto; display: block; overflow: visible; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--ink-2); margin: 4px 0 2px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend i { display: inline-block; width: 14px; height: 2px; border-radius: 1px; }
.tip { position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--border);
       border-radius: 8px; padding: 8px 10px; font-size: 12px; box-shadow: 0 4px 16px rgba(0,0,0,.12);
       min-width: 150px; z-index: 5; display: none; }
.tip .head { color: var(--ink-2); margin-bottom: 4px; }
.tip .row { display: flex; align-items: center; gap: 8px; }
.tip .row b { font-variant-numeric: tabular-nums; min-width: 42px; }
.tip .row i { display: inline-block; width: 12px; height: 2px; }
.tip .row span { color: var(--ink-2); }
table { border-collapse: collapse; width: 100%; font-size: 13px; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--grid); }
th { color: var(--ink-2); font-weight: 600; }
tr.current td { font-weight: 600; }
details { margin-top: 10px; }
summary { cursor: pointer; color: var(--ink-2); font-size: 13px; }
.takeaway { background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--s1);
            border-radius: 8px; padding: 8px 12px; margin: 8px 0 0; max-width: none; }
.table-wrap { overflow-x: auto; }
.scale { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--ink-2); margin-top: 6px; }
.scale .bar { width: 160px; height: 8px; border-radius: 4px; }
</style>
</head>
<body>
<main>
  <h1>Which settings work best? A test of the parallel finder</h1>
  <p class="sub">This page tests the five settings at the top of <code>matcher.py</code>. For each setting, several
  values were tried, and for each value we measured how well the program finds parallels.</p>
  <p class="small" id="intro"></p>

  <div class="card" style="margin-top:16px">
    <h3>The two tests</h3>
    <p class="small"><b>1. The practice test.</b> We hid passages copied from one Gospel inside a jumbled-up text.
    Some are exact copies, others have 10&ndash;40% of their words changed. Because we hid them ourselves, we know
    every right answer, so we can grade the program exactly.</p>
    <p class="small" id="realtest"></p>

    <h3 style="margin-top:12px">What the scores mean</h3>
    <p class="small">Imagine looking for 100 coins hidden on a beach with a metal detector.</p>
    <p class="small"><b>Precision (correct):</b> of everything you dug up, how much was really a coin and not a bottle
    cap? High precision = few false alarms.<br>
    <b>Recall (found):</b> of the 100 hidden coins, how many did you find? High recall = few missed.<br>
    <b>Overall (F1):</b> one grade that combines the two. It is only high when both are high, so this is the main
    score to look at.<br>
    <b>Boundary fit:</b> when a passage is found, how exactly its start and end are right (100% = exactly right).<br>
    <span id="goldnote"></span></p>

    <h3 style="margin-top:12px">How to read the charts</h3>
    <p class="small">Each setting is changed on its own while the others stay as they are. The thin vertical line
    marked &ldquo;current&rdquo; is the value used now. Higher lines are better. Move the mouse over a chart to see
    the exact numbers, or click &ldquo;Show all the numbers&rdquo; under it. Differences of 1&ndash;2 points are too
    small to matter: they can change by chance.</p>
  </div>

  <h2>Summary: should any setting change?</h2>
  <div class="card table-wrap"><table id="summary"></table></div>

  <div id="sections"></div>

  <h2 id="heat-title"></h2>
  <p class="sub" id="heat-sub"></p>
  <div class="card"><div class="chart" id="heatmap"></div><div class="scale" id="heat-scale"></div>
    <details><summary>Show all the numbers</summary><div class="table-wrap"><table id="heat-table"></table></div></details>
  </div>
</main>

<script>
const DATA = /*DATA*/null;
const pct = v => (v * 100).toFixed(0) + "%";
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const SVG = "http://www.w3.org/2000/svg";
function el(tag, attrs, parent) {
  const e = document.createElementNS(SVG, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function h(tag, text, parent, cls) {
  const e = document.createElement(tag);
  if (text !== undefined && text !== null) e.textContent = text;
  if (cls) e.className = cls;
  if (parent) parent.appendChild(e);
  return e;
}
function rowsFor(param) { return DATA.rows.filter(r => r.parameter === param); }

/* ---------- line chart with crosshair tooltip ---------- */
function lineChart(container, opt) {
  container.innerHTML = "";
  const W = 520, H = 262, L = 44, R = 116, T = 26, B = 40;
  const n = opt.x.length, step = (W - L - R) / Math.max(1, n - 1);
  const X = i => L + i * step, Y = v => T + (1 - v) * (H - T - B);
  if (opt.series.length > 1) {
    const lg = h("div", null, container, "legend");
    opt.series.forEach(s => { const sp = h("span", null, lg); const i = h("i", null, sp); i.style.background = cssVar(s.color); h("b", s.name, sp).style.fontWeight = 400; });
  }
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opt.title }, container);
  [0, 0.25, 0.5, 0.75, 1].forEach(v => {
    el("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), stroke: cssVar(v === 0 ? "--axis" : "--grid"), "stroke-width": 1 }, svg);
    el("text", { x: L - 6, y: Y(v) + 4, "text-anchor": "end", "font-size": 11, fill: cssVar("--muted") }, svg).textContent = pct(v);
  });
  opt.x.forEach((v, i) => {
    el("text", { x: X(i), y: H - B + 16, "text-anchor": "middle", "font-size": 11, fill: cssVar("--muted") }, svg).textContent = v;
  });
  el("text", { x: (L + W - R) / 2, y: H - 4, "text-anchor": "middle", "font-size": 11, fill: cssVar("--ink-2") }, svg).textContent = opt.xTitle;
  if (opt.currentIndex >= 0) {
    el("line", { x1: X(opt.currentIndex), x2: X(opt.currentIndex), y1: T - 12, y2: H - B, stroke: cssVar("--ink-2"), "stroke-width": 1 }, svg);
    el("text", { x: X(opt.currentIndex), y: T - 16, "text-anchor": "middle", "font-size": 10, fill: cssVar("--ink-2") }, svg).textContent = "current";
  }
  // lines and points
  const ends = [];
  opt.series.forEach(s => {
    const color = cssVar(s.color);
    const d = s.values.map((v, i) => `${i ? "L" : "M"}${X(i)},${Y(v)}`).join(" ");
    el("path", { d, fill: "none", stroke: color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    s.values.forEach((v, i) => el("circle", { cx: X(i), cy: Y(v), r: 4, fill: color, stroke: cssVar("--surface"), "stroke-width": 2 }, svg));
    if (s.label !== false) ends.push({ y: Y(s.values[n - 1]), name: s.name });
  });
  // direct labels at the right end, pushed apart so they don't overlap
  ends.sort((a, b) => a.y - b.y);
  for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 13) ends[k].y = ends[k - 1].y + 13;
  ends.forEach(e => { el("text", { x: X(n - 1) + 9, y: e.y + 4, "font-size": 11, fill: cssVar("--ink-2") }, svg).textContent = e.name; });
  // hover layer
  const cross = el("line", { y1: T, y2: H - B, stroke: cssVar("--muted"), "stroke-width": 1, visibility: "hidden" }, svg);
  const hit = el("rect", { x: L - step / 2, y: 0, width: W - L - R + step, height: H - B, fill: "transparent", tabindex: 0 }, svg);
  const tip = h("div", null, container, "tip");
  function show(i) {
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("visibility", "visible");
    tip.innerHTML = "";
    h("div", `${opt.xTitle} = ${opt.x[i]}${i === opt.currentIndex ? " (the value used now)" : ""}`, tip, "head");
    opt.series.forEach(s => { const r = h("div", null, tip, "row"); h("b", pct(s.values[i]), r); h("i", null, r).style.background = cssVar(s.color); h("span", s.name, r); });
    (opt.extra ? opt.extra(i) : []).forEach(t => h("div", t, tip, "small"));
    tip.style.display = "block";
    const box = svg.getBoundingClientRect(), scale = box.width / W;
    let left = X(i) * scale + 12;
    if (left + tip.offsetWidth > box.width) left = X(i) * scale - tip.offsetWidth - 12;
    tip.style.left = left + "px"; tip.style.top = (T * scale + 18) + "px";
  }
  function hide() { cross.setAttribute("visibility", "hidden"); tip.style.display = "none"; }
  hit.addEventListener("pointermove", ev => {
    const box = svg.getBoundingClientRect(), x = (ev.clientX - box.left) * W / box.width;
    show(Math.max(0, Math.min(n - 1, Math.round((x - L) / step))));
  });
  hit.addEventListener("pointerleave", hide);
  let focusIndex = opt.currentIndex >= 0 ? opt.currentIndex : 0;
  hit.addEventListener("focus", () => show(focusIndex));
  hit.addEventListener("blur", hide);
  hit.addEventListener("keydown", ev => {
    if (ev.key === "ArrowRight") focusIndex = Math.min(n - 1, focusIndex + 1);
    else if (ev.key === "ArrowLeft") focusIndex = Math.max(0, focusIndex - 1);
    else return;
    ev.preventDefault(); show(focusIndex);
  });
}

/* ---------- helpers for the text ---------- */
function best(rows, key) {
  // highest value; on a tie, the one closest to the current setting
  let b = rows[0];
  rows.forEach(r => { if (r[key] > b[key] + 1e-9) b = r; });
  const ties = rows.filter(r => Math.abs(r[key] - b[key]) < 1e-9);
  return ties.find(r => r.is_current) || ties[0];
}
function advice(rows) {
  // Plain-language advice: keep the current value unless another one is clearly better on BOTH tests.
  const cur = rows.find(r => r.is_current), b = best(rows, "f1");
  if (!cur) return { keep: false, short: `Try ${b.value}`, long: `The best value on the practice test is ${b.value}.` };
  if (b.is_current) return { keep: true, short: "Keep it: already the best",
    long: `Keep ${cur.value}: no other value gets a better overall score on the practice test.` };
  if (DATA.hasGold && b.known_found < cur.known_found - 0.02) return { keep: true, short: "Keep it: the other value finds fewer real parallels",
    long: `Keep ${cur.value}. The practice test likes ${b.value} a little more (${pct(b.f1)} instead of ${pct(cur.f1)}), ` +
          `but on the real Gospels ${b.value} finds fewer of the known parallels (${pct(b.known_found)} instead of ${pct(cur.known_found)}).` };
  if (b.f1 - cur.f1 < 0.02) return { keep: true, short: "Keep it: the difference is too small to matter",
    long: `Keep ${cur.value}. The best value, ${b.value}, scores ${pct(b.f1)} instead of ${pct(cur.f1)}: a difference too small to matter.` };
  return { keep: false, short: `Worth trying ${b.value}`,
    long: `Worth trying ${b.value}: it scores ${pct(b.f1)} instead of ${pct(cur.f1)} on the practice test` +
          (DATA.hasGold ? ` and finds ${pct(b.known_found)} of the known real parallels (now ${pct(cur.known_found)}).` : ".") };
}
function takeaway(container, rows) {
  const cur = rows.find(r => r.is_current), first = rows[0], last = rows[rows.length - 1], a = advice(rows);
  const box = h("div", null, container, "takeaway");
  const p1 = h("p", null, box); p1.style.margin = "0 0 4px";
  h("b", a.long, p1);
  const p2 = h("p", null, box); p2.style.margin = "0";
  p2.textContent = (cur ? `Right now the overall score is ${pct(cur.f1)}` +
      (DATA.hasGold ? ` and ${pct(cur.known_found)} of the known real parallels are found. ` : ". ") : "") +
    `With the smallest value tried (${first.value}), ${pct(first.precision)} of the reported matches are correct and ` +
    `${pct(first.recall)} of the hidden passages are found; with the biggest (${last.value}) it is ${pct(last.precision)} correct ` +
    `and ${pct(last.recall)} found.`;
}

/* ---------- build the page ---------- */
function render() {
  const info = DATA.info;
  const names = info.books.map(b => b[0].toUpperCase() + b.slice(1)).join(", ");
  document.getElementById("intro").textContent =
    `Practice test: ${info.planted} hidden passages in ${info.cases} jumbled texts made from ${names}.` +
    (DATA.hasGold ? ` Real test: ${info.gold} known parallels.` : "") +
    ` Made on ${info.created}${info.quick ? " (quick run: fewer passages, so the numbers are rougher)" : ""}.`;
  const realtest = document.getElementById("realtest"); realtest.innerHTML = "";
  h("b", "2. The real test. ", realtest);
  realtest.appendChild(document.createTextNode(DATA.hasGold
    ? `We run the program on the real Gospels and compare it with a list of ${info.gold} known parallels ` +
      `taken from Kurt Aland's Synopsis, the standard reference book scholars use (file gold_parallels.csv). ` +
      `This checks that the settings also work on real texts, not just on our made-up test.`
    : "Skipped, because the file gold_parallels.csv was not found."));
  const goldnote = document.getElementById("goldnote"); goldnote.innerHTML = "";
  if (DATA.hasGold) {
    h("b", "Known found (real test): ", goldnote);
    goldnote.appendChild(document.createTextNode("the share of the known parallels that the program found. Not every known " +
      "parallel can be found: some stories are told in completely different words."));
    goldnote.appendChild(document.createElement("br"));
    h("b", "Inside known (real test): ", goldnote);
    goldnote.appendChild(document.createTextNode("the share of the program's matches that lie inside a known parallel. " +
      "The known list is not complete, so the true share of correct matches is higher than this."));
  }

  // summary table
  const sum = document.getElementById("summary"); sum.innerHTML = "";
  const hr = h("tr", null, h("thead", null, sum));
  ["Setting", "Value now", "Overall score now", "Best value (practice test)", "Its overall score"]
    .concat(DATA.hasGold ? ["Known parallels found now"] : []).concat(["Advice"]).forEach(t => h("th", t, hr));
  const tb = h("tbody", null, sum);
  Object.keys(DATA.sweeps).forEach(p => {
    const rows = rowsFor(p), cur = rows.find(r => r.is_current), b = best(rows, "f1");
    const tr = h("tr", null, tb);
    h("td", p, tr); h("td", String(DATA.current[p]), tr); h("td", cur ? pct(cur.f1) : "n/a", tr);
    h("td", String(b.value), tr); h("td", pct(b.f1), tr);
    if (DATA.hasGold) h("td", cur ? pct(cur.known_found) : "n/a", tr);
    h("td", advice(rows).short, tr);
  });

  // one section per setting
  const sections = document.getElementById("sections"); sections.innerHTML = "";
  Object.keys(DATA.sweeps).forEach(p => {
    const rows = rowsFor(p), x = rows.map(r => r.value), ci = rows.findIndex(r => r.is_current);
    h("h2", p, sections);
    h("p", DATA.explain[p], sections, "sub");
    takeaway(sections, rows);
    const g = h("div", null, sections, "grid2");
    const card = (title, note) => { const c = h("div", null, g, "card"); h("h3", title, c); h("p", note, c, "small"); return h("div", null, c, "chart"); };

    lineChart(card("Practice test: how good are the results?", "The Overall (F1) line is the main score."),
      { title: `${p}: precision, recall and F1`, x, xTitle: p, currentIndex: ci,
      series: [{ name: "Precision (correct)", values: rows.map(r => r.precision), color: "--s1" },
               { name: "Recall (found)", values: rows.map(r => r.recall), color: "--s2" },
               { name: "Overall (F1)", values: rows.map(r => r.f1), color: "--s3" }],
      extra: i => [`${rows[i].reported} matches reported`] });

    lineChart(card("Practice test: hidden passages found, by how much they were changed", "The more a passage was changed, the harder it is to find."),
      { title: `${p}: recall by how much the passage was changed`, x, xTitle: p, currentIndex: ci,
      series: DATA.editRates.map((rate, k) => ({ name: rate === 0 ? "Exact copy" : `${Math.round(rate * 100)}% changed`, color: `--o${k + 1}`,
        values: rows.map(r => r[`found_${Math.round(rate * 100)}pct_edits`]), label: k === 0 || k === DATA.editRates.length - 1 })) });

    lineChart(card("Practice test: are the start and end in the right place?", "100% = the start and end of each found passage are exactly right."),
      { title: `${p}: boundary fit`, x, xTitle: p, currentIndex: ci,
      series: [{ name: "Boundary fit", values: rows.map(r => r.boundary_fit), color: "--s1", label: false }] });

    if (DATA.hasGold) {
      lineChart(card("Real test: the known Gospel parallels", "Known found = how many known parallels were found. Inside known = how many matches are inside a known parallel."),
        { title: `${p}: known parallels in the real Gospels`, x, xTitle: p, currentIndex: ci,
        series: [{ name: "Known found", values: rows.map(r => r.known_found), color: "--s1" },
                 { name: "Inside known", values: rows.map(r => r.real_inside_known), color: "--s2" }],
        extra: i => [`${rows[i].real_reported} matches reported in the real Gospels`] });
    }

    // the numbers
    const det = h("details", null, sections); h("summary", "Show all the numbers", det);
    const wrap = h("div", null, det, "table-wrap"), t = h("table", null, wrap);
    const cols = [["value", p], ["f1", "Overall (F1)"], ["precision", "Precision (correct)"], ["recall", "Recall (found)"], ["boundary_fit", "Boundary fit"]]
      .concat(DATA.editRates.map(r => [`found_${Math.round(r * 100)}pct_edits`, r === 0 ? "Found: exact copies" : `Found: ${Math.round(r * 100)}% changed`]))
      .concat([["reported", "Matches reported (practice)"]])
      .concat(DATA.hasGold ? [["known_found", "Known found (real)"], ["real_reported", "Matches reported (real)"], ["real_inside_known", "Inside known (real)"]] : [])
      .concat([["seconds", "Seconds"]]);
    const thr = h("tr", null, h("thead", null, t)); cols.forEach(c => h("th", c[1], thr));
    const tbody = h("tbody", null, t);
    rows.forEach(r => {
      const tr = h("tr", null, tbody); if (r.is_current) tr.className = "current";
      cols.forEach(([k]) => {
        let v = r[k];
        if (k === "value") v = r.is_current ? `${v} (now)` : v;
        else if (k === "reported" || k === "real_reported") v = String(v);
        else if (k === "seconds") v = v.toFixed(1);
        else v = pct(v);
        h("td", String(v), tr);
      });
    });
  });

  heatmap();
}

/* ---------- heatmap: two settings at once ---------- */
function mix(a, b, t) {
  const p = s => [1, 3, 5].map(i => parseInt(s.slice(i, i + 2), 16));
  const A = p(a), B = p(b);
  return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(",")})`;
}
function heatmap() {
  const [pa, pb] = DATA.gridParams, va = DATA.sweeps[pa], vb = DATA.sweeps[pb];
  document.getElementById("heat-title").textContent = `Trying ${pa} and ${pb} together`;
  document.getElementById("heat-sub").textContent =
    `These two settings affect each other, so here every combination was tried. Each square shows the overall score (F1) ` +
    `on the practice test; the color scale under the grid shows which color means better. The square with a thick border ` +
    `is the combination used now. Move the mouse over a square to see its numbers. This grid only uses the practice test, ` +
    `so check a promising combination on the real Gospels too before switching.`;
  const box = document.getElementById("heatmap"); box.innerHTML = "";
  const cell = 46, gap = 2, L = 90, T = 46;
  const W = L + vb.length * cell + 10, H = T + va.length * cell + 40;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "F1 heatmap" }, box);
  svg.style.maxWidth = W * 1.4 + "px";
  // the color scale starts at the 25th percentile, so differences between the good settings stay visible
  const vals = DATA.grid.map(g => g.f1).sort((a, b) => a - b), hi = vals[vals.length - 1];
  const lo = vals[Math.floor(vals.length * 0.25)], clamped = vals[0] < lo;
  const low = cssVar("--seq-low"), high = cssVar("--seq-high");
  const color = v => mix(low, high, hi > lo ? Math.max(0, (v - lo) / (hi - lo)) : 1);
  const bestCell = DATA.grid.reduce((a, b) => (b.f1 > a.f1 ? b : a));
  const tip = h("div", null, box, "tip");
  vb.forEach((v, j) => { el("text", { x: L + j * cell + cell / 2, y: T - 8, "text-anchor": "middle", "font-size": 11, fill: cssVar("--muted") }, svg).textContent = v; });
  el("text", { x: L + vb.length * cell / 2, y: 12, "text-anchor": "middle", "font-size": 11, fill: cssVar("--ink-2") }, svg).textContent = pb;
  va.forEach((v, i) => { el("text", { x: L - 10, y: T + i * cell + cell / 2 + 4, "text-anchor": "end", "font-size": 11, fill: cssVar("--muted") }, svg).textContent = v; });
  el("text", { x: 14, y: T + va.length * cell / 2, "text-anchor": "middle", "font-size": 11, fill: cssVar("--ink-2"), transform: `rotate(-90 14 ${T + va.length * cell / 2})` }, svg).textContent = pa;
  DATA.grid.forEach(g => {
    const i = va.indexOf(g[pa]), j = vb.indexOf(g[pb]);
    const x = L + j * cell + gap / 2, y = T + i * cell + gap / 2, s = cell - gap;
    const isCur = g[pa] === DATA.current[pa] && g[pb] === DATA.current[pb];
    const r = el("rect", { x, y, width: s, height: s, rx: 4, fill: color(g.f1), tabindex: 0 }, svg);
    if (isCur) el("rect", { x: x + 1, y: y + 1, width: s - 2, height: s - 2, rx: 4, fill: "none", stroke: cssVar("--ink"), "stroke-width": 2, "pointer-events": "none" }, svg);
    if (g === bestCell || isCur) {
      const rgb = color(g.f1).match(/\d+/g).map(Number);
      const lum = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255;
      el("text", { x: x + s / 2, y: y + s / 2 + 4, "text-anchor": "middle", "font-size": 11, "font-weight": 600, fill: lum < 0.55 ? "#ffffff" : "#0b0b0b", "pointer-events": "none" }, svg).textContent = pct(g.f1);
    }
    const show = () => {
      r.setAttribute("stroke", cssVar("--ink-2")); r.setAttribute("stroke-width", 1);
      tip.innerHTML = "";
      h("div", `${pa} = ${g[pa]}, ${pb} = ${g[pb]}${isCur ? " (used now)" : ""}${g === bestCell ? " (best)" : ""}`, tip, "head");
      [["Overall (F1)", g.f1], ["Precision (correct)", g.precision], ["Recall (found)", g.recall]].forEach(([n, v]) => { const row = h("div", null, tip, "row"); h("b", pct(v), row); h("span", n, row); });
      tip.style.display = "block";
      const b = svg.getBoundingClientRect(), sc = b.width / W;
      let left = (x + s) * sc + 8; if (left + tip.offsetWidth > box.clientWidth) left = x * sc - tip.offsetWidth - 8;
      tip.style.left = left + "px"; tip.style.top = (y * sc) + "px";
    };
    const hide = () => { r.removeAttribute("stroke"); tip.style.display = "none"; };
    r.addEventListener("pointerenter", show); r.addEventListener("pointerleave", hide);
    r.addEventListener("focus", show); r.addEventListener("blur", hide);
  });
  const sc = document.getElementById("heat-scale"); sc.innerHTML = "";
  h("span", `Overall score ${clamped ? "≤ " : ""}${pct(lo)}`, sc); const bar = h("span", null, sc, "bar");
  bar.style.background = `linear-gradient(90deg, ${low}, ${high})`; h("span", pct(hi), sc);
  h("span", `Best square: ${pa} = ${bestCell[pa]}, ${pb} = ${bestCell[pb]} (${pct(bestCell.f1)})`, sc);

  const t = document.getElementById("heat-table"); t.innerHTML = "";
  const thr = h("tr", null, h("thead", null, t)); h("th", `${pa} \\ ${pb}`, thr); vb.forEach(v => h("th", String(v), thr));
  const tbody = h("tbody", null, t);
  va.forEach(a => { const tr = h("tr", null, tbody); h("th", String(a), tr);
    vb.forEach(b => { const g = DATA.grid.find(q => q[pa] === a && q[pb] === b); h("td", pct(g.f1), tr); }); });
}

render();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
