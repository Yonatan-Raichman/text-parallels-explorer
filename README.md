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

The program compares two texts (for example two Gospels) in five steps.

1. **Split both texts into words.**  
   Each text is turned into a list of lowercase words. Punctuation and numbers are dropped, so verse
   numbers like `3:1` are ignored. For every word, its original character position in the text is
   also saved. These positions are needed later to locate and highlight the matched passage in the
   original text.

2. **Find seeds: 4-word phrases that appear in both texts.**  
   A **seed** is a sequence of **4 consecutive words** that appears in both texts. To find them
   quickly, the program first puts every 4-word phrase of the second text into a dictionary
   (phrase → the positions where it appears). It then goes through the first text one 4-word phrase
   at a time and looks each phrase up in the dictionary, which is instant. Every hit is saved as a
   seed: a pair of word positions, for example `(100, 250)`, meaning "the phrase starting at word 100
   in text A also starts at word 250 in text B". Phrases that appear **more than 25 times** in the
   second text are skipped, because they are too common (like "and he said unto") to be useful
   evidence of a real parallel.

3. **Group nearby seeds into passages.**  
   Seeds that are close to each other in **both texts** are joined into one group. A seed can join a
   group only if it comes **after** the group's last seed, and **no more than 20 words after it, in
   both texts**. This connects several small exact matches into one longer passage, even if some words
   between them are different. That is what makes near matches possible. A seed that cannot join any
   group starts a new one.

4. **Measure how similar each passage is.**  
   Each group becomes a passage: from the first seed to the end of the last seed (the last seed's
   start plus its 4 words), in both texts. The two versions of the passage are then compared with
   `SequenceMatcher` from Python's `difflib` library:

```
            2 × words that match, in the same order
   score = -----------------------------------------
            words in passage A + words in passage B
```

   The score is between `0` (nothing in common) and `1` (identical). For example, Mark 1:3 and
   John 1:23 share 13 of 15 words in order: 2 × 13 ÷ (15 + 15) = **0.87**.

   An exact comparison would be too strict, because real parallels often differ in a few words. This
   score shows how much of the two passages matches, in order. Because it counts the length of
   **both** passages, a short passage inside a much longer one does not get a perfect score. For
   example, 10 matching words inside a 30-word passage score 2 × 10 ÷ (10 + 30) = 0.5, not 1.

5. **Filter and save the results.**  
   Passages shorter than **8 words** or with a score below **0.5** are thrown away. A score of `1`
   is labelled **exact**, anything lower **near**. If two passages overlap in both texts, only the
   longer one is kept. Finally, the word positions are converted back into **character positions**
   in the original texts, and these are what is saved in the database.
   
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
| `MIN_SCORE = 0.5` | On the practice test, the value 0.7 got the best score (91% instead of 89%). But on the real Gospels, 0.7 finds fewer known parallels (61% instead of 68%). | Keep 0.5 |
| `MAX_COMMON = 25` | On the practice test, the value 1 got the best score (92% instead of 89%), because it ignores every repeated phrase. But on the real Gospels it finds fewer known parallels (64% instead of 68%). | Keep 25 |

**Conclusion:** the current settings are a good balance, so I kept them. For two settings (MIN_SCORE and
MAX_COMMON) the two tests disagreed: the practice test preferred stricter values, the real Gospels preferred
looser ones. Real authors change wording in more ways than my random edits do, so I followed the real texts.

## Extra features (and why)

- **Verse references** (e.g. "Matthew 3:3"): readers think in verses, not character positions.
- **Orange highlighting of different words**: in a near match you can see right away which words changed.
- **Overview of parallels per pair of books**: shows which Gospels are closest (Matthew–Mark 237, Matthew–Luke 226, Mark–Luke 155; John has far fewer: 60, 29 and 23, as scholars expect).
- **"Compared with" filter**: to study one pair of books at a time.
- **Click a row to compare**: faster than typing an ID.
- **Confirm / Reject buttons**: a person can review results, and running the detection again never erases a review.
- **CSV download**: to use the results in Excel or other tools.
- **Settings benchmark** (`benchmark.py`): tests each setting on a practice test and against 455 known parallels from Aland's Synopsis, so the chosen values are backed by numbers, not guesses.

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
