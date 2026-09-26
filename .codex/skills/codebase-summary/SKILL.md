# Codebase Summary

Use this skill when entering an unfamiliar module, tracing behavior across files, or when broad context is needed.

## Goal

Build the minimum accurate map of the codebase required to solve the task without wasting context on blind full-file reading.

## Procedure

1. Inspect the repository tree at a useful depth.
2. Identify:
   - entry points,
   - relevant packages/modules,
   - configuration,
   - tests,
   - build/packaging scripts,
   - generated or synchronized code.
3. Search for the concrete symbols, imports, call sites, config keys, and tests related to the task.
4. Follow real import/call relationships rather than guessing architecture.
5. Read focused code ranges first; expand to full files only when necessary.
6. Reuse gathered context instead of repeatedly rereading large files.

## Output Mental Model

Maintain a concise internal map:

- source of truth,
- consumers,
- data/control flow,
- relevant tests,
- synchronization/build implications.

## Guardrails

- No blind drive scans.
- No arbitrary reading of hundreds of unrelated lines.
- Do not infer behavior from filenames alone.
- User instructions and `AGENTS.md` outrank this skill.
