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

## Owner rulings, 2026-10-24 (batch 2 spec: stat value model)

- One shared baseline covers **every** stat and effect in the game, positive and negative.
  Per-character changes only where they change how the character plays (Demon pays in max
  HP, weapon class) or for its special attributes. Speed is always weighted.
- Every stat has a **curve, not a flat multiplier**, with diminishing returns: +100 speed makes
  more speed worth little. This applies to every stat, not only those with a game formula;
  where the game has none, we author the curve (shape, falloff, cap, negative-side slope,
  documented reason) in one data table.
- The curve is evaluated **at the run's current stats**: value = curve(current + delta) −
  curve(current), using live player stats, held items, current weapon stats and the wave.
- Interactions come from game formulas where they exist: damage taken = 15/(15+armor)
  (`run_data.gd:1429`), so effective HP ≈ HP·(15+armor)/15 and at 100 armor / 20 HP one max HP
  is worth about 6 armor; dodge is capped at 60% (`player_run_data.gd:434`).
- Negative effects are priced on the same curves, so trade-offs such as "-1 HP regen vs +8%
  damage" are decided against the current build.
- Any effect key without a curve is caught by a dataset check and routed to review, never
  scored zero.
- Bans: tier 1 `exclude_items` (mod-enforced never-acquire, all profiles) and tier 2
  `ban_items` (per run, set by the planner; spends the game's 8 ban tokens). Tier 2 waits
  until chal_banned_items (a danger-3 win) is unlocked; until then it acts as tier 1.
- Character mechanics (F01 extended): before the value curves, inventory every character's
  effects from the dataset and game source and classify each as a plain stat modifier
  (handled by the curves at current stats) or a mechanic. Mechanics get handlers wherever
  they change how the character should be played. Owner scope (soft ruling; raise evidence that contradicts it): **any measured behaviour or
  policy is fair game** when it helps or hurts that character, not only steering, weapon
  choice and stat preferences (e.g. Engineer: one turret, uncollected materials buff it, so
  leave some on the floor; the turret copies the best ranged weapon and scales with
  engineering). A negative weight alone never stands in for a playstyle. The output is a
  per-character spec for owner review before it is built.
- Progression (owner, 2026-10-24): keep well_rounded and climb danger 2 -> 5 with one
  controlled change per run; novel challenges/characters wait until the levers settle.
