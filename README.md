# Text Parallels Explorer

Finds passages that are the same or almost the same in the four Gospels (King James Version),
saves them in a database, and lets a researcher review them in a web page.

## How to run

```
docker compose up --build
```

Then open http://localhost:8501.

Without Docker: `pip install -r requirements.txt` and then `streamlit run app.py`.
Tests: `python tests.py`

## Corpus

`corpus/` contains Matthew, Mark, Luke and John from the King James Version (public domain,
Project Gutenberg ebooks 8040-8043), cleaned by `get_texts.py` to one verse per line.
Matthew, Mark and Luke share a lot of text, John shares little, so it is a useful comparison.

## Database (SQLite, one file)

- `documents (id, name UNIQUE, text)`
- `parallels (id, doc_a, doc_b, a_start, a_end, b_start, b_end, score, kind, words, status)`
  - `a_start/a_end` and `b_start/b_end` are character positions in each text
  - `kind` is `exact` or `near`; `status` is `pending`, `confirmed` or `rejected`
  - `UNIQUE (doc_a, doc_b, a_start, a_end, b_start, b_end)`: the same parallel can never be saved twice.
    Re-runs use `INSERT ... ON CONFLICT DO UPDATE`, which never changes `status`, so reviews are kept.

## Algorithm

1. Split each text into lowercase words, remembering each word's position in the original text.
2. **Seeds**: find every 4-word phrase that appears in both texts.
   Phrases that appear more than 25 times are ignored as too common.
3. **Group**: seeds that are close together (at most 20 words apart) in both texts form one passage.
   The gaps between seeds are what allow near matches.
4. **Score**: `2 x matching words / total words` (Python's `difflib`). 1.0 = exact, otherwise near.
   Matches shorter than 8 words or below 0.5 are dropped, and overlapping matches are reduced to the longest.

## Extra features

- Verse numbers (e.g. Mark 1:3) next to every passage, to help with researchers cite.
- Words that differ between the two passages are highlighted to help and aim researchers at their studies.
- Overview of how many parallels each pair of books shares.
- Download the (filtered) list as CSV.

## Limitations

- Only finds passages that share some exact 4-word phrases, paraphrases with different words are missed.
- "Exact" ignores capital letters and punctuation.
- The settings were chosen by checking known parallels by hand, not measured against a labelled test set.
- If a text file is changed, old positions are no longer correct You should delete the database to start fresh.
- SQLite is fine for one researcher, not for many people writing at once.

## Use of AI

I used Claude to help plan the project, write a first version of the code
and explain the concepts. I ran, tested and checked everything, and can explain every part.
