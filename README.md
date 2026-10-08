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

`corpus/` folder contains the four Gospels. The Gospels are Matthew, Mark, Luke, and John from the King James Version of the Bible (public domain, Project Gutenberg ebooks 8040–8043). The texts are processed by `get_texts.py`, which organizes them into one verse per line.

Matthew, Mark, and Luke tell many of the same stories about Jesus, often using similar wording. John tells the story from a different perspective and shares fewer identical passages. This makes the four Gospels useful for testing how well the algorithm identifies similarities and differences between texts.

## Database (SQLite, one file)

- `documents (id, name UNIQUE, text)`
- `parallels (id, doc_a, doc_b, a_start, a_end, b_start, b_end, score, kind, words, status)`
  - `a_start/a_end` and `b_start/b_end` are character positions in each text
  - `kind` is `exact` or `near`; `status` is `pending`, `confirmed` or `rejected`
  - `UNIQUE (doc_a, doc_b, a_start, a_end, b_start, b_end)`: the same parallel can never be saved twice.
    Re-runs use `INSERT ... ON CONFLICT DO UPDATE`, which never changes `status`, so reviews are kept.

## Algorithm

1. **Split the two Gospels into words.**  
   Each Gospel is cleaned into a list of lowercase words, while the original character position of every word is also saved. These positions are needed later so the matched passage can be located and highlighted in the original text.

2. **Find seeds using a sliding window.**  
   Both Gospels are searched for **seeds**, where a seed is a sequence of **4 consecutive identical words**. A 4-word sliding window moves through the texts and compares the phrases. When the same 4-word phrase appears in both texts, its **starting word position in each Gospel** is saved as a seed, for example `(100, 250)`. Phrases that appear **more than 25 times** in the second text are ignored because they are too common to be useful evidence of a meaningful parallel.

3. **Group nearby seeds into larger passages.**  
   Seeds that occur close to each other in **both Gospels** are grouped together. A new seed can join a group only if it is no more than **20 words after the previous seed in both texts**. This allows the algorithm to connect several small exact matches into one larger passage, even if some words between the seeds are different. If a seed is too far away to join an existing group, it starts a new group.

4. **Build and evaluate the complete passage.**  
   The first and last seeds in each group are used to determine the full passage in both Gospels. The passages are then given a similarity score using `SequenceMatcher`:

                 2 × matching words in order
   score = -----------------------------------------
            words in passage A + words in passage B

The similarity score is calculated using `SequenceMatcher` because an exact comparison would be too strict. Parallel passages may contain small wording differences while still being clearly related. The score measures how much of the two passages matches in the same order while taking the length of both passages into account. This produces a normalized value between `0` and `1`, where `1` means the passages are identical. Using both passage lengths also prevents a short passage contained inside a much longer passage from incorrectly receiving a perfect score.

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

## Limitations

- Only finds passages that share some exact 4-word phrases. Paraphrases with different words are missed.
- "Exact" ignores capital letters and punctuation.
- The settings were tested on the Gospels only. Other texts (or other languages) may need other settings.
- The known parallels list is not complete, so the benchmark can show what the program misses, but only
  estimate how many of its matches are wrong.
- If a text file is changed, old positions are no longer correct.
- SQLite is fine for one researcher, not for many people writing at once.

## Use of AI

I used Claude to help plan the project, write a first version of the code
and explain the concepts. I ran, tested and checked everything, and can explain every part.
