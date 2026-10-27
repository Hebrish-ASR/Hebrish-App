from hebrish.engine import seam_split

TOKENS = [" the", " question", ".", " in", "div", "idual", " cases"]
TIMES = [0.0, 0.32, 0.8, 2.96, 3.04, 3.12, 3.44]


def test_word_timed_across_the_split_stays_whole():
    # " in" sits in the frame before at=3.0: the old split kept "dividual cases"
    assert "".join(TOKENS[seam_split(TOKENS, TIMES, 3.0):]).strip() == "individual cases"


def test_split_on_a_word_start_is_unchanged():
    assert seam_split(TOKENS, TIMES, 2.9) == 3


def test_context_mark_stays_with_the_context():
    assert seam_split(TOKENS, TIMES, 0.5) == 2   # "." has no space and is not a word piece


def test_nothing_after_the_split():
    assert seam_split(TOKENS, TIMES, 9.0) == len(TOKENS)


def test_apostrophe_piece_continues_the_word():
    assert seam_split([" ok", " it", "'s", " fine"], [0.0, 1.9, 2.05, 2.3], 2.0) == 1
