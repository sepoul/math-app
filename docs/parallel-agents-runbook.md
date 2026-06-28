# Runbook — parallel autonomous Claude Code workers (one repo, N issues)

Reproducible recipe for running several independent GitHub issues at once with
native Claude Code + Git, no dispatcher/cron/Action/webhook. Two modes:

- **Mode A — Agent View (interactive):** you dispatch + watch from one screen.
- **Mode B — Headless control-plane (scriptable):** one process fans out N
  autonomous workers; **this is what lets one operator reproduce it solo**.

Each worker is a full, independent Claude Code session with its **own git
worktree** (own branch + checkout), so workers never edit over each other or
your main checkout. Work lands as **review-gated PRs** you approve.

---

## 0. Prerequisites (one time)

```bash
# Install the standalone CLI so `claude` is on PATH (separate from the VS Code
# extension). Same login/credentials; installs to ~/.local/bin/claude.
curl -fsSL https://claude.ai/install.sh | bash
claude --version          # need >= 2.1.139 for Agent View
```

## 1. Repo prep (one time, committed)

- **`.worktreeinclude`** at repo root — copies gitignored files each worker
  needs into its fresh worktree (`.gitignore` syntax):
  ```
  math-ui/.env.local
  ```
- **`.gitignore`** — add `.claude/worktrees/` so worker checkouts don't show as
  untracked in your main tree.

Both are already committed in this repo.

---

## Mode A — Agent View (interactive)

```bash
cd <repo> && claude        # first time per dir: accept the trust dialog, then exit
claude agents              # opens the dashboard
```
In the dashboard: type a task prompt + `Enter` → each prompt starts its **own**
background session (a new row). `Space` peek/reply, `Enter` attach, `←` detach
(keeps running). A green `PR #N` badge appears when a worker opens its PR.

Shell equivalents: `claude --bg "<task>"`, `claude attach <id>`,
`claude logs <id>`, `claude stop <id>`, `claude agents --json [--all]`.

> Note: `--bg` with `bypassPermissions` requires accepting a disclaimer once:
> `claude --dangerously-skip-permissions` interactively, then exit. After that,
> background workers can run unattended.

---

## Mode B — Headless control-plane (scriptable, solo-reproducible)

`claude -p` (print/automation mode) runs a task to completion non-interactively
and **skips the bypass disclaimer**, so it needs no one-time interactive accept.
Give each worker its **own** `--worktree` for file isolation.

### B.1 Write one prompt file per issue

Keep prompts in files (no shell-escaping headaches). Each prompt should:
read the issue with `gh issue view <N>`, implement strictly in scope, run the
package's tests, commit, push, open a PR with `gh pr create` (referencing the
issue + epic), and **not** merge / deploy / touch other issues.

```bash
mkdir -p /tmp/agent-prompts
cat > /tmp/agent-prompts/issue-15.txt <<'EOF'
You are an autonomous coding worker on the sepoul/math-app repo. You are ALREADY
in an isolated git worktree on your own branch — do NOT create/switch worktrees.
Implement GitHub issue #15: read it with `gh issue view 15` (+ `gh issue view 14`
for epic context), implement strictly in scope, run the math-notes package tests,
commit on the current branch, push, and open a PR with `gh pr create` referencing
#15 and #14. Do not work on other issues, do not deploy/restart any platform, do
not merge. End by printing the PR URL prefixed "PR_URL: ".
EOF
# ...one file per issue (issue-16.txt, etc.)
```

### B.2 Launch one worker per issue (parallel, isolated)

```bash
cd <repo>
claude -p --dangerously-skip-permissions --worktree issue-15 \
  < /tmp/agent-prompts/issue-15.txt > /tmp/agent-prompts/log-15.txt 2>&1 &

claude -p --dangerously-skip-permissions --worktree issue-16 \
  < /tmp/agent-prompts/issue-16.txt > /tmp/agent-prompts/log-16.txt 2>&1 &
```

`--worktree issue-15` → checkout at `.claude/worktrees/issue-15` on branch
`worktree-issue-15`, branched from `origin/HEAD` (clean main). `&` backgrounds
each OS process so they run concurrently.

### B.3 Scale to N issues with a loop

```bash
for N in 15 16 17 19; do          # lead with independent issues
  claude -p --dangerously-skip-permissions --worktree "issue-$N" \
    < "/tmp/agent-prompts/issue-$N.txt" > "/tmp/agent-prompts/log-$N.txt" 2>&1 &
done
wait    # optional: block until all finish
```

### B.4 Monitor (the "are they actually parallel?" check)

```bash
git worktree list                 # one .claude/worktrees/issue-N per live worker
gh pr list --state open           # PRs appear as workers finish
tail -f /tmp/agent-prompts/log-15.txt   # follow one worker
git -C .claude/worktrees/issue-15 log --oneline -5   # what a worker committed
```
Tell-tale of parallelism: multiple `.claude/worktrees/issue-*` dirs and multiple
worker PIDs alive at once. (Plain `claude` = 1 lane; this = N lanes.)

### B.5 Review, merge, clean up

```bash
gh pr view <PR#> --web             # review from your MAIN checkout
gh pr checks <PR#>
gh pr merge <PR#> --squash --delete-branch
git worktree remove .claude/worktrees/issue-15   # -p worktrees aren't auto-removed
```

---

## The control-plane loop (wave-based, dependency-aware)

How to drive a whole epic end-to-end — the pattern we actually ran:

1. **Decompose** the feature into an epic + independent child issues with
   explicit contracts/seams (so stories parallelize). File with `gh`.
2. **Sequence by dependency.** A worker branches from `origin/main`, so it only
   sees code that's already **merged**. Group issues into waves:
   - **Wave 1** — independent contract-owners (no deps) → fire in parallel.
   - **Wave N** — dependents → fire only after their contracts are merged.
   Don't fan dependents out off a stale main; you'll get conflict hell.
3. **Dispatch** each issue's worker headless + isolated (Mode B), one prompt
   file per issue.
4. **Review before merge (non-negotiable).** Read each PR's diff / run a review;
   workers never merge or deploy themselves. Merge with
   `gh pr merge <N> --squash --delete-branch`, then `git worktree remove` the
   spent worktree.
5. **Sync + next wave.** `git pull` main so the next wave branches from the
   merged base, then fire the dependents.

**Cross-repo / operator steps a worker CANNOT do** (e.g. an SDK regen that needs
the running platform + an npm publish in `../ai-platform`): don't block the wave
on them. Have the dependent worker build against **local types** mirroring the
new contract + leave a PR note, and do the operator step + type-swap later.

Worked example (epic #14, daily-notes adaptive synthesis):

| Wave | Issues | Note |
| --- | --- | --- |
| A | #15 NoteMagnitude, #16 prompt | base contracts → merge first |
| B | #17 SynthesisPlan, #19 enriched schema | parallel, off merged main |
| C | #18 adaptive synth, #21 eval | after B merges |
| D | #20 UI | last — local types now, SDK swap later |

---

## Pilot room — watch every lane (Agent View)

You don't build this — it ships natively. **Agent View** (`claude agents`) is
one full-screen table of all background sessions grouped by **Needs input /
Working / Completed**, with live state icons, `PR #N` badges, peek (`Space`),
and attach (`Enter`). Scope it to one repo:

```bash
claude agents --cwd <repo>      # mission control for this project
claude agents --json            # same data as a feed (for a custom dashboard)
```

**Visibility rule (important):**

| Launch | Hosted by | Shows in `claude agents`? | Monitor with |
| --- | --- | --- | --- |
| `claude --bg …` (Mode A) | per-user supervisor | **Yes** — appears as a row | the room itself |
| `claude -p … &` (Mode B) | plain OS process | **No** | `git worktree list`, `gh pr list`, `tail` |

So to get **autonomous workers _and_ the pilot room**, dispatch with `--bg`
(not `-p`). `--bg` + `bypassPermissions` needs the one-time disclaimer accept:

```bash
claude --dangerously-skip-permissions          # once, ever: accept, then /exit
# then each worker becomes a supervisor session that appears in the room:
claude --bg --name "w-issue-15" --permission-mode bypassPermissions \
  "$(cat /tmp/agent-prompts/issue-15.txt)"
```

Now `claude agents` is your room — you watch all lanes live while the control
plane (or you) dispatches. Headless `-p` (Mode B) stays the right choice when you
want zero interactive steps and don't need the visual room.

---

## Hands-off observability with hooks (pump worker activity to one place)

Hooks are the official lifecycle mechanism, and they **fire in headless `-p`
workers** — so you can stream every worker's activity to one feed without
`--bg`, without the disclaimer, without being in the loop.

Verified facts:
- Hooks live in **settings files, NOT the `--settings` flag** (that flag can't
  add hooks). For workers in worktrees the reliable spots are **user-level
  `~/.claude/settings.json`** (applies everywhere, no commit) or a **committed
  `.claude/settings.json`** (push it so the worktree checkout has it).
- In `-p` mode, `SessionStart` / `UserPromptSubmit` / `PreToolUse` /
  `PostToolUse` / `Stop` / `SessionEnd` fire. (`Notification` is for
  interactive/`--bg`; a headless bypass worker has no prompts to wait on.)
- **Env-gate** the hook so it's dormant for your normal sessions and only writes
  for fleet workers launched with the gate set.

A `PostToolUse` activity feed + a `SessionEnd` done-marker, gated on `$FLEET_LOG`:

```jsonc
// ~/.claude/settings.json  (or committed .claude/settings.json)
{
  "hooks": {
    "PostToolUse": [{ "hooks": [{ "type": "command",
      "command": "test -n \"$FLEET_LOG\" && jq -r '\"[\\(.cwd|split(\"/\")|last)] \\(.tool_name)\"' >> \"$FLEET_LOG\" || true" }]}],
    "SessionEnd": [{ "hooks": [{ "type": "command",
      "command": "test -n \"$FLEET_LOG\" && jq -r '\"[\\(.cwd|split(\"/\")|last)] DONE\"' >> \"$FLEET_LOG\" || true" }]}]
  }
}
```

Launch workers with the gate set, then tail the unified feed:

```bash
FLEET_LOG=/tmp/agent-prompts/fleet.log \
  claude -p --dangerously-skip-permissions --worktree issue-15 < issue-15.txt &
tail -f /tmp/agent-prompts/fleet.log      # every worker's tool calls, one stream
```

Want a "ping me only when needed" feel? Point the `SessionEnd` (or a `Stop`)
hook at a desktop notification or Slack webhook instead of a log file:

```bash
osascript -e 'display notification "worker done" with title "fleet"'   # macOS
```

Simpler, no hooks: relaunch workers with `--output-format stream-json --verbose`
so each redirected log is already a live activity stream you can `tail -f`.

---

## Caveats (math-app specific)

- **Quota scales with N** — N parallel workers burn subscription usage ~N×.
- **Shared singleton platform** (`../ai-platform`, :8000) is **not** per-worktree.
  Workers should do code + unit tests only; **serialize** anything that needs the
  live platform (`aiplatform deploy`, `docker restart ...`, UI smoke) through your
  main session.
- **Dev-server port** — `math-ui` runs `next dev` on **:3000**; don't have many
  workers start it. Keep the one live UI in your main checkout.
- **Per-worktree setup** — `node_modules/`, `.venv/` aren't shared; a worker that
  runs tests installs its own deps in its worktree.
- **Contract order** — start with independent owners (#15, #17, #19); bring
  dependents (#16, #18, #20, #21) online as contracts land.
- **Deleting a worker's worktree discards uncommitted changes** — push/PR first.

---

## What this repo's pilot ran (concrete example)

```bash
# from repo root, two workers in parallel, headless + isolated:
claude -p --dangerously-skip-permissions --worktree issue-15 < prompt15.txt &
claude -p --dangerously-skip-permissions --worktree issue-16 < prompt16.txt &
# monitored with: git worktree list ; gh pr list ; tail log15.txt log16.txt
```
