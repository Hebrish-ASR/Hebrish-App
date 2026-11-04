"""Agent skills shipped with the app (B-87): copies of the desktop skills from the public repo
Hebrish-ASR/Hebrish-Agent-Skills in hebrish/data/agent-skills/, installed by Settings → Local API or
`hebrish --install-agent-skills`. Copied only into agents found on this computer: a home folder
with no ~/.codex is left without one. Re-installing overwrites these skills and nothing else."""

import shutil
from pathlib import Path

SOURCE = Path(__file__).parent / "data" / "agent-skills"
AGENTS = {"Claude Code": ".claude", "Codex": ".codex", "Gemini CLI": ".gemini"}


def bundled() -> list[Path]:
    return sorted(p for p in SOURCE.iterdir() if (p / "SKILL.md").is_file()) if SOURCE.is_dir() else []


def install(home: Path | None = None) -> dict[str, Path]:
    """Copy every bundled skill into each agent present. Returns agent name -> skills folder."""
    home = home or Path.home()
    done = {}
    for name, folder in AGENTS.items():
        if not (home / folder).is_dir():
            continue
        root = home / folder / "skills"
        for skill in bundled():
            (root / skill.name).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(skill / "SKILL.md", root / skill.name / "SKILL.md")
        done[name] = root
    return done


def report(done: dict[str, Path]) -> str:
    if not done:
        return ("No coding agent found (Claude Code, Codex, Gemini CLI). The skills are also at "
                "github.com/Hebrish-ASR/Hebrish-Agent-Skills.")
    return f"{len(bundled())} skills installed for " + ", ".join(done) + "."
