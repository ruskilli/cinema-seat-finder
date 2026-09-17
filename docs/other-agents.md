# Using cinema-seat-finder in other agentic environments

The skill itself is just a markdown playbook
(`.claude/skills/cinema-seat-finder/SKILL.md`) that orchestrates plain
Python scripts — nothing about it is Claude-specific. Any coding agent
that can read a file and run shell commands can follow the same steps.

**GitHub Copilot** (Copilot Chat in VS Code, or the Copilot coding agent)

- Attach the playbook as context and ask your question, e.g. in VS Code
  Copilot Chat: `#file:.claude/skills/cinema-seat-finder/SKILL.md what's
  playing tonight?`
- To have it apply automatically to every chat in this repo, fold the
  SKILL.md steps into `.github/copilot-instructions.md`, which Copilot
  reads as repo-wide custom instructions.

**Gemini (Gemini CLI)**

- Gemini CLI auto-loads a `GEMINI.md` context file from the repo root, the
  same way Claude Code loads `CLAUDE.md`. Add a `GEMINI.md` at the project
  root that points at the playbook (e.g. `See
  .claude/skills/cinema-seat-finder/SKILL.md for the cinema-seat-finder
  workflow`), or copy its content in directly.
- For one-off use, you can also just paste the SKILL.md content into the
  prompt.

**Any other agent**

- Point it at `.claude/skills/cinema-seat-finder/SKILL.md` as its
  instructions and let it drive `scripts/discover_shows.py`,
  `scripts/filmgrail_checkout.py` + `scripts/filmgrail_zone_match.py`,
  `scripts/odeon_checkout.py` + `scripts/odeon_zone_match.py`,
  `scripts/ebillett_checkout.py` + `scripts/ebillett_zone_match.py`, and
  `scripts/nfkino_checkout.py` + `scripts/nfkino_zone_match.py` per the
  steps there — the scripts are plain Python 3 with no Claude Code
  dependency.
