---
name: queue-sprint
description: Queue a batch of Hebrish feature requests, fixes and ideas into the per-platform sprints in planning/backlog.md (desktop = Ubuntu + Windows; Android), logging each in planning/requests.md and adding parity follow-ups. Use when Daniel or a contributor sends several asks at once ("queue this for the sprint", "add these to the Android sprint", "for the next Ubuntu version…", "the other thing I'd queue is…"), often in the middle of other work, and they should be recorded rather than built right now.
---

# Queue a batch into the sprints

Requests often arrive in batches, mid-task, dictated, and spanning several platforms. The job is
to record every one faithfully and put it in the right place. It is **not** to build it, unless
the person says to. Keep working on the current task afterwards.

`planning/` is public: follow the hygiene rules in the `log-decision` skill (no private details,
users unnamed unless they ask for credit).

## 1. Split the batch

Break the message into separate asks. One ask is one thing that could ship on its own. For each,
note:
- **Platform(s):** desktop (Ubuntu + Windows, shared code in `desktop/`), Android, or all. "The
  Ubuntu app" means desktop; Windows comes with it.
- **Kind:** feature, fix, design, or idea (wanted but explicitly "for later").
- **The ask in one line**, in plain words. Keep the person's specifics: numbers, defaults,
  names, and "default should be…" details. Don't round them off or reinterpret them. If a dictated
  phrase is ambiguous, write the most likely reading and flag it in your reply.

## 2. Log the requests

`planning/requests.md`: one row per ask, newest at the top, id `R-<date>-<n>` continuing that
day's numbers. "From" is `Daniel`, `user`, or an issue link.

## 3. Place each one

`planning/backlog.md`:
- Into **Sprint: desktop** or **Sprint: Android** (a new `B-<n>` id, continuing the highest
  number in the file), status `planned`. An "all platforms" ask gets an item in each sprint.
- Explicitly later, or too big or risky for now → **Ideas for future versions** (`I-<n>`).
- Already in the backlog → don't duplicate: add the new request id to the existing item, and
  any new detail.
- **Parity:** when an item lands on one platform, check whether the other sprint needs a
  matching item (`docs/feature-parity.json` is the matrix). Add it, and mark it "(parity with B-…)".
- Order inside a sprint: what was asked first or what blocks others, then the rest. The
  release item stays last.

Link each request's Outcome to its backlog anchor. Update "Last updated".

## 4. Decisions

If the batch settles a choice (a default, a scope call, "for later"), log it with the
`log-decision` skill.

## 5. Commit and report

Stage only `planning/` (other sessions commit here too; stage and commit in one command):
`planning: queue R-… into the sprints`. Push. In the reply, list what went where in a few
lines, and anything you interpreted.
