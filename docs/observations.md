# Observations

Single data points noted by the owner or the controller after a run. Each entry is an
observation to test later, not a change request. Promote one to a proposal or a mod
change only when a later run or a code read confirms it.

## 2026-10-22 run 1 (20261022-223221-well_rounded-d0): materials pile up out of reach

- Observed by the owner while watching: the bot seemed bad at collecting materials. There
  was almost always a large reserve of materials that could not then be spent in the next
  shop.
- Measured from the run file: the shop itself spends nearly everything. Gold left when the
  bot pressed Go was 0 to 52 per shop, median about 10, while gold at wave end ranged from
  25 to 480. So the unspent reserve is not shop behaviour.
- Mechanism, confirmed by the owner: the reserve was the bag. Materials the character
  did not pick up during the wave are swept off the floor at wave end into the bag, and
  the bag pays out during the next wave instead of being spendable at that shop. So the
  bot is not pathing to materials well enough during the wave. This is most likely
  inherited from BOTato's steering rather than anything in our plan layer.
- Evidence gap: snapshots record `gold` but neither floor materials nor bag contents, so
  the run file cannot measure how much went to the bag each wave. A future snapshot
  field for floor and bag material counts would quantify it.
- Status: one run, one observation. Not acted on.

## 2026-10-22 idea: record full-run pathing for steering analysis

- Owner's idea: collect the whole run's pathing so the steering can be optimised from
  data rather than by watching.
- What the run file already holds: one `snapshot` per second while the bot acts (982 in
  run 1), each with `pos`, `heading`, `hp`, `gold`, `enemies`, `nearest_threat`, `edge`
  distance and the arbiter's counters (`still`, `flips`, `eng` and so on). That is a 1 Hz
  path with threat context, enough to draw where the potato went each wave and where it
  stood still.
- What it lacks for the materials question: floor material count, bag count, and the
  nearest material's distance. Without those, a path cannot show which materials were
  left behind. A 1 Hz cadence also hides short dodges; 5 to 10 Hz would show them.
- Possible mod change, not scheduled: add `mats` (floor count, bag count, nearest
  material distance) to each snapshot, and optionally a denser `trace` event of `pos`
  only. Both are a few lines in the telemetry recorder and cost little per run.
- Status: idea only. Parked until the current run series settles.

## 2026-10-22 run 1: Opus 5.5 steering analysis (reviewed)

- Report: `C:\Users\eliza\AppData\Local\Temp\claude\C--Users-eliza-Desktop-ClaudeFiles\df54e382-c4c0-4b39-9d98-50979b7e9e38\scratchpad\run1-analysis\report.md`
  (with `paths.png` and the scripts). Scratchpad only; copy into the repo if it is to be kept.
- Verified against the run file and code by the controller: gold after every shop 0 to 52;
  33% of snapshots mostly still, 87% of those with the nearest enemy beyond 400 px; the
  potato never came within 212 px of a wall; Well Rounded has no steering profile row, so
  it runs the baseline with no `sweep` and no `gold_end`; the `--arb-sweep` override and
  the `w_hyst` still-after-still bonus exist where the report says.
- Caveats: gold per kill is the only collection proxy and bag payouts contaminate it; one
  run at 1 Hz. The report labels inferences and is honest about what it cannot measure.
- Top two testable changes it proposes, not scheduled: (1) `sweep` about 2.5 at radius 420
  for the baseline profile, testable with the existing `--arb-sweep` knob; (2) pay the
  still-after-still bonus only to characters that gain from standing.

## 2026-10-22 run 1: damage telemetry recorded nothing (resolved 2026-10-23: no hits were taken)

- Measured: zero `damage` events, `dmg_w` 0 in all 982 snapshots, every `wave_end`
  `damage_taken` 0. Yet HP fell from 88 to 60 during wave 20 and from 25 to 18 across
  wave 7, and wave 7 began at 1/28 HP (unexplained; the wave-6 shop bought
  `item_alien_magic`).
- Resolution (2026-10-23, measured): in run 1 HP never fell between any two consecutive
  1 Hz snapshots. Waves 7 and 20 *began* at 1 HP (1/28 and 1/96) and regenerated; the
  "88 to 60" reading compared wave 19's end with wave 20's partial regen. Run 2 recorded
  damage events and per-wave damage normally with the same mod build. So the hook works
  and run 1 simply took no unblocked hits at danger 0. Not a telemetry bug.
- The 1-HP wave starts are explained (owner's recall, confirmed in the data 2026-10-23):
  Weird Ghost (tier 0, 12 gold) carries `effect_hp_start_next_wave -100`, i.e. the next
  wave starts at 1 HP, alongside its max-HP bonus. Run 1 bought it in the wave-6 shop
  (wave 7 began at 1/28) and again in the wave-19 shop (wave 20 began at 1/96). Run 2
  bought one too. The scorer sees only the max-HP effect; the downside is an unweighted
  effect key, so Weird Ghost is a concrete negative intangible for step 4 of the plan,
  the mirror of Dangerous Bunny's unscored free rerolls.
- Hardening, agreed by the owner 2026-10-23: log the `took_damage` connect result and
  emit a `warning` event when it fails; have `collect` flag a run whose HP fell between
  snapshots with no damage event in between. Do it with the next harness/mod change.

## 2026-10-22 idea: ask the sidecar after rerolls too, under a per-visit budget

- Today the shop asks the sidecar at most once per visit, before the first buy, and only
  when the scored offering is a near tie, weak, or holds an `ask_on` item. After the ask,
  every reroll is scored and bought by the plan weights alone (run 1: 8 asked buys, 37
  rule buys, 60 rule rerolls).
- Owner's point: an offering after a reroll is no less uncertain than the first one, so
  the same trigger should be allowed to fire again. The once-per-visit rule is a cap, not
  a policy.
- Proposed shape: re-run the ask test on every offering, with a per-visit ask budget (a
  plan key, default 1 to keep today's behaviour; try 2 or 3), and only while gold stays
  above the reroll floor. Each ask pauses 3 to 16 s, so the budget bounds the stall.
- Measure before adopting: same plan and character, budget 1 vs 3, compare gold per
  wave, final build and deaths.
- Status: agreed by the owner on 2026-10-23 as the better rule ("one call right when
  entering the shop" is the weaker one). Scheduled after run 2; implement as a mod
  change in the shop extension plus a plan key, then A/B it.

## 2026-10-23 agreed design: one call carries the action and an optional plan patch

- Owner's proposal, agreed 2026-10-23: the single shop or level-up answer may carry a
  `plan_patch` alongside its action (today `revise_plan` is exclusive with buy/pick and
  level-ups cannot patch at all), so the rules that make every later decision run on
  adjusted weights without another call.
- Guards, all agreed: the patch is optional and the model may keep the weights as they
  are; the shaped goal stat cannot be changed and stays one of the primary drivers (the
  mod re-asserts the goal weight after merging, or rejects the patch and records why);
  patches are small (few keys, bounded delta per weight) and logged as their own event
  with before/after weights; the prompt says omit the patch unless the state gives a
  reason.
- Lands together with the ask-after-reroll budget (same shop extension, same schema),
  after run 2, under one review; then A/B against runs without patches on gold per wave,
  final build, deaths and whether the target fired.

## 2026-10-23 run 2 (20261022-235147-well_rounded-d0): first shaped run, died wave 16, speed only -10

- Plan well-rounded-slow-v1 (stat_speed -14, 16 item bonuses), danger 0. Died on wave 16
  to a helmet alien with 400 gold in hand. chal_slow did not fire. Six other challenges
  completed; profile 1 is now 18 done, 22 of 64 characters.
- Speed reached -4 by wave 13 and about -10 at death: Ugly Tooth (w2), Bag (w7), Helmet
  (w8), Reinforced Steel (w11), Bag (w14). No tier-3 or tier-4 speed item (Statue, Esty's
  Couch, Evil Hat) was ever bought; whether one was offered is not in the run file.
- Where the gold went: 48 buys, 19 of them weapons (plain weapons score 22, a locked or
  combining weapon 100, both above any item), and a long tail of low-score items bought
  because `min_buy` is 2.0 (Coral 2.2, Penguin 4.0, Mouse 4.6, Dangerous Bunny 0 via
  the model). The shop spends everything every wave, so a 60 to 130 gold goal item is
  never affordable when it shows up.
- Reading: shaping made speed items win among items, but the flat weight (+14 for a -1
  Bag as for a -20 Couch; the per-point bonus is small next to it) and the weapon scorer
  sitting outside the stat weights mean the goal does not steer gold. Reaching -20 needs
  either a big item saved for, or about seven cheap ones; the run managed five in 15
  waves. Candidates for the next proposal and for mod work: a higher `min_buy` under a
  stat goal, goal-aware saving (lock a visible goal item and hold gold for it, the way
  the shop already locks weapons), and a magnitude-aware bonus for goal items.
- Damage telemetry recorded non-zero `damage_taken` this run (1, 5, 8, 6, 39 across
  waves); see the run-1 entry above, now resolved as "no hits taken".
- Bag of uncollected materials observed again by the owner. Same open item as run 1.
