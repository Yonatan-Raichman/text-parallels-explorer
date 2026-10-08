# Text Parallels Explorer

Finds passages that are the same or almost the same in the four Gospels (King James Version),
saves them in a database, and lets a researcher review them in a web page.

## How to run

```
docker compose up --build
```

Then open http://localhost:8501. The first start takes a few minutes.

Without Docker: `pip install -r requirements.txt` and then `streamlit run app.py`.
Tests: `python tests.py`

## Corpus

`corpus/` contains Matthew, Mark, Luke and John from the King James Version (public domain,
Project Gutenberg ebooks 8040-8043), cleaned by `get_texts.py` to one verse per line.
Matthew, Mark and Luke share a lot of text; John shares little, so it is a useful comparison.

## Database (SQLite, one file)

- `documents (id, name UNIQUE, text)`
- `parallels (id, doc_a, doc_b, a_start, a_end, b_start, b_end, score, kind, words, status)`
  - `a_start/a_end` and `b_start/b_end` are character positions in each text
  - `kind` is `exact` or `near`; `status` is `pending`, `confirmed` or `rejected`
  - `UNIQUE (doc_a, doc_b, a_start, a_end, b_start, b_end)`: the same parallel can never be saved twice.
    Re-runs use `INSERT ... ON CONFLICT DO UPDATE`, which never changes `status`, so reviews are kept.

## Algorithm

1. Split each text into lowercase words, remembering each word's position in the original text.
2. **Seeds**: find every 4-word phrase that appears in both texts (using a dictionary, so it is fast).
   Phrases that appear more than 25 times are ignored as too common.
3. **Group**: seeds that are close together (at most 20 words apart) in both texts form one passage.
   The gaps between seeds are what allow near matches.
4. **Score**: `2 x matching words / total words` (Python's `difflib`). 1.0 = exact, otherwise near.
   Matches shorter than 8 words or below 0.5 are dropped, and overlapping matches are reduced to the longest.

## How good is it? Testing the settings

The algorithm has five settings at the top of `matcher.py` (for example `SEED_SIZE = 4`). I didn't want to
pick them by guessing, so I wrote `benchmark.py`. It tries many values for each setting and measures how well
the program finds parallels with each one.

### The two tests

1. **The practice test.** I hid 400 passages copied from one Gospel inside jumbled-up text. Some are exact
   copies; others have 10-40% of their words changed. Because I hid them myself, I know every right answer,
   so the program can be graded exactly.
2. **The real test.** The program runs on the real Gospels, and its results are compared with a list of
   455 known parallels from Kurt Aland's *Synopsis of the Four Gospels*, the standard reference book that
   scholars use (`gold_parallels.csv`, made from `gold/aland_table.txt` by `gold/make_gold.py`).

### What the scores mean

Imagine looking for 100 coins hidden on a beach with a metal detector:

- **Precision (correct):** of everything you dug up, how much was really a coin? High = few false alarms.
- **Recall (found):** of the 100 hidden coins, how many did you find? High = few missed.
- **Overall score (F1):** one grade combining the two. It is only high when both are high.
- **Known found:** in the real test, how many of the 455 known parallels the program found.

### Results with the current settings

| What was measured | Result |
|---|---|
| Practice test: matches that are correct (precision) | **86%** |
| Practice test: hidden passages found (recall) | **92%** |
| Practice test: overall score (F1) | **89%** |
| Practice test: exact copies found | 100% |
| Practice test: passages with 40% of the words changed, found | 71% |
| Real test: known parallels found | **68%** (308 of 455) |
| Real test: matches reported | 618 |
| Real test: matches that are inside a known parallel | 76% (the real share of correct matches is higher, because the known list is not complete) |

Not every known parallel can be found: some stories are told in completely different words, and a program
that compares words cannot match those. Even the loosest settings only find about 85% of them.

### What I learned about each setting

| Setting | What the test showed | Decision |
|---|---|---|
| `SEED_SIZE = 4` | 4 is the best value. With 2 or 3 the program finds more, but many matches are wrong (only 20% and 57% correct). With 5 or more it misses edited passages. | Keep 4 |
| `MAX_GAP = 20` | Values from 10 to 60 score almost the same on the practice test. At 60, separate passages get glued together (618 matches become 350), so fewer real parallels are found. | Keep 20 |
| `MIN_WORDS = 8` | 10 is 1 point better on the practice test but finds fewer real parallels. 4 is far too low: almost 7,000 matches, mostly short common phrases. | Keep 8 |
| `MIN_SCORE = 0.5` | The practice test likes 0.7 slightly more, but on the real Gospels 0.7 finds fewer known parallels (61% instead of 68%). | Keep 0.5 |
| `MAX_COMMON = 25` | The practice test likes 1, but on the real Gospels it finds fewer known parallels (64% instead of 68%). | Keep 25 |

**Conclusion:** the current settings are a good balance, so I kept them. For two settings (MIN_SCORE and
MAX_COMMON) the two tests disagreed: the practice test preferred stricter values, the real Gospels preferred
looser ones. Real authors change wording in more ways than my random edits do, so I followed the real texts.
This is exactly why it is useful to have both tests.

### See it yourself

Open `benchmark_report.html` in a browser for the charts and all the numbers. To run the benchmark again
(it takes a few minutes, and nothing extra needs to be installed):

```
python benchmark.py
```

## Extra features

- Verse numbers (e.g. Mark 1:3) next to every passage, because that is how researchers cite.
- Words that differ between the two passages are highlighted, because the differences are what a researcher studies.
- Overview of how many parallels each pair of books shares.
- Download the (filtered) list as CSV.

## Limitations

- Only finds passages that share some exact 4-word phrases; paraphrases with different words are missed.
- "Exact" ignores capital letters and punctuation.
- The settings were tested on the Gospels only; other texts (or other languages) may need other settings.
- The known-parallels list is not complete, so the benchmark can show what the program misses, but only
  estimate how many of its matches are wrong.
- If a text file is changed, old positions are no longer correct (delete the database to start fresh).
- SQLite is fine for one researcher, not for many people writing at once.

## Use of AI

I used Claude (an AI assistant) to help plan the project, write a first version of the code
and explain the concepts. I ran, tested and checked everything, and can explain every part.
