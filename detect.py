from itertools import combinations # lets you take items and generate every possible unique pair
from pathlib import Path # Path makes it easier to work with files and folders

import database # imports database.py
import matcher # file containing your parallel-detection algorithm

CORPUS_FOLDER = Path(__file__).parent / "corpus"
BOOK_ORDER = ["matthew", "mark", "luke", "john"]


def run(): # connect database -> load books -> compare books -> save parallels -> print statistics -> close database
    conn = database.connect() # connection to parallels.db
    # 1. Put every text file from the corpus folder into the database
    for name in BOOK_ORDER:
        path = CORPUS_FOLDER / f"{name}.txt"
        if path.exists(): # does this file actually exist?
            database.save_document(conn, name.title(), path.read_text(encoding="utf-8")) # Read the current Gospel text file and save its name and full text into the database

    # 2. Compare every pair of documents: (Matthew, Mark), (Matthew, Luke), ... 6 pairs for 4 books
    before = database.count_parallels(conn)
    documents = database.get_documents(conn)
    for doc_a, doc_b in combinations(documents, 2): # combinations(documents, 2) - Give me every possible group of 2 documents
        for m in matcher.find_parallels(doc_a["text"], doc_b["text"]): # For each match that the algorithm finds, store it temporarily in m
            database.save_parallel(conn, doc_a["id"], doc_b["id"], m)
    conn.commit()

    total = database.count_parallels(conn)
    print(f"{len(documents)} documents, {total} parallels, {total - before} new")
    conn.close()


if __name__ == "__main__":
    run()
