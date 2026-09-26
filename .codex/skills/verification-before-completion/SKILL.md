# Verification Before Completion

Use this skill after implementation, bug fixes, refactors, configuration changes, sync changes, or packaging changes.

## Iron Rule

No completion claim without fresh, relevant verification evidence.

## Verification Ladder

Choose checks proportional to the change:

1. Syntax/static validation where relevant.
2. Targeted tests for the changed behavior.
3. Regression tests for a fixed bug when meaningful.
4. Broader relevant test suite.
5. Required source synchronization checks.
6. Build/package validation when the packaged application is affected.
7. Final `git diff` and `git status` review.

Typical project commands include:

```bash
python -m pytest
python tools/sync_mobile_core.py
python build_exe.py
git status
git diff
```

Run only the commands that are relevant and available in the current environment.

## Evidence Rules

- Report actual exit status/test results.
- Do not invent coverage, test counts, build success, artifact sizes, or runtime behavior.
- If a check cannot run, state why.
- A partial test pass is not equivalent to full-suite success.
- If new edits are made after a successful test, rerun the checks invalidated by those edits.

## Completion Language

Use "completed/fixed" only when the required verification passed.

If verification is incomplete, say what is implemented and what remains unverified.

User instructions and `AGENTS.md` outrank this skill.
