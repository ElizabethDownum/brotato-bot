# Improvement backlog

Ranked improvements not yet scheduled. Each entry says how it was established. The full
read-only audit (2026-10-24, Sol, against `562a97e`) lives in the gitignored
`.ai/tasks/2026-10-24-code-audit/audit.md`; this file keeps the actionable summary.

Impact is h/m/l, effort S/M/L. "Verified" means the controller re-read the code or game
source; "audit" means the claim is the auditor's and was not re-checked.

## Next, after run 11

| id | finding | impact / effort | status |
|---|---|---|---|
| F02 | `world_view.gd` `_refresh_kill_ref` reads `w.stats` (base resource) for damage, projectiles and cooldown; the game fires with `current_stats` (`.decompiled/weapons/weapon.gd:136-156`). The comment claiming `stats` is post-init is wrong. Killability and attack positioning never see build growth. Changes combat steering, so not in run 11. | h / S | verified |
| F08 | `experience.py` `_final_build` reads builds only from `snapshot`/`death` events; a win writes a standalone build record (run 10 line 1439), so every win's buy/take rows have `kept_to_end: null`. Add a winning fixture and a refresh path for already-joined decisions. | m / S | verified |
| F01 | 42 of 50 character rows have no speed weight; `get_plan()` replaces `DEFAULT.stats`, so a default alone does not reach them. Fill missing stats after row selection, keeping explicit negative goal weights. | h / S | audit; matches the run 7 speed decline |
| F03 | Goal-shaped `ban_items` only act when the game's ban mode is on (`base_shop.gd` `_apply_bans`); scoring and crate fallback ignore them. Give exclusions a consistent acquisition meaning. | h for keep-at-zero targets / S-M | audit; known since run 8 |

## Scoring and shop policy

| id | finding | impact / effort | status |
|---|---|---|---|
| F04 | Unknown effect keys score 0. Gentle Alien's enemy-count effect looks free (and has no `text_key`, so the crate ask misses it); Piggy Bank and Dangerous Bunny get no value and never reach review. Price the common mechanics; route consequential unknowns to review. | h / M | audit |
| F05 | Scoring uses raw weighted stat gains; ignores caps (dodge, speed, HP, crit, curse via `utils.gd:469`) and stat-gain modifiers (`run_data.gd:1383`). Score effective before/after change. | h / M | audit |
| F06 | Haiku approves items independently per turn; the rules can buy two approved items that are dangerous together (a drain plus an HP reset). Ask for a jointly compatible set. | h when triggered / M | audit; not observed |
| F07 | Demon pays in max HP, but the shop uses `get_player_gold` (`base_shop.gd:430/479/510`), not `get_player_currency`; state export shows the wrong currency to Haiku. | h for Demon / M | verified |
| F14 | No marginal weapon value model; set bonuses counted when a combine leaves set count unchanged; no autonomous merging of held pairs (run 8 ended with two Laser Gun II). | m-h / L | audit |
| F15 | Level-ups can never reroll a weak board; the sidecar contract allows only `pick`. | m / M | audit |
| F16 | Purchases maximize score without pricing it; rerolls stop on count and gold; savings target weapons only; Piggy Bank interest not valued. Runs 9 and 10 spent 926 and 966 on rerolls (not shown to be waste). | m / M | audit |

## Sidecar context and robustness

| id | finding | impact / effort | status |
|---|---|---|---|
| F12 | The sidecar renders `plan.json` itself; the mod's effective plan is that file merged over the character row, so built-in fields are invisible to Haiku. Reroll price, free rerolls and reserves are not exported. Export the resolved plan and economy. | m / M | audit |
| F13 | Held items are grouped by id with base-dataset effects, losing cursed and other live variants; the 8000-char equipment cap can drop late safety-relevant items. | m / M | audit |
| F18 | Run 10: 30 calls, 206.5 s of sidecar time (run 9: 26 calls, 152.3 s). Usage sits in raw output, not report fields; changing state precedes reusable knowledge in the prompt. Normalize metrics before optimizing. | m / M | audit |
| F19 | A sidecar failure writes no response, so the mod waits its full 45 s deadline. Add an explicit "use rules" reply. No run has hit this (204/204 first-attempt successes). | m when failing / M | audit |

## Experiment loop

| id | finding | impact / effort | status |
|---|---|---|---|
| F09 | `collect` resolves an old run's target from the current plan/config when no target event exists; re-collecting after switching targets can misattribute it. Record the target in the header. | m / S | audit |
| F10 | Experience rows lack target, target-fired, danger and plan id; retrieval mixes contexts and a target-missing win looks better than a target-hitting death. | m / S | audit |
| F11 | `prepare.validate_plan` and `PlanFile.load_from` check much less than sidecar patch validation; a malformed shop value fails at runtime instead of at prepare. | m / S-M | audit |
| F17 | Runs cannot be reproduced exactly: no archived effective plan/config, patches keep the plan id, prompts stored as hashes, `proposal_n` always null. | m / M | audit |

## Previously recorded

- Linear-mode pickup deadlock (`docs/observations.md`, measured idling): addressed by target
  mode, which run 11 tests.
- `brotato-next` exclusion list for unshapeable targets; looter value/range tuning from run 11's
  loot telemetry; `ban_items` outside ban mode (F03); objective context for Haiku (F10, F12).
- Per-tick cost is not a problem today: run 10 wave 19 gather+choose median 1.5 ms, p95 3.0 ms
  (1 Hz samples).
