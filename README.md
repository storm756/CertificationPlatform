# Start here

This folder is everything needed to build the **Cyber First Response certification platform** from scratch.

1. Clone `github.com/storm756/CertificationPlatform` to **D:\CertificationPlatform** (not OneDrive or the Desktop: syncing breaks things).
2. Copy everything in this folder into the repo root, keeping the layout (`CLAUDE.md` at the root, the rest under `docs/`). Commit.
3. Open the repo in Claude Code. Do the stages in `docs/build-stages.md` **in order**, one fresh Claude session per stage, starting each one with that stage's prompt.
4. After each stage, open a PR. It gets reviewed before merging.

| File | What it is |
| --- | --- |
| `CLAUDE.md` | Rules Claude follows in every session (it is loaded automatically) |
| `docs/architecture.md` | The full design: what to build and how. The source of truth. |
| `docs/decisions.md` | Product decisions that are settled. Don't change them without asking. |
| `docs/build-stages.md` | Stages 0–10, with tasks, a "done when" list and the prompt for each |
| `docs/legacy-sources.md` | Where the old content (questions, lessons, films) lives and how to import it |

The old Moodle version is **reference only**. Nothing from its code is reused, only its content.
