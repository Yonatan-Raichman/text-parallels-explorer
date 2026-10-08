"""The web page. Start it with:   streamlit run app.py"""
import csv
import html
import io

import streamlit as st

import database
import detect
from matcher import get_words

st.set_page_config(page_title="Text Parallels Explorer", layout="wide")


@st.cache_resource  # Streamlit runs this only once, when the app starts
def find_parallels_once():
    detect.run()


find_parallels_once()
conn = database.connect()


# ---------- small helper functions ----------

def verse(text, position):
    """Return the verse number (like '3:1') of the line that contains this position."""
    line_start = text.rfind("\n", 0, position) + 1
    return text[line_start:].split(" ", 1)[0]


def side(p, letter):
    """Everything about one side (a or b) of a parallel, in one small dictionary."""
    text, start, end = p[f"text_{letter}"], p[f"{letter}_start"], p[f"{letter}_end"]
    return {"book": p[f"name_{letter}"], "text": text, "start": start, "end": end,
            "ref": f"{p[f'name_{letter}']} {verse(text, start)}", "passage": text[start:end]}


def highlight(s, other_passage):
    """Show the passage in yellow, with some text around it.
    Words that do not appear in the other passage are shown in orange."""
    text, start, end = s["text"], s["start"], s["end"]
    other_words = {w for w, _, _ in get_words(other_passage)}
    before = text[max(0, start - 250):start]
    after = text[end:end + 250]
    # don't cut a word in half at the edges
    if start > 250 and " " in before:
        before = before[before.find(" ") + 1:]
    if end + 250 < len(text) and " " in after:
        after = after[:after.rfind(" ")]

    middle = ""
    position = start
    for word, w_start, w_end in get_words(text[start:end]):
        w_start, w_end = start + w_start, start + w_end
        middle += html.escape(text[position:w_start])          # spaces and punctuation
        if word in other_words:
            middle += html.escape(text[w_start:w_end])
        else:
            middle += f"<span class='diff'>{html.escape(text[w_start:w_end])}</span>"
        position = w_end
    middle += html.escape(text[position:end])

    return (f"<div class='passage'>…{html.escape(before)}"
            f"<span class='match'>{middle}</span>{html.escape(after)}…</div>")


def to_csv(rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["id", "text A", "text B", "type", "score", "words", "status"])
    for p in rows:
        writer.writerow([p["id"], p["a"]["ref"], p["b"]["ref"], p["kind"], p["score"], p["words"], p["status"]])
    return out.getvalue()


st.markdown("""
<style>
.passage { font-family: Georgia, serif; font-size: 17px; line-height: 1.7; color: #888; white-space: pre-wrap; }
.match { background: #fff3a0; color: #111; }
.diff { background: #ffb870; }
</style>
""", unsafe_allow_html=True)


# ---------- the page ----------

st.title("Text Parallels Explorer")

# Filters in the left sidebar
documents = [d["name"] for d in database.get_documents(conn)]
st.sidebar.header("Filters")
doc_filter = st.sidebar.selectbox("Document", ["All"] + documents)
if doc_filter == "All":
    other_filter = "All"
else:  # a second drop-down, to look at one pair of books, e.g. Matthew and Mark
    other_filter = st.sidebar.selectbox("Compared with", ["All"] + [d for d in documents if d != doc_filter])
kind_filter = st.sidebar.selectbox("Type", ["All", "exact", "near"])
status_filter = st.sidebar.selectbox("Status", ["All", "pending", "confirmed", "rejected"])
min_score = st.sidebar.slider("Minimum score", 0.0, 1.0, 0.0, 0.05)
search = st.sidebar.text_input("Passage contains (e.g. wilderness)")

# Keep only the parallels that pass every filter
shown = []
for row in database.get_parallels(conn):
    p = {"id": row["id"], "kind": row["kind"], "score": row["score"], "words": row["words"],
         "status": row["status"], "a": side(row, "a"), "b": side(row, "b")}
    books = (p["a"]["book"], p["b"]["book"])
    if doc_filter != "All" and doc_filter not in books:
        continue
    if other_filter != "All" and other_filter not in books:
        continue
    if kind_filter != "All" and p["kind"] != kind_filter:
        continue
    if status_filter != "All" and p["status"] != status_filter:
        continue
    if p["score"] < min_score:
        continue
    if search and search.lower() not in (p["a"]["passage"] + " " + p["b"]["passage"]).lower():
        continue
    if doc_filter != "All" and p["b"]["book"] == doc_filter:
        p["a"], p["b"] = p["b"], p["a"]  # the chosen book is always shown first (on the left)
    shown.append(p)

# How many parallels does each pair of books share?
with st.expander("Overview: parallels per pair of books"):
    pairs = {}
    for p in shown:
        pair = f"{p['a']['book']} – {p['b']['book']}"
        pairs[pair] = pairs.get(pair, 0) + 1
    st.dataframe([{"pair": k, "parallels": v} for k, v in sorted(pairs.items(), key=lambda kv: -kv[1])],
                 hide_index=True)

# The list. Clicking a row selects it for the side-by-side view below.
st.subheader(f"{len(shown)} parallels")
st.caption("Click a row (the box at its left edge) to compare it side by side below. Click a column title to sort.")
table = st.dataframe(
    [{
        "id": p["id"],
        "text A": p["a"]["ref"],
        "text B": p["b"]["ref"],
        "type": p["kind"],
        "score (%)": round(p["score"] * 100),  # a number, so the table sorts it correctly
        "words": p["words"],
        "status": p["status"],
        "passage": p["a"]["passage"][:80],
    } for p in shown],
    hide_index=True, use_container_width=True, height=300,
    on_select="rerun", selection_mode="single-row",
    # a new key when the filters change, so an old selection never points at the wrong row
    key=f"table-{doc_filter}-{other_filter}-{kind_filter}-{status_filter}-{min_score}-{search}",
)
st.download_button("Download as CSV", to_csv(shown), "parallels.csv", "text/csv")

if not shown:
    st.stop()

# The side-by-side view: the clicked row, or the first row if nothing is clicked yet
selected = table.selection.rows
p = shown[selected[0]] if selected and selected[0] < len(shown) else shown[0]

st.subheader("Compare side by side")
st.write(f"**#{p['id']}**: {p['a']['ref']} ↔ {p['b']['ref']} ({p['kind']}, {p['score']:.0%})"
         + ("" if selected else "  ·  *click a row in the table to choose another*"))
left, right = st.columns(2)
with left:
    st.markdown(f"**{p['a']['ref']}**")
    st.markdown(highlight(p["a"], p["b"]["passage"]), unsafe_allow_html=True)
with right:
    st.markdown(f"**{p['b']['ref']}**")
    st.markdown(highlight(p["b"], p["a"]["passage"]), unsafe_allow_html=True)

st.caption("Yellow = the matching passage. Orange = words that are not in the other passage.")

# Review buttons
st.write(f"Current status: **{p['status']}**")
b1, b2, b3 = st.columns([1, 1, 6])
if b1.button("✓ Confirm"):
    database.set_status(conn, p["id"], "confirmed")
    st.rerun()
if b2.button("✗ Reject"):
    database.set_status(conn, p["id"], "rejected")
    st.rerun()