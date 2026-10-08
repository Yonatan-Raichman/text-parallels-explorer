"""Turn Aland's table of Gospel parallels (aland_table.txt) into ../gold_parallels.csv,
the answer key used by benchmark.py.

Run it from the project folder with:   python gold/make_gold.py

Which stories are kept: only stories that appear in at least two of the books listed in BOOKS.
John is left out by default, because John usually tells the same story in different words,
and our program can only find shared wording.
"""
import csv
import re
from pathlib import Path

BOOKS = ["matthew", "mark", "luke"]  # add "john" here to include John
COLUMNS = ["matthew", "mark", "luke", "john"]  # the order of the columns in aland_table.txt

HERE = Path(__file__).parent
TABLE = HERE / "aland_table.txt"
OUTPUT = HERE.parent / "gold_parallels.csv"


def parse_cell(cell):
    """'13.1-9 8.34-9.1 16.1-2a,4' -> [('13:1', '13:9'), ('8:34', '9:1'), ('16:1', '16:2'), ('16:4', '16:4')]"""
    cell = re.sub(r"\.\s+(\d)", r".\1", cell)        # '9. 10b-17'  -> '9.10b-17'
    cell = re.sub(r"(\d)\s+[ab]\b", r"\1", cell)      # '3.7-13 a'   -> '3.7-13'
    if re.search(r"[c-zA-Z]", cell):                  # e.g. '1 Cor. 15.3-8' or 'see note below'
        return []
    ranges = []
    for reference in cell.split():
        chapter, _, verses = reference.partition(".")
        for part in verses.split(","):                # '1-2a,4' -> '1-2a' and '4'
            part = re.sub(r"[ab]", "", part)          # half verses count as the whole verse
            first, _, last = part.partition("-")
            if not last:
                last = first
            if "." in last:                           # crosses into the next chapter: '34-9.1'
                end_chapter, end_verse = last.split(".")
            else:
                end_chapter, end_verse = chapter, last
            ranges.append((f"{int(chapter)}:{int(first)}", f"{int(end_chapter)}:{int(end_verse)}"))
    return ranges


def main():
    rows, seen, stories = [], set(), 0
    for line in TABLE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        number, title, *cells = [c.strip() for c in line.split("|")]
        refs = {book: parse_cell(cell) for book, cell in zip(COLUMNS, cells) if book in BOOKS}
        refs = {book: r for book, r in refs.items() if r}
        if len(refs) < 2:
            continue                                  # a story in only one book has no parallel
        # Aland lists some stories twice (once in each Gospel's order); keep each only once
        key = tuple(sorted((book, tuple(r)) for book, r in refs.items()))
        if key in seen:
            continue
        seen.add(key)
        stories += 1
        for book, ranges in refs.items():
            for first, last in ranges:
                rows.append([f"Aland {number}: {title}", book, first, last])

    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["story", "book", "first_verse", "last_verse"])
        writer.writerows(rows)
    print(f"Wrote {OUTPUT.name}: {stories} stories, {len(rows)} verse ranges, books: {', '.join(BOOKS)}")


if __name__ == "__main__":
    main()
