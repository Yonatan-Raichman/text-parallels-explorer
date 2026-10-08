import csv
import re
from pathlib import Path

BOOKS = ["matthew", "mark", "luke"] 
COLUMNS = ["matthew", "mark", "luke", "john"]  

HERE = Path(__file__).parent
TABLE = HERE / "aland_table.txt"
OUTPUT = HERE.parent / "gold_parallels.csv"


def parse_cell(cell):
    """'13.1-9 8.34-9.1 16.1-2a,4' -> [('13:1', '13:9'), ('8:34', '9:1'), ('16:1', '16:2'), ('16:4', '16:4')]"""
    cell = re.sub(r"\.\s+(\d)", r".\1", cell)        
    cell = re.sub(r"(\d)\s+[ab]\b", r"\1", cell)      
    if re.search(r"[c-zA-Z]", cell):                  
        return []
    ranges = []
    for reference in cell.split():
        chapter, _, verses = reference.partition(".")
        for part in verses.split(","):               
            part = re.sub(r"[ab]", "", part)          
            first, _, last = part.partition("-")
            if not last:
                last = first
            if "." in last:                           
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
            continue                                  
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
