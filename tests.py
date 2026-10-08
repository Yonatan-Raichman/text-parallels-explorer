"""Simple checks that the important parts work. Run with:   python tests.py"""
import os
import tempfile

os.environ["DB_FILE"] = os.path.join(tempfile.mkdtemp(), "test.db")  # use a throwaway database

import database
import matcher

MARK = "1:3 The voice of one crying in the wilderness, Prepare ye the way of the Lord, make his paths straight."
JOHN = "1:23 He said, I am the voice of one crying in the wilderness, Make straight the way of the Lord, as said the prophet Esaias."
OTHER = "1:1 In the beginning God created the heaven and the earth."


def test_exact_match():
    result = matcher.find_parallels("Some words here. " + MARK, "Other words. " + MARK)
    assert len(result) == 1 and result[0]["kind"] == "exact"


def test_near_match():
    result = matcher.find_parallels(MARK, JOHN)
    assert len(result) == 1 and result[0]["kind"] == "near"
    assert 0.5 <= result[0]["score"] < 1


def test_no_match_in_unrelated_texts():
    assert matcher.find_parallels(MARK, OTHER) == []


def test_positions_point_at_the_right_text():
    m = matcher.find_parallels(MARK, JOHN)[0]
    assert MARK[m["a_start"]:m["a_end"]].startswith("The voice of one crying")
    assert JOHN[m["b_start"]:m["b_end"]].startswith("the voice of one crying")


def test_running_twice_creates_no_duplicates_and_keeps_review():
    conn = database.connect()
    database.save_document(conn, "Mark", MARK)
    database.save_document(conn, "John", JOHN)
    for _ in range(2):  # save the same results twice
        for m in matcher.find_parallels(MARK, JOHN):
            database.save_parallel(conn, 1, 2, m)
        conn.commit()
        if database.count_parallels(conn) == 1:
            database.set_status(conn, 1, "confirmed")
    assert database.count_parallels(conn) == 1
    assert database.get_parallels(conn)[0]["status"] == "confirmed"


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("OK  ", name)
    print("All tests passed")
