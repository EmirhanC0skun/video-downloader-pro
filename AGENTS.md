# Video Downloader Pro — Codex Operating Rules

These instructions apply to every Codex task in this repository unless a higher-priority system/platform instruction or an explicit user instruction conflicts with them.

## 1. Instruction Priority

Use this priority order:

1. Platform/system/security requirements
2. The user's explicit current request
3. This `AGENTS.md`
4. Relevant skill files under `.codex/skills/`
5. Existing repository conventions and documentation

If an explicit user instruction conflicts with a skill, follow the user's instruction.

Do not invent additional approval gates. If the user has already authorized the work, continue autonomously through reversible repository work, code edits, tests, builds, and analysis. Ask only when a genuinely destructive/irreversible action, unavailable credential, external side effect, or material ambiguity cannot be resolved from context.

If a skill causes you to stop, ask for permission, or leave work unfinished, identify the exact skill and rule that caused it.

## 2. Default Execution Style

When the user requests a change, fix, investigation, refactor, or implementation:

- Treat the request as authorization to perform the requested repository work.
- Do not stop after proposing a plan when implementation is possible.
- Infer routine implementation details from the codebase and prior context.
- Keep the diff narrowly scoped to the request.
- Preserve user changes and inspect `git status` before editing.
- Do not perform unrelated refactors, dependency upgrades, formatting sweeps, or cleanup.
- Do not expose secrets, tokens, `.env` values, or credentials in logs/output.
- Do not use blind recursive scans of entire drives.

For non-trivial work, give only a short high-level plan. Do not narrate every file read or shell command.

## 3. Relevant Skills

Apply these skill files when relevant:

- `.codex/skills/supervisor/SKILL.md`
  - Complex, multi-step, or parallelizable work.
- `.codex/skills/codebase-summary/SKILL.md`
  - First contact with an unfamiliar module or when architecture/context must be mapped.
- `.codex/skills/systematic-debugging/SKILL.md`
  - Bugs, failures, crashes, test failures, regressions, unexpected behavior.
- `.codex/skills/verification-before-completion/SKILL.md`
  - Any code/configuration change that must be validated before completion.

`AGENTS.md` is authoritative if a skill conflicts with it.

## 4. Project-Specific Architecture Rules

### Desktop / Mobile Core Synchronization

The repository root is the source of truth for core modules.

If any of these change:

- `engine.py`
- `extractor.py`
- `sniffer.py`
- `history.py`
- `logger.py`
- `exceptions.py`
- `downloader.py`
- anything under `extractors/`

run:

```bash
python tools/sync_mobile_core.py
```

`android_app/core/` is generated/synchronized output. Do not manually maintain divergent copies there.

After synchronization, run the relevant sync regression test(s). Prefer the repository's current test names; inspect the test suite instead of assuming an obsolete filename.

### FFmpeg Resolution

Do not blindly search PATH or scan disks for FFmpeg.

Use the project's local resolver:

```python
engine.get_ffmpeg_path()
```

Subprocesses and tests that require FFmpeg should use the resolved binary path.

### Async / Streaming Rules

- Do not perform blocking disk/network/CPU-heavy operations directly on the main asyncio event loop.
- Offload blocking work to an appropriate executor/worker.
- Reuse persistent HTTP connections where practical.
- Stream media in bounded chunks; never buffer complete video payloads in RAM unnecessarily.
- Close abandoned stream responses.
- Keep Playwright/network-sniffer contexts isolated and tear them down promptly.

### Tkinter Thread Safety

Do not update Tkinter widgets directly from background threads.

Marshal UI updates to the main loop using mechanisms such as:

```python
self.after(0, ...)
```

or `after_idle`.

### Exception Handling

Do not add silent handlers such as:

```python
except Exception:
    pass
```

If an exception is intentionally tolerated, record useful diagnostic information, normally at debug level with traceback context.

## 5. Testing and Verification

Use verification proportional to the change.

For Python logic changes, start with targeted tests when available, then run the broader relevant suite if warranted:

```bash
python -m pytest
```

For bug fixes, add a regression test when the repository's testing structure supports it and the test meaningfully proves the bug cannot recur.

Do not claim a fix is complete without fresh evidence from appropriate tests/builds/checks.

Do not fake validation or report tests as passed unless they were actually executed.

Do not mock away the core behavior being tested merely to produce a passing result.

## 6. Packaging

When desktop or engine changes materially affect the packaged Windows application, run:

```bash
python build_exe.py
```

Use `VideoDownloaderPro.spec` as the packaging source of truth. Do not create a second independent hidden-import/data-file list.

If packaging cannot run in the current environment, report that explicitly instead of pretending it passed.

## 7. Documentation

Update `README.md` when the requested change materially changes public behavior, setup, usage, supported features, or user-visible workflows.

Do not invent badge values, test counts, coverage percentages, performance claims, or success metrics. Use measured output only.

## 8. Git Discipline

At task start and task end, inspect repository state:

```bash
git status
```

Review the final diff before declaring completion.

Do not overwrite unrelated user work.

### Commit / Push Policy

Do **not** automatically commit or push merely because implementation finished.

Commit and/or push when:
- the user explicitly requested it, or
- the current task clearly includes publishing the completed repository changes and prior authorization covers it.

Otherwise leave the verified changes in the working tree and report them.

Never force-push, rewrite shared history, delete branches, or perform other destructive Git operations without explicit authorization.

## 9. Completion Report

When work is complete, report concisely:

- **Değişiklik:** what changed
- **Etkilenen dosyalar:** important files touched
- **Doğrulama/Test:** commands run and concrete results
- **Kalan / çalıştırılamayan doğrulamalar:** anything that could not be verified; otherwise `Yok`

Do not say “fixed”, “done”, or “completed” unless the relevant verification succeeded.
