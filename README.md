# brotato-bot

An attended bot for Brotato (Steam, game version 1.1.15.4) that plays visibly inside
the game while a theorycrafting loop decides what to do next from game data, run
history and unlock targets. It is a fork of BOTato's AutoBattler mod, renamed to
`Ellie-BrotatoBot`, and it also serves as an advisor that never acts on manual runs.

The project has three subsystems: the in-game mod (`mod/Ellie-BrotatoBot`, Godot 3
GDScript loaded by Godot Mod Loader 6.0.0), which drives the player, follows
file-based plans and records runs; the Python harness and sidecar, which launches
runs, reads recordings and answers mid-run decisions; and the Claude Code skills,
which plan, review and theorycraft between runs. `scripts/sync_mod.ps1` copies the
mod into the game's `mods-unpacked` folder.

The design, goals and decisions are in the spec:
[docs/superpowers/specs/2026-10-21-brotato-bot-design.md](docs/superpowers/specs/2026-10-21-brotato-bot-design.md).
