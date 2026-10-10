# AITD32X development instructions

Avoid unnecessary tests or unrequested actions whenever possible to conserve tokens, credits, and Codex usage limits.

Read README.md and docs/DEVELOPMENT.md before changing this port. Use docs/ARCHITECTURE.md for memory and platform constraints. Keep each requested change focused and run only the checks relevant to it.

When applying an optimization, reuse it throughout the game wherever the same conditions hold and existing behaviour can be preserved.

Preserve original assets, user saves and the ignored .local/baseline release. Do not add msdos-game/, generated assets/builds, local dependencies or emulator saves to Git. Do not overwrite a user's battery save with a test fixture.

Keep the 25 Hz gameplay simulation and approved 60 Hz animation clock independent of rendering. Preserve save compatibility unless a requested change requires a documented migration. Do not expand gameplay scope or remove approved UI behaviour as part of an unrelated fix.

Do not claim hardware validation from emulator results. Document material RAM/ROM changes and build/validation limitations. Commit only when requested; keep future feature/fix commits small and reviewable.
