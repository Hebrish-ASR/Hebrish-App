"""hebrish.titles (B-75): the title model's reply made into a plain, length-limited title."""

from hebrish import titles


def test_clean_json_and_emojis():
    assert titles.clean('{"title": "🥛 Milk & Shufersal Order"}') == "Milk & Shufersal Order"
    assert titles.clean('{"title": "Vaad Bayit Elevator Repair 🛠️"}') == "Vaad Bayit Elevator Repair"
    assert titles.clean('```json\n{ "title": "🎙️ Podcast Development & AI" }\n```') == "Podcast Development & AI"


def test_clean_plain_and_broken():
    assert titles.clean('"Hebrish release notes."') == "Hebrish release notes"
    assert titles.clean('{"title": "Half a tit') == "Half a tit"
    assert titles.clean('{"title": "🤖🤖"}') == ""
    assert titles.clean("") == ""


def test_fit():
    t = titles.fit("Notes on the Hebrish release and the Android floating mic", 30)
    assert len(t) <= 30 and t == "Notes on the Hebrish release"
    assert titles.fit("Elevator repairs & arnona", 20) == "Elevator repairs"
    assert titles.limit("abc") == 60 and titles.limit(3) == titles.MIN_CHARS and titles.limit(500) == 120


class Fake:
    def __init__(self, reply=None, fail=False):
        self.reply, self.fail, self.prompt = reply, fail, None

    def complete(self, prompt, n, timeout, stop=()):
        self.prompt = prompt
        if self.fail:
            raise TimeoutError("slow")
        return self.reply, "eos"


def test_make():
    f = Fake('{"title": "🛒 Makolet Shopping List"}')
    assert titles.make("word " * 5000, f, 60) == "Makolet Shopping List"
    assert f.prompt.startswith("<start_of_turn>user\n### Task:") and f.prompt.endswith("<start_of_turn>model\n")
    assert len(f.prompt.split("USER: ")[1].split("\n")[0].split()) == titles.INPUT_WORDS
    assert titles.make("text", Fake(fail=True)) is None
    assert titles.make("text", Fake('{"title": "✨"}')) is None
    assert titles.make("  ", Fake("x")) is None
