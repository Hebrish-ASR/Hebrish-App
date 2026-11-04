"""hebrish.agent_skills (B-87): the skills shipped with the app."""

import re

from hebrish import agent_skills, local_api


def test_bundled_skills_are_complete():
    names = {p.name for p in agent_skills.bundled()}
    assert {"update-hebrish", "read-hebrish-history", "fix-hebrish-mistranscriptions",
            "transcribe-with-hebrish"} <= names
    for p in agent_skills.bundled():
        assert re.match(rf"---\nname: {p.name}\n", (p / "SKILL.md").read_text(encoding="utf-8"))


def test_skills_only_use_real_routes():
    known = {re.sub(r"\{.*", "", p).rstrip("/") for _, p, _, _ in local_api.ROUTES} | {"/v1"}
    for p in agent_skills.bundled():
        for path in re.findall(r"127\.0\.0\.1:8723(/[\w/]*)", (p / "SKILL.md").read_text(encoding="utf-8")):
            path = path.rstrip("/")
            assert path in known or path.startswith("/v1/history/"), (p.name, path)


def test_install_only_into_agents_present(tmp_path):
    (tmp_path / ".claude").mkdir()
    done = agent_skills.install(tmp_path)
    assert list(done) == ["Claude Code"]
    assert (tmp_path / ".claude/skills/update-hebrish/SKILL.md").is_file()
    assert not (tmp_path / ".codex").exists()
    assert "installed for Claude Code" in agent_skills.report(done)


def test_install_with_no_agent(tmp_path):
    assert agent_skills.install(tmp_path) == {}
    assert "No coding agent" in agent_skills.report({})
