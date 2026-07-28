# Context Vault (L1)

This is the **durable, human-curated memory** for the project — the layer that
stops fresh sessions (and other models) from re-deriving what you already
figured out. It's plain Markdown, so Claude, ChatGPT, or anything else can read
it, and Obsidian gives you backlinks + graph view on top.

## The one rule that makes this pay off

> A note earns its place only if reading it is **cheaper than re-deriving it from
> source**. Distill; don't dump.

If a note is just pasted code, delete it — vexp/L2 already serves code better. A
good note captures the *understanding*: how something works, why it's that way,
what bites you. That's the stuff source code doesn't tell you.

## Folders

| Folder | Holds | Read it when… |
|--------|-------|---------------|
| `00-Index/` | The map of the vault + project-wide MOCs (maps of content) | starting anywhere |
| `10-Architecture/` | System-level "how it fits together" deep-dives | a task crosses module boundaries |
| `20-Modules/` | One note per meaningful module/package | working inside that module |
| `30-Decisions/` | ADRs — why we chose X over Y | tempted to change a load-bearing choice |
| `40-Gotchas/` | Footguns, non-obvious constraints, "don't do this" | anywhere near the sharp edges |
| `50-Sessions/` | Dated logs of notable sessions + what changed | reconstructing recent history |
| `_templates/` | The note templates below | creating any new note |

## How it connects to the rest of the pipeline

- `CLAUDE.md` (L0) links *into* these folders by path. It stays tiny; the depth
  lives here.
- When Claude finishes a task, the "end-of-task ritual" is to distill new
  understanding into `20-Modules/`, `30-Decisions/`, or `40-Gotchas/`.
- Keep each note short and single-topic. Many small notes > one giant note:
  cheaper to load exactly what a task needs.

## Maintenance (manual, low effort)

- One note = one topic. Rename freely; use `[[wikilinks]]` to connect.
- Prune quarterly. A stale note is worse than no note — it makes the model
  confidently wrong.
- Every note starts with a **TL;DR** so it's useful even if only the top is read.
