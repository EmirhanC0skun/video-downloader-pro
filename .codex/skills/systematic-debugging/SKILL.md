# Systematic Debugging

Use this skill for bugs, crashes, regressions, test failures, unexpected output, or behavior that differs from the user's expectation.

## Iron Rule

Do not apply speculative fixes before isolating a plausible root cause with evidence.

## Procedure

1. Read the complete relevant error, traceback, logs, or failing assertion.
2. Reproduce the issue consistently when the environment allows it.
3. Trace the failing path through the actual code.
4. Form one testable hypothesis.
5. Change or instrument one meaningful variable at a time.
6. Confirm or reject the hypothesis with evidence.
7. Fix the root cause, not merely the visible symptom.
8. Add a meaningful regression test when practical.
9. Re-run targeted verification and then broader relevant checks as warranted.

## Circuit Breaker

If three well-founded hypotheses fail to explain the same root problem:

- stop stacking speculative patches,
- remove temporary experiments/instrumentation that should not remain,
- summarize what was ruled out,
- report the actual blocker and the next evidence needed.

## Exception Discipline

Do not silence failures with bare/logless exception handling.

If an exception is intentionally tolerated, preserve diagnostic information.

## Guardrails

- Do not report a hypothesis as fact before testing it.
- Do not weaken tests merely to make them pass.
- Do not mock away the behavior whose correctness is under investigation.
- User instructions and `AGENTS.md` outrank this skill.
