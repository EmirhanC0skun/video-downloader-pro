# Supervisor

Use this skill for complex, multi-step work or when independent tasks can be parallelized.

## Goal

Protect the overall architecture, scope, quality bar, and completion criteria while delegating only well-bounded subproblems.

## Procedure

1. Establish the current repository state and the user's actual goal.
2. Map the high-level execution path and identify independent subproblems.
3. Delegate only when it improves speed or quality.
4. Give each subtask:
   - exact scope,
   - relevant files/modules,
   - constraints,
   - a measurable "done when" condition.
5. Do not accept a subtask result blindly.
6. Review resulting diffs and run appropriate tests/checks before integration.
7. Resolve conflicts by preserving user intent and minimizing unrelated changes.

## Guardrails

- Keep the main task ledger and architectural context at the supervisor level.
- Do not delegate vague "investigate everything" tasks.
- Do not duplicate work across subagents.
- Do not use delegation as a substitute for verification.
- User instructions and `AGENTS.md` outrank this skill.
