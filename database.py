import os
import sqlite3

DB_FILE = os.environ.get("DB_FILE", "parallels.db") # Give me the value of the environment variable DB_FILE. if it doesn't exist, give me "parallels.db"

TABLES = """
CREATE TABLE IF NOT EXISTS documents (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    text  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS parallels (
    id       INTEGER PRIMARY KEY,
    doc_a    INTEGER NOT NULL REFERENCES documents(id),
    doc_b    INTEGER NOT NULL REFERENCES documents(id),
    a_start  INTEGER NOT NULL,
    a_end    INTEGER NOT NULL,
    b_start  INTEGER NOT NULL,
    b_end    INTEGER NOT NULL,
    score    REAL NOT NULL,
    kind     TEXT NOT NULL,
    words    INTEGER NOT NULL,
    status   TEXT NOT NULL DEFAULT 'pending',
    UNIQUE (doc_a, doc_b, a_start, a_end, b_start, b_end)
);
"""


def connect(): # This function job is to open the database and prepare it
    conn = sqlite3.connect(DB_FILE) # Connects Python to my SQLite database
    conn.row_factory = sqlite3.Row  # lets us write row["name"] instead of row[1]
    conn.executescript(TABLES) # This line sends those SQL instructions to SQLite
    return conn


def save_document(conn, name, text): # This creates a function that saves a document (database connection, document name, full document text)
    conn.execute( # Executes the following SQL Command
        "INSERT INTO documents (name, text) VALUES (?, ?) "
        "ON CONFLICT (name) DO UPDATE SET text = excluded.text",
        (name, text),
    )
    conn.commit() # Saves the changes permanently


def get_documents(conn): # Creates a function for getting all documents
    return conn.execute("SELECT * FROM documents ORDER BY id").fetchall() # fetchall gives all rows returned by the query


def save_parallel(conn, doc_a, doc_b, m): # This function saves one detected parallel, m is the match dictinary returned by the algorithm
    conn.execute(
        """INSERT INTO parallels (doc_a, doc_b, a_start, a_end, b_start, b_end, score, kind, words)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (doc_a, doc_b, a_start, a_end, b_start, b_end)
           DO UPDATE SET score = excluded.score, kind = excluded.kind, words = excluded.words""",
        (doc_a, doc_b, m["a_start"], m["a_end"], m["b_start"], m["b_end"],
         m["score"], m["kind"], m["words"]),
    )


def count_parallels(conn): # Function for counting how many parallel rows are in the database
    return conn.execute("SELECT COUNT(*) FROM parallels").fetchone()[0] # returns the count of the parallels


def get_parallels(conn): # This function retrieves all detected parallels
    return conn.execute(
        """SELECT p.*, a.name AS name_a, a.text AS text_a, b.name AS name_b, b.text AS text_b
           FROM parallels p
           JOIN documents a ON a.id = p.doc_a
           JOIN documents b ON b.id = p.doc_b
           ORDER BY p.score DESC, p.words DESC"""
    ).fetchall()


def set_status(conn, parallel_id, status): # This function changes the review status of a particular parallel
    conn.execute("UPDATE parallels SET status = ? WHERE id = ?", (status, parallel_id))
    conn.commit()
