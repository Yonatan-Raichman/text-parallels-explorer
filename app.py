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


def highlight(text, start, end, other_passage):
    """Show the passage in yellow, with some text around it.
    Words that do not appear in the other passage are shown in orange."""
    other_words = {w for w, _, _ in get_words(other_passage)}
    before = text[max(0, start - 250):start]
    after = text[end:end + 250]

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
    writer.writerow(["id", "text A", "verse A", "text B", "verse B", "type", "score", "words", "status"])
    for p in rows:
        writer.writerow([p["id"], p["name_a"], verse(p["text_a"], p["a_start"]), p["name_b"],
                         verse(p["text_b"], p["b_start"]), p["kind"], p["score"], p["words"], p["status"]])
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
kind_filter = st.sidebar.selectbox("Type", ["All", "exact", "near"])
status_filter = st.sidebar.selectbox("Status", ["All", "pending", "confirmed", "rejected"])
min_score = st.sidebar.slider("Minimum score", 0.0, 1.0, 0.0, 0.05)
search = st.sidebar.text_input("Passage contains (e.g. wilderness)")

# Keep only the parallels that pass every filter
shown = []
for p in database.get_parallels(conn):
    passage_a = p["text_a"][p["a_start"]:p["a_end"]]
    passage_b = p["text_b"][p["b_start"]:p["b_end"]]
    if doc_filter != "All" and doc_filter not in (p["name_a"], p["name_b"]):
        continue
    if kind_filter != "All" and p["kind"] != kind_filter:
        continue
    if status_filter != "All" and p["status"] != status_filter:
        continue
    if p["score"] < min_score:
        continue
    if search and search.lower() not in (passage_a + " " + passage_b).lower():
        continue
    shown.append(p)

# How many parallels does each pair of books share?
with st.expander("Overview: parallels per pair of books"):
    pairs = {}
    for p in shown:
        pair = f"{p['name_a']} – {p['name_b']}"
        pairs[pair] = pairs.get(pair, 0) + 1
    st.table([{"pair": k, "parallels": v} for k, v in sorted(pairs.items())])

# The list
st.subheader(f"{len(shown)} parallels")
st.dataframe(
    [{
        "id": p["id"],
        "text A": f"{p['name_a']} {verse(p['text_a'], p['a_start'])}",
        "text B": f"{p['name_b']} {verse(p['text_b'], p['b_start'])}",
        "type": p["kind"],
        "score": f"{p['score']:.0%}",
        "words": p["words"],
        "status": p["status"],
        "passage": p["text_a"][p["a_start"]:p["a_end"]][:80],
    } for p in shown],
    hide_index=True, use_container_width=True, height=300,
)
st.download_button("Download as CSV", to_csv(shown), "parallels.csv", "text/csv")

if not shown:
    st.stop()

# The side-by-side view
st.subheader("Compare side by side")
labels = {p["id"]: f"#{p['id']}  {p['name_a']} {verse(p['text_a'], p['a_start'])}  ↔  "
                   f"{p['name_b']} {verse(p['text_b'], p['b_start'])}  ({p['kind']}, {p['score']:.0%})"
          for p in shown}
chosen_id = st.selectbox("Choose a parallel", list(labels), format_func=lambda i: labels[i])
p = next(p for p in shown if p["id"] == chosen_id)

passage_a = p["text_a"][p["a_start"]:p["a_end"]]
passage_b = p["text_b"][p["b_start"]:p["b_end"]]
left, right = st.columns(2)
with left:
    st.markdown(f"**{p['name_a']} {verse(p['text_a'], p['a_start'])}**")
    st.markdown(highlight(p["text_a"], p["a_start"], p["a_end"], passage_b), unsafe_allow_html=True)
with right:
    st.markdown(f"**{p['name_b']} {verse(p['text_b'], p['b_start'])}**")
    st.markdown(highlight(p["text_b"], p["b_start"], p["b_end"], passage_a), unsafe_allow_html=True)

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
