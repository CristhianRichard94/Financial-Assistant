# Project Instructions

## Team

- `ux-designer` — user flow / information architecture.
- `ui-designer` — visual design and component specs, built on the UX flow.
- `software-engineer` — implements features/fixes/refactors.
- `qa-engineer` — reviews correctness and conformance to spec, and gives ship/no-ship verdicts.
- `security-engineer` — cybersecurity review after implementation: auth/access-control, secrets, injection, data exposure, dependency/config risk; gives ship/no-ship verdicts.

## Feature Development Workflow

Whenever the user requests a new feature or fix, do NOT stop after one implementation pass. Run the full workflow below without asking for permission to continue.

**1. Design (conditional — UI-facing work only)**
   - `ux-designer` defines the user flow: steps, decision points, and every non-happy-path state (loading, empty, error, edge cases).
   - `ui-designer` turns the UX flow into a visual/component spec (layout, states, responsive behavior, accessibility), consistent with the app's existing design system.
   - Skip both steps entirely for backend-only or infra changes — go straight to implementation.

**2. Branch** — Before any code is written, create a worktree and feature branch:
   ```
   git worktree add .worktrees/<feature-name> -b feature/<feature-name>
   ```
   All implementation work happens inside this worktree. Never implement directly on `main`.

**3. Implement** — Delegate to `software-engineer`. Give it the full feature request, any relevant context (which app, existing conventions, constraints), the UX/UI specs if produced, and which worktree/branch to work in.

**4. Review** — Every implementation pass gets two independent reviews, run in parallel against the same diff:
   - `qa-engineer` — bugs, missing edge cases, spec deviations, anything that would block shipping.
   - `security-engineer` — auth/access-control gaps, secret handling, injection risks, unsafe data exposure (e.g. missing RLS/access policies on new tables or storage), dependency/config risk.
   Run `security-engineer` on every feature/fix pass, not just ones that look security-sensitive — access-control and data-exposure gaps (e.g. a new table with no RLS) are easy to miss precisely when a change doesn't look security-related on the surface.

**5. Fix** — If either `qa-engineer` or `security-engineer` reports a blocking issue, send its exact findings back to `software-engineer` in the same worktree/branch. Do not summarize or soften either agent's findings — pass them through directly. If both report blocking issues, pass both through together.

**6. Repeat** steps 4–5 until both `qa-engineer` and `security-engineer` report no blocking issues, or until 4 review rounds have happened.

**7. Stop condition** — If after 4 rounds blocking issues remain, stop and report honestly to the user what's left, instead of declaring the feature done. Never claim something is "perfect" or "done" when known issues remain.

**8. Merge & cleanup** — Only after both `qa-engineer` and `security-engineer` give a clean pass:
   - Merge the feature branch into `main`.
   - Remove the worktree and branch:
   ```
   git worktree remove .worktrees/<feature-name>
   git branch -d feature/<feature-name>
   ```

**9. Summary** — Summarize what QA and security checked, and any follow-up (env vars, migrations, dependencies to install).

## Ground Rules

- Determine upfront whether the request needs `ux-designer`/`ui-designer` (UI-facing work) or is backend/infra-only (skip straight to `software-engineer`) — don't force design steps onto backend-only work, and don't skip them on UI work.
- Every feature or fix lives in its own worktree + branch. Never commit feature work directly to `main`.
- Worktrees are temporary — create them at step 2, delete them at step 8. Do not leave stale worktrees or branches behind.
- Keep iterating within a round rather than handing back a half-working feature to the user asking "does this look right?" unless you're genuinely blocked on a decision only the user can make.
- Every round of fixes should be scoped to QA's/security's actual findings, not a full rewrite.
- Each agent hands off a concrete, actionable artifact to the next (flow → visual spec → code → bug list) — favor specific, unambiguous handoffs over vague summaries.
- Code and all file content must be in English, regardless of the conversation language.
