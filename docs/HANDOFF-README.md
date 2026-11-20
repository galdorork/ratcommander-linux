# Aerox 9 Linux Configurator — Codex handoff

**Status:** Design and implementation plan, 14 November 2026. No app has been built and no hardware writes have been tested on your mouse.

Build a native Linux desktop app with the part of SteelSeries GG that matters here: a visual 12-button editor, named layouts, and an explicit **Apply to mouse** button that writes basic bindings to onboard memory. No background remapper should be needed for an applied layout.

## Start here

1. Extract this bundle into a new project folder. Keep `AGENTS.md` at the project root and preserve the `docs/` paths.
2. Open that folder in Codex. If you want Git history from the start, initialize a repository in that folder before opening it.
3. Paste the kickoff prompt below. It asks for a working GUI in demo mode and stops short of writing to your daily-driver mouse.

> Read AGENTS.md and the docs it links to. Implement milestones M0–M2 of docs/IMPLEMENTATION-PLAN.md. Start by checking the current Rivalcfg release and PR #243, then build the native Linux GUI in explicit demo mode with a fake backend. Run the documented checks and give me the launch command. Do not install system rules or write to the real mouse in this session. Tell me what we need to validate locally before enabling the hardware backend.

| File | Use it for |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Short repository instructions Codex should carry across sessions |
| [Product spec](docs/PRODUCT-SPEC.md) | What the GUI does, what it displays, and what stays out of v0.1 |
| [Implementation plan](docs/IMPLEMENTATION-PLAN.md) | Milestones, interfaces, tests, and release criteria |
| [Hardware verification](docs/HARDWARE-VERIFICATION.md) | Owner-run checklist for the actual mouse and a results template |
