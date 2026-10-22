# Upstream: Spud Coach

Folded into `brotato_bot/dataset/` on 2026-10-21 (harness plan, Task 2).

- Repository: https://github.com/brendanlefebvre/spud-coach (MIT, (c) 2026 Brendan LeFebvre)
- Commit: `9e02315609302a1c6c5d92099b4743efdce21341`, 2026-08-04, tag `v0.14.1`
- Package: pyproject name `spudcoach` 0.14.1, import package `brotato_coach`

Every copied file starts with `# Folded from Spud Coach (MIT) commit 9e02315, see
learnings/upstream.md`; upstream docstrings are kept. Imports were rewritten
`brotato_coach` -> `brotato_bot.dataset.spud`; no other edits to the spud/ tree (ruff
findings there are silenced via `per-file-ignores` instead of rewriting upstream code).
The license notice is appended to `LICENSE` under Third-party.

## Kept

| Upstream | Here |
|---|---|
| `brotato_coach/tres.py`, `dataset.py`, `schemas.py` | `brotato_bot/dataset/spud/` |
| `brotato_coach/builders/*` (all 15 modules) | `brotato_bot/dataset/spud/builders/` |
| `brotato_coach/calc.py` | `brotato_bot/dataset/spud/calc.py` - imported by `builders/weapons.py` |
| `brotato_coach/scene.py` | `brotato_bot/dataset/spud/scene.py` - imported by `builders/enemies.py` |
| `unpack_pck.py` | `brotato_bot/dataset/unpack.py` - edits: shebang dropped, `unpack()` returns the file count |
| `build_dataset.py` main flow | re-implemented in `brotato_bot/dataset/build.py` (`game_version` passed in; no `recovered/`; atomic write; no `--strict`) |

`calc` and `scene` were on the plan's drop list, but kept builders import them, so the
rule "keep a module only if a kept builder imports it" wins: dropping them would break
`builders/weapons.py` and `builders/enemies.py`.

Tests copied to `tests/dataset/` (imports rewritten): `test_tres`, `test_dataset`,
`test_calc`, `test_scene`, and `test_build_{achievements,characters,classifications,
discover,enemies,items,localization,provenance,timestamps,version,waves,weapons}`.

## Dropped

- `server.py` (MCP server), `answers.py`, `evaluate.py`, `query.py`, `runfile.py`,
  `orientation.py` and their tests (`test_server`, `test_answers`, `test_evaluate`,
  `test_query`, `test_runfile`, `test_orientation`, `test_run_report`).
- `bestiary.py` + `test_bestiary.py`: no kept builder imports it (it imports `query`).
- `tools/` (`brotato_inspect.py`, `diff_dataset.py`, `gather_achievements.py`) +
  `test_diff_dataset.py`: no kept builder imports them.
- `build_dataset.py` itself and `test_build_dataset_paths.py` (tests the `recovered/`
  path resolver, which does not exist here).
- `test_shipped_dataset.py`, `test_docs.py`, `test_smoke.py` (tie to upstream's shipped
  data, docs and package entry point), docs/, site/, plugin/.

## Notes from the first build (game 1.1.15.4)

- The pck holds no `translations.csv`: translations are binary Godot
  `resources/translations/translations.<locale>.translation` resources. Upstream read a
  decompiled CSV from `recovered/`. So a pck-only build has slug-derived names
  (`display_name` falls back); a CSV can be passed via `build_dataset(translations=...)`.
- Version detection: a bare `\d+\.\d+\.\d+\.\d+` scan of Brotato.pck finds
  `3.100.1.8` (MP3 encoder tag `LAME3.100.1.8` in audio data), `0.1.3.5` (noise),
  `1.1.13.2` and `1.1.15.4`. Only the last two are Godot Variant-framed String constants
  (u32 type 4, u32 length) in .gdc bytecode, so `version.detect_game_version` requires
  that framing.
- Counts: 202 weapons, 208 items, 50 characters, 15 sets, 39 enemies, 20 zone-1 waves.
  Upstream's README says 197 items for 1.1.15.4, but that sentence dates from upstream
  commit 9c73338 (2026-07-02), before later discover fixes (e.g. data-file prefixes that
  differ from the folder name); the 11-item gap is most likely a stale README, unverified.
