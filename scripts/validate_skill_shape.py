#!/usr/bin/env python3
"""Validate the repository's Codex skill package shape."""

from __future__ import annotations

import re
from pathlib import Path


def main() -> int:
    skill = Path("skills/paper-interpretation")
    skill_md = skill / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")

    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    end = text.find("\n---", 4)
    assert end != -1, "SKILL.md frontmatter is not closed"

    frontmatter = text[4:end]
    assert re.search(r"^name:\s*paper-interpretation\s*$", frontmatter, re.M)
    assert re.search(r"^description:\s*.+", frontmatter, re.M)

    for required in ["agents", "references", "scripts", "templates"]:
        assert (skill / required).exists(), f"missing {required}/"

    version = (skill / "VERSION").read_text(encoding="utf-8").strip()
    root_version = Path("VERSION").read_text(encoding="utf-8").strip()
    assert version == root_version, "root VERSION and skill VERSION differ"
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), "VERSION must be semver"

    print(f"Skill shape is valid: paper-interpretation {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
