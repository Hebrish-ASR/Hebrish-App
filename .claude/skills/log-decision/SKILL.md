---
name: log-decision
description: Record a decision about the Hebrish apps in the public decision log, planning/decisions.md, and keep planning/requests.md and planning/backlog.md consistent with it. Use when Daniel (or a contributor) settles a default, a trade-off, a scope call or a "not this way", says "log that decision", "note that we decided", "put that in the decision log", or when you implement something on a choice that someone made and that a future reader would otherwise have to guess.
---

# Log a decision

`planning/` is public (see `CLAUDE.md`). Everything written there is read by strangers and by
agents opening the repo cold.

## 1. Is it a decision?

Log it if a future reader would ask "why is it like this?": a default value, a naming choice,
a feature scoped in or out, an approach chosen over another, a reversal. Don't log routine
implementation detail; that goes in `desktop/docs/maintaining.md` or `android/docs/maintaining.md`.

## 2. Write the entry

Append at the **top** of the entries in `planning/decisions.md` (newest first). Id:
`D-<YYYY-MM-DD>-<nn>`, where `nn` continues that day's highest number. Never renumber or delete
an entry. A reversal is a new entry that says `Supersedes D-…`, and the old entry gets one line
added: `Superseded by D-…`.

```markdown
### D-2026-10-22-07: <the decision as a short statement>

- **Decision:** what was chosen, with the concrete identifiers (config keys, file paths, values).
- **Why:** the reason, including the constraint that settled it.
- **Alternatives:** what was considered and not chosen, and why. Omit if there were none.
- **By:** Daniel | <contributor handle, if they want credit> | agent (implementing D-…).
  Links: request R-…, backlog B-…/I-…, commit or tag.
```

Who decided matters. "Daniel" only for what he actually chose. A detail you chose while
implementing his decision is `agent, implementing D-…`.

## 3. Keep the other files consistent

- The request that led to it (`planning/requests.md`): set its Outcome to the backlog item.
- The backlog item (`planning/backlog.md`): link the decision id. Move it between *Now*, *Next*
  and *Ideas for future versions* if the decision changed its schedule, and update "Last updated".
- If the decision is about platform parity, check `docs/feature-parity.json` still agrees.

## 4. Public-repo hygiene (every time)

- No private names, emails, phone numbers, machine or host names, account ids, internal URLs, or
  the contents of private repositories. A user is "user" unless they asked to be credited.
- No credentials, ever, and no "this was in the private notes" paraphrases.
- Write plainly: dates absolute, no "we" (one-person project: "Daniel decided").

## 5. Commit

Commit the `planning/` change on its own, or alongside the code change it explains, with a
message like `planning: D-2026-10-22-07 <short>`. Stage only your files and commit in one
command, because other sessions work in this repo too. Push.
