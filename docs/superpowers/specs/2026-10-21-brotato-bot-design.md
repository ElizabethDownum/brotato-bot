# Brotato bot: design

Status: **approved by Ellie 2026-10-21** (revision 2 plus her amendments).
Implementation workers: Opus 5.5 recommended by Ellie.
Owner: Ellie. Drafted with Claude Fable 5.1 from a question loop on 2026-10-21.
Attribution: "(Ellie)" marks what Ellie decided; "(Claude's call)" marks a
default Claude chose that Ellie can overrule.

## 1. Intent

Two goals, one project:

1. **A bot that plays Brotato** inside Ellie's Steam copy, visibly, so she can
   watch it reason while doing something else on the same machine.
2. **A theorycrafting loop** that decides what to do next, both between runs
   and mid-run, from ground-truth game data, cached guide knowledge, Ellie's
   unlock targets and the logged outcomes of earlier decisions. It works the
   unlock graph systematically and gets better at each character. It also
   serves Ellie on her own manual runs as an advisor that never acts.

The bot measures what the loop decides. Ellie learns by watching the overlay
live and by reading run reports, decision logs and proposals.

## 2. Goals, non-goals, anti-goals

Goals (Ellie):
- Primary objective when one is set: an **unlock target**, a set of locked
  characters, items and weapons to unlock systematically.
- When no unlock target is set, the secondary objective becomes primary:
  **optimise the run for the character being played**, the current build and
  the prospective build, including pivots driven by what the shop offers.
- Steam achievements keep firing (verified, section 5).
- **Advisor mode for manual runs**: Ellie can export game state mid-run on her
  own profile and ask Sonnet for an analysis. The bot never acts there.
- First milestone target: unlock any one locked character.
- Decisions and their outcomes are logged so later LLM calls are guided by
  what actually happened. A form of learning from experience through Haiku
  calls, not gradient RL.

Non-goals (Ellie): unattended operation across runs, parallel runs, co-op,
Workshop publishing, reinforcement learning, screen capture, OS-level input
injection.

Anti-goals (Ellie). Failure even if it technically works:
1. **Ellie cannot use her computer while it runs.** The bot must never steal
   focus, mouse or keyboard.
2. **An endless failure cycle the loop cannot learn from.** Persistent failure
   must change the approach, never just repeat it.
3. **Any bot action on profile 0 or during Ellie's own play.** Grounds for an
   immediate bot halt.

Not failures (Ellie): noisy early reports (temporary); the bot cheesing a win
(good learning material).

## 3. Operating model (Ellie)

- Ellie launches the game and starts each run by hand, on profile 1. One run
  at a time.
- **Within a run the bot is autonomous.** It steers, shops, picks level-ups,
  and may pause the game (the pause-menu mechanism, `get_tree().paused`) to
  think. When the best next action is not known from rules and data, it asks
  Haiku through the sidecar (section 7.3) and acts on the structured answer.
  No mid-run interference from Ellie is needed or expected.
- The run ends at a **completion event**: wave 20 cleared or death. Then the
  bot stops acting and waits for Ellie to start the next run.
- When the **target unlock fires mid-run**, the run is played out. The event
  is recorded, and at the end of that wave the sidecar runs a Sonnet
  checkpoint analysis (what was achieved, what the rest of the run can still
  earn, plan adjustment for the remaining waves). The bot applies the
  adjustment and continues.
- Grind-and-learn: an out-of-reach target is retried, not skipped. Randomness
  is real, so the loop reasons in batches and confidence, learning from death
  records, not single outcomes.
- Between runs the loop is **file-based**: run report and decision log in
  markdown and JSON, a proposal for the next run, and Ellie discussing it with
  Fable in Claude Code when she wants to.

## 4. Recon facts (measured 2026-10-21)

- Game: Brotato 1.1.15.4 + Abyssal Terrors DLC at
  `D:\SteamLibrary\steamapps\common\Brotato`. Custom Godot 3.7 build. The
  Godot Mod Loader (6.x) is shipped inside the game; mods load from
  `mods-unpacked/<Namespace-ModName>/` next to the executable or from
  Workshop zips. No mods were installed before the spike.
- Save: `%APPDATA%\Brotato\<steam64 id>\`. Three profiles; profile 0 is
  Ellie's (26 characters unlocked, Danger 5 on Mage, Explorer, Arms Dealer);
  profile 1 untouched.
- Unlock graph source: `challenges/*.tres` in the pck (117 resources with
  `my_id`, `reward`, `stat`, `number`, `unlocked_by_default`). Trigger logic
  in `singletons/challenge_service.gd`; `complete_challenge` saves
  immediately. Progress lives in the per-profile save (`challenges_completed`,
  `characters_unlocked`, `items_unlocked`, `weapons_unlocked`,
  `difficulties_unlocked`).
- Input path: `player_movement_behavior.gd` `get_movement()` reads
  `Input.get_vector(...)`. Overriding it in-process steers the player with no
  synthesized OS input. BOTato makes no `warp_mouse`, `parse_input_event` or
  window-focus calls.
- Focus: `settings.pause_on_focus_lost` is a **global** setting (defaults
  true, exposed in Options as "on lost focus"). Must be off while the bot
  plays; it also affects manual play.
- Prior art to build on:
  - **BOTato** (github.com/boardengineer/botato, MIT, last commit 2026-09-03,
    ~10k lines GDScript, namespace `Pasha-AutoBattler` 2.0.2). Arbiter
    steering (24 headings + stand, scored in expected HP lost over 0.8 s),
    shop advisor driven by per-character plans as dictionaries (50 plans
    including DLC characters), overlay, 1 Hz telemetry to stdout in debug
    builds only. Manifest targets 0.8.0.3; 1.1.15.4 behaviour unverified
    (spike pending). Toggle: Shift+Space in-game; config in
    `user://pasha-botato-options.cfg`; Mod Options dependency is optional.
  - **Spud Coach** (github.com/brendanlefebvre/spud-coach, MIT, 0.14.1).
    Builds `data/brotato.json` from a local install (202 weapons, 197 items,
    50 characters, enemies, waves, DPS and stat formulas). Ships a stdlib pck
    unpacker. Dataset never distributed.
  - Brotato wiki: MediaWiki 1.43 API open, no license declared. Cache
    locally, personal use.
- Rejected: Brotato-HTTP-server (GPLv3), brotatoai (PPO RL), screen capture.
- Decompile: GDRE Tools 2.7.4 recovers the 476 scripts in 6 s. Output stays
  in a gitignored folder; never committed or pushed.

## 5. Achievements and mods (measured)

`singletons/platforms/steam.gd` `complete_challenge()` calls
`steam.setAchievement` with no check on loaded mods; `challenge_service.gd`
has no mod gating; the only mod-aware behaviour is a one-time title-screen
warning. Mods do not disable Steam achievements. Workshop and local
`mods-unpacked` feed the same loader; we use the local folder only.

## 6. Profiles and save safety

- Brotato has three save profiles with native `reset_save_profile`,
  `copy_save_profile` and `unlock_all_save_profile` in
  `singletons/progress_data.gd`. Unlocks are per profile; Steam achievements
  are per account.
- **Profile 1 is bot-only.** The bot acts only when
  `ProgressData.current_profile_id == 1` and a plan file exists. Any other
  profile, or a human input event while the bot is enabled, halts the bot
  immediately and shows it on the overlay. (Ellie.) Unlocks the bot earns stay
  on profile 1; they do not need to reach profile 0. (Ellie.)
- Advisor mode (export only) works on any profile; it reads state and writes
  a file, it never acts.
- Wipe: the in-game profile reset. Steam Cloud autocloud is on, so file-level
  deletes are unreliable.
- Backup: one-time copy of the whole save folder before the first modded
  launch, kept in `backups/` (gitignored). No per-run snapshots; profile 1 is
  disposable by design. (Claude's call, after Ellie's question in the review.)
- The mod itself is global. Its toggles default off; the profile guard above
  is what protects profile 0, not the toggle.

## 7. Architecture

Four parts: the mod (GDScript), the harness and sidecar (Python), the
decision protocol between them, and the Claude Code skills.

### 7.1 In-game mod (GDScript): `mods-unpacked/Ellie-BrotatoBot/`

A fork of BOTato's `Pasha-AutoBattler`, renamed, with these changes:

- **Plan loading from a file.** `BuildPlans.get_plan()` returns the plan from
  `user://brotato-bot/plan.json` when present, else BOTato's built-in plan
  for the character. Same dictionary schema as `build_plans.gd`. The plan is
  reloaded whenever the file changes (checked at wave boundaries and in the
  shop).
- **Run recorder.** JSON Lines per run under `user://brotato-bot/runs/`
  in release builds: run header (character, danger, plan, profile, game and
  mod version), 1 Hz snapshots (wave, time, HP, gold, enemy and projectile
  counts, nearest threat, chosen heading and score margin), every shop action
  with score and gold, every level-up pick with alternatives, every damage
  event with source, wave summaries, death record (wave, position, killer,
  last three threats, build), challenges completed, completion event.
- **State export.** A function that serialises the full run state (wave, HP
  and stats, gold, weapons with tiers, items, current shop offering with
  prices and the advisor's scores, level-up options, unlock delta, recent
  telemetry) to `user://brotato-bot/state/<run_id>-<seq>.json`. Called by
  the decision protocol and by a hotkey (F9, Claude's call) for advisor mode
  on any profile.
- **Decision requests.** At a shop or level-up screen, when the advisor's
  top score is below a confidence threshold, or two options tie within a
  margin, or the plan marks the situation as "ask" (pivot candidates), the mod
  exports state, writes a request file, pauses the game, and waits for a
  response file with a timeout. On response it applies the action (buy,
  reroll, lock, pick, update plan). On timeout it falls back to the rule-based
  choice and logs that. In-wave steering never asks; Haiku is far too slow
  for per-frame decisions.
- **Target checkpoint.** Hooks `ChallengeService` for the configured
  `target_challenge`. On fire: record, finish the wave, export state with
  `kind: checkpoint`, pause, wait for the Sonnet analysis and optional plan
  revision, continue.
- **Completion gate.** Stops acting on wave 20 cleared or death; writes the
  completion event; leaves the UI to Ellie.
- **Guards.** Profile guard (section 6). Focus guard: assert
  `pause_on_focus_lost` is false; warn on overlay and in the log otherwise.
  Human-input guard: any movement key or controller input while the bot is
  enabled halts it.
- **Overlay** kept and extended: range ring, threat and loot vectors, chosen
  heading, plan name and target, last shop decision and its source (rule or
  Haiku), bot state (acting, paused for decision, halted).
- **No Mod Options dependency.** Toggles come from `plan.json` and the config
  file.
- Co-op code paths are left in but untested.
- Ellie allows fixing bugs in the BOTato fork directly. Our own learnings and
  tuning notes live in the project's `learnings/` folder, not in the fork's
  files. (Ellie.)

### 7.2 Harness and data (Python 3.12, `uv`): `brotato_bot/`

- `dataset/`: Spud Coach's unpacker, `.tres` parser and builders **folded
  into this repo** (MIT, notice preserved, upstream commit recorded in
  `learnings/upstream.md`) so we are not beholden to it; upstream is checked
  for updates occasionally and still cited as a source. (Ellie.) Builds
  `data/brotato.json` (gitignored) and the **unlock graph**: every challenge
  with reward and trigger, character unlock conditions, joined with the
  profile 1 save into `data/unlock_state.json` (done / available / blocked,
  and which runs would progress what).
- `knowledge/`: wiki and guide cache. Fetches named pages via the MediaWiki
  API and selected guide URLs once, stores markdown with fetch dates under
  `knowledge/cache/`, refresh on demand. Seeds: BOTato's
  `CHARACTER-PROFILES.md` and `SHOP-GUIDES.md`.
- `run/`: `prepare` writes `plan.json` and the target; checks the focus
  setting and the profile; `collect` ingests the run `.jsonl` and decision
  log and renders `runs/<date>-<n>-<character>-d<danger>.md` plus
  `runs/index.json`.
- `report/`: markdown templates for run reports, decision logs and
  checkpoint notes.

### 7.3 Sidecar (Python, same package): `brotato_bot sidecar`

A small long-running process Ellie starts in a terminal before a bot run
(Claude's call: a terminal she can watch, not a service). It:

- Watches `user://brotato-bot/requests/` for request files from the mod.
- For each request, assembles the prompt: the exported state, the plan, the
  relevant slice of `brotato.json` (the offered items and weapons with full
  stats and set bonuses), the unlock state, the relevant knowledge-cache
  excerpts, and the **experience log** of past decisions in similar
  situations with their outcomes.
- Calls the Claude Code CLI headless (`claude -p` with the skill prompt and a
  JSON output format), Haiku 5.5 by default, Sonnet 5.5 for checkpoints or
  when Haiku's answer fails validation twice. No API keys. (Ellie.)
  Measured 2026-10-21 on Claude Code 2.1.307: `-p` supports `--model`,
  `--system-prompt-file`, `--output-format json` and `--json-schema` for
  structured output validation, so the strict schema is enforced by the CLI
  itself and re-checked by the sidecar.
- Validates the answer against a strict JSON schema (section 7.4). On an
  invalid answer: (1) retry the same call once with the validation error
  appended; (2) if still invalid, a separate **repair call** to Haiku that is
  given the prior prompt, the malformed output and the validation error and
  asked only to produce the valid object; (3) if that fails, fall back to the
  rule-based choice and log all three attempts. (Ellie.)
- Writes the response file; logs request, prompt digest, answer, latency and
  model to `decisions/<run_id>.jsonl`.
- After the run, `collect` joins decisions with outcomes (did the run win,
  HP at next wave, did the bought item get used) into the experience log that
  future prompts cite.

### 7.4 Decision protocol

Files under `user://brotato-bot/`:

- `requests/<id>.json`: `{kind: shop|levelup|checkpoint|pivot, run_id, seq,
  state_path, options: [...], deadline_ms}`.
- `responses/<id>.json`: `{action: buy|reroll|lock|skip|pick|revise_plan,
  option_index?, plan_patch?, confidence: 0..1, rationale: <=2 sentences,
  tags: [...]}`.
- The schema is the contract. The skill prompt instructs the model to output
  only that object. The sidecar rejects anything else. Rationale and tags
  feed the experience log; the mod only reads `action`, `option_index`,
  `plan_patch`.
- Timeouts: shop and level-up 45 s (game is paused, so this is only Ellie's
  patience); checkpoint 120 s. Both are config values expected to be tuned.
  (Ellie.)
- Advisor mode (any profile): the F9 export writes a `kind: advise` state
  file under `user://brotato-bot/state/`. Ellie opens it in Claude Code
  herself with the `brotato-advise` skill. The sidecar does nothing with it.
  (Ellie.)

### 7.5 Claude Code skills: `.claude/skills/`

- `brotato-next`: between runs. Reads the latest run report, decision log,
  `runs/index.json`, `unlock_state.json`, `targets.md` and the knowledge
  cache; writes `proposals/<date>-<n>.md` with next character, danger,
  target, the full `plan.json`, rationale citing evidence, risk, and a
  stagnation check. Haiku 5.5 by default, Sonnet 5.5 on request. Invoked by
  Ellie, by Fable, or by the sidecar at run end.
- `brotato-decide`: the mid-run prompt used by the sidecar. Strict output
  schema. Same prompt file is usable by hand on any exported state.
- `brotato-advise`: advisor mode for manual runs; Ellie points it at an
  exported state file; free-form markdown, Sonnet.
- **Stagnation rule** (anti-goal 2, Ellie wants it lax): after three failed
  runs on one target with no improvement in death wave or wave-20 HP, the
  next proposal must change something material (plan family, character, or
  route through the unlock graph). Only after material changes also fail does
  it pause the target and notify Ellie with the evidence. It never
  re-proposes an unchanged plan after a stagnation hit.

## 8. Data layout in the project

```
brotato-bot/                          its own git repo, nested in ClaudeFiles
  docs/superpowers/specs/             this design, later the plan
  mod/Ellie-BrotatoBot/               the GDScript mod (synced into the game)
  brotato_bot/                        python: dataset, knowledge, run, report, sidecar
  data/                               brotato.json, unlock_state.json (gitignored)
  knowledge/cache/                    fetched wiki/guide markdown (committed, dated)
  learnings/                          our own tuning notes, kept apart from the fork
  runs/                               run reports and jsonl, index.json
  decisions/                          per-run decision logs, experience log
  proposals/                          between-run proposals
  advice/                             advisor-mode notes for manual runs
  backups/                            one-time save backup (gitignored)
  targets.md                          Ellie's current unlock targets
  .claude/skills/                     brotato-next, brotato-decide, brotato-advise
```

Game-side files live under `user://brotato-bot/`, which resolves to
`%APPDATA%\Brotato\brotato-bot\`. The builder measures whether Steam
autocloud syncs that folder; if so, the mod writes elsewhere.

## 9. Milestones

1. **Spike (throwaway):** stock BOTato in `mods-unpacked`, profile 1,
   Danger 0, confirm it loads and plays on 1.1.15.4. Ellie approved; waiting
   for her to finish her current session.
2. Fork and rename; plan-from-file; run recorder; state export; completion
   gate; guards. One attended run at Danger 0 on profile 1.
3. **Publish the fork.** Push the project repo to GitHub under
   ElizabethDownum, MIT licence (BOTato's MIT notice preserved; MIT is the
   most permissive licence compatible with it). Decompiled scripts, dataset
   and save backups gitignored. (Ellie.)
4. Dataset and unlock graph; `unlock_state.json` from profile 1.
5. Harness `prepare` / `collect`, run report, decision log.
6. Knowledge cache with seed pages.
7. Sidecar and the decision protocol with `brotato-decide`; validate with
   shop decisions at Danger 0.
8. `brotato-next` with the stagnation rule; `brotato-advise` and the F9
   export for manual runs.
9. Target checkpoint with Sonnet analysis.
10. First real target: the cheapest locked character. Run the loop until it
    fires.

## 10. Risks and open items

- BOTato on 1.1.15.4 may need fixes; the spike measures this. Fallback: keep
  steering and shop logic, re-point extension paths.
- Set the fork manifest `compatible_game_version` to 1.1.15.4.
- Headless CLI latency: expect 5 to 30 s per Haiku decision. The game is
  paused meanwhile, so it costs Ellie's patience while watching, nothing
  else. Keep requests rare: rules first, Haiku only when rules are unsure.
- Haiku may propose poorly early; the experience log and the strict schema
  are the mitigation, and the fallback is always the rule-based choice.
- Game data and decompiled scripts derive from copyrighted files: gitignored,
  never pushed. The wiki declares no licence: cached pages are personal use.
- Telemetry and logs are tens of KB per run; no performance concern.

## 11. Decided by Claude, reviewed with Ellie at each step

Ellie asked that these be decided by Claude or reviewed as the builder
reaches them:
- Exact JSONL event schema, state export schema, markdown templates.
- Which wiki pages and guide URLs seed the knowledge cache.
- The confidence threshold and tie margin that trigger a Haiku request.
- How `prepare` verifies the profile id.
- Overlay wording.

## 12. Review history

- Builder check 1 (2026-10-21): unlocks per profile (resolved: profile 1
  only); target-fire behaviour (resolved: play out, checkpoint); restore
  command (resolved: dropped per-run snapshots, one-time backup instead).
- Ellie's review (2026-10-21): added advisor mode, secondary-becomes-primary
  objective, in-run autonomy with pause, sidecar calling Haiku via the Claude
  Code CLI with strict output, experience log, lax stagnation, publish the
  fork to GitHub under MIT, learnings folder, profile-0 halt rule.
- Ellie's second pass (2026-10-21): repair call on malformed JSON, advisor
  export is run by Ellie herself, timeouts tunable, Spud Coach folded into
  the repo. Approved.
