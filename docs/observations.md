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

## 2026-10-23 agreed design: magnitude-aware scoring

- Problem (run 2): `stat_score` added a flat weight per effect, so a -1 speed Bag scored
  the same as a -10 Statue and junk with one weighted effect cleared `min_buy` 2.0.
- Formula: per effect on a weighted stat, `sign(v) * weight * min(|v| / unit, 4)`, with the
  phase-boost multiplier and the harvest cap applied to the weight as before. A unit is the
  stat's tier-1 level-up value, read from `items/upgrades/<stat>/1/*_effect.tres` (game
  1.1.15.4); a tier-1 level-up of a stat scores exactly its weight, and no single effect
  counts for more than 4 units; an effect with a non-empty `text_key` (conditional or
  temporary: Statue's attack speed, Coral's regen) counts for at most 1 unit. The old `min(v, 20) * 0.02` tie-breaker is dropped:
  magnitude replaces it.
- Code: `mod/Ellie-BrotatoBot/shopping/effect_score.gd` (pure, source of truth, tested
  headless), `shop_advisor.gd` `stat_score` delegates to it; `brotato_bot/run/score.py`
  mirrors it. `score_weapon` and the ask thresholds are unchanged, so an item with a
  ~4-unit effect of a weight >= 6 stat now outranks a plain weapon (22).
- `min_buy` is now calibrated with `python -m brotato_bot score --plan|--proposal FILE
  [--min-buy X]`, which scores every dataset item under a plan as given. `proposal shape`
  raises `min_buy` to 6.0 under a stat goal (`MIN_BUY_UNDER_GOAL`). Calibration on the
  shaped chal_slow plan (2026-10-23): 6 is "worth more than a tier-1 level-up of a weight-6
  stat"; it cuts Penguin (2.0), Gummy Berserker (3.0) and Dangerous Bunny (0) and keeps every
  speed item (Bag 6.17, Helmet 16.3, Statue 89.7, Esty's Couch 96.3); Coral (8.0, a
  stand-still regen counted in full) and Mouse (14.0) still pass. 87 of 247 items score
  above 6. A rule buy is gated by `min_buy`; a model (`haiku`) buy is not.

## 2026-10-23 owner observation: the bot does not go after trees (or materials) when it should

- Owner, before run 3: the bot does not seem to prioritise trees. Some goals or characters
  want trees avoided, but Well Rounded on a goal that does not require avoiding them should
  fell them. Same family of issue as the uncollected materials (runs 1 and 2).
- Mechanism (`steering/world_view.gd`): a living tree is a reward only when the character's
  steering row sets `tree_value`; the default is 0, and only Pacifist (5.0) and the one-hit
  tree lap character (6.0) set it. Well Rounded has no steering row, so trees are never a
  destination; they fall only when a weapon happens to target one. The tree reward is also
  gated to trees inside the pickup radius, so even a row value would not steer toward a
  tree across the map.
- Materials: `GOLD_VALUE` 0.8 is by design a tie-breaker that never outbids a dodge; the
  greedy draw (x1.5) applies only with no live enemy within 280 px, and the between-bursts
  `sweep` multiplier is a per-row opt-in. BOTato's author tuned this for survival at high
  danger (the comment records a flat x1.2 greed dropping Well Rounded from waves 18/18/20
  to 9/14/20). At danger 0 the survival margin is large and that caution costs economy.
- Candidate for step 5 (behaviour profile, Well Rounded first): a Well Rounded row, or a
  danger-aware default, with `tree_value` > 0 and a sweep/greed level scaled to danger,
  plus a tree reward that reaches beyond the pickup radius. Evidence first: run 3's
  wave_end `gold` versus a human's, and the parked `floor`/`mats` snapshot field.

## 2026-10-23 owner concerns: weapon merging and the crate take-or-recycle rule (all three to be scheduled)

- **Combining is purchase-only.** `shop_advisor.gd` `would_combine` scores a copy of a held
  weapon at `COMBINE_SCORE` (100) only when the board is full, so a third copy on offer is
  bought and the game merges. The bot never presses the owned-gear popup's Combine button
  (`base_shop.gd` `_handle_shop_popup` is mouse handling for the human), so two held copies
  are never merged by hand to open a slot. Run 2 spread buys across four weapon families.
- **Crate items are taken blind.** `upgrades_ui.gd` takes a crate item unless it is a weapon
  whose `score_weapon` is below 0; a non-weapon item is never scored, the sidecar is not
  asked, and no event is logged. Under a stat goal this takes items the shop would score
  negative (Jetpack -58 under chal_slow raises speed).
- Owner's ruling (2026-10-23): all three must be accounted for; fold into step 5 or step 7
  as fits, manual merge possibly after step 7.
  1. Crate rule: score the item as the shop does (`score_shop_entry`), recycle below 0, log a
     `crate` event. Small mod change; step 7 candidate.
  2. Stack toward combines: flip `stack_combine` for Well Rounded in a proposal, judge from
     the report. Plan-only; step 5 candidate.
  3. Manual merge of held pairs: own design note (merging a pair early loses damage; merge
     when the board is full, or when a better affordable weapon is on offer). Evidence: the
     held build in `death` / `complete` lines. After step 7.


## 2026-10-23 run 3 (20261023-085402-well_rounded-d0): won wave 20, target not fired, no big speed item ever seen

- Plan `well-rounded-slow-v2` (proposal 4, min_buy 6, stat_speed -14). Won at wave 20 with
  98 HP (max 119), 78 damage taken in the whole run, all in wave 20. Speed went +5 to -1
  (helmet -2, campfire -2, plus one more point); the goal is -20. Unlocked chal_gatherer_3,
  chal_survivor_4 and chal_robust along the way; chal_slow did not fire.
- Watch points from the handoff: weapons came first (5 weapons by wave 3, 6 by wave 6,
  combines from wave 4 on), so items outranking a plain weapon did not starve the build.
  Gold was not banked: every shop spent down to the reroll floor (wave 19 entered with 562,
  spent 359 on buys and 175 on rerolls). 11 sidecar asks, all answered by haiku, all 11
  rationales name the speed goal.
- The miss: none of Bag, Ugly Tooth, Reinforced Steel, Statue, Esty's Couch or Evil Hat was
  bought in 61 rerolls across 19 shops (about 80 boards, at most about 320 slot rolls;
  the first draft of this entry said 380 offers). Helmet (wave 8) and Campfire (wave 12)
  were the only speed buys. Checked and ruled out:
  `score_shop_entry` has no filter beyond the scorer (Helmet's 16.33 in the run log matches
  the Python mirror exactly); all of them except Evil Hat are unlocked on profile 1. So
  they were never on the board, or never affordable when they were. The run stream only
  records buys, rerolls and locks, not what was offered, and the 11 ask snapshots (the only
  offer records) show none of them. Telemetry gap: log the offering (ids and scores) on
  every shop view, so the next run answers "offered and skipped" versus "never offered".
- Remaining junk through min_buy 6: alien worm 7 (x4), lens 8 (x4), bat 8 (x3), duct tape
  6.33, scope 6.2, little muscley dude 8.33 (x2). Their scores come from several weak
  on-plan effects adding up, not from magnitude; a price-per-score factor (step 4) would
  rank them below a reroll but does not address the target.
- Dataset note: the profile save's `items_unlocked` is a list of Godot `String.hash()`
  values (djb2: h = h * 33 + byte, 32-bit, seed 5381) of the item ids; the formula maps
  all 197 entries to ids in `data/brotato.json`. `unlock-state` could list locked items
  (Evil Hat is locked on profile 1), which matters for goal item bonuses.
- Consequence for the plan: survival and economy are not the problem at danger 0; finding
  the goal items is. Step 4 (intangible weights) would not have changed this run. Go to
  step 5 as planned, and carry the offer log into the next mod sync; a goal-item hunt
  (reroll while gold stays above a keep and no goal item is on the board, like the
  `prefer_weapons` hunt in `base_shop.gd`) belongs with the step 7 shop changes.

## 2026-10-23 owner thought: spending down to the floor every shop is not always right

- Owner, after run 3: holding some gold is sometimes better than rerolls or marginal
  items, for instance with Piggy Bank bought early (the game's effect text key marks its
  +20% of held materials at wave start as limited).
- What exists: the plan key `gold_floor` (`base_shop.gd`), reserved from wave 5 on, ramping
  5% per wave of the shop's incoming gold to 35%, capped at the plan's number. Only Saver's
  row sets it (250: hoarding is Saver's damage stat). Well Rounded runs at 0. Lock-and-save
  reserves gold for a strong weapon on offer; nothing reserves for anything else.
- Two gaps, both shop rules, step 7 candidates next to the goal-item hunt and goal-aware
  saving:
  1. Floor keyed on held items: Piggy Bank, Saver-style damage per held material, and
     similar effects should raise the floor once held, as a function of the player's items
     rather than the plan constant alone.
  2. Price the reroll: run 3 paid 49 for a reroll at wave 19 with nothing above `min_buy`
     on the board. Reroll only while the expected value of a fresh offering beats the
     price; today the only brakes are `max_rerolls` 15 and `reroll_keep`.

## 2026-10-23 audit A (Opus 5.5, read-only): the big speed items are rare by design

Report: `.superpowers/sdd/2026-10-23-levers-audit/report-a.md` (brief beside it). Source
claims verified by the controller at the cited lines of the restored decompiled game
(`.decompiled/singletons/item_service.gd`).

- Shop tier odds (per slot, checked from legendary down): uncommon 0.06 per wave capped
  0.6; rare from wave 3, 0.02 per wave capped 0.25; legendary from wave 7, 0.0023 per wave
  capped 0.08; luck scales only the wave term. Weapons take 35% of slots even with every
  weapon slot held. Over a 20-wave run that is about 0.05-0.11 sightings of Esty's Couch,
  0.4-0.6 of Statue and 1.7-1.8 of each tier-1 goal item. Run 3 not seeing a Statue or a
  Couch was the expected outcome, not bad luck, and buying every goal item a run sees
  yields about -25 to -33 speed of offers before `max_nb` caps and affordability.
- Consequences the audit ranks highest: (1) the offer log with tier, price and gold at
  view, to confirm the rates; (2) the Blunt weapon set (-10 speed at 6 weapons, and held
  sets pull weapon draws toward themselves at 35% plus an early bonus), which the ranged
  Well Rounded plan and the no-set-selection ruling currently block: an owner call;
  (3) goal-aware saving and a goal-item hunt (step 7); (4) `ask_on` filled with the goal
  item ids by shaping, so Haiku can lock a goal item the moment one appears (plan-only,
  about an hour); (5) the crate rule, since crates draw from the same tier odds and are a
  second goal-item channel; (6) deactivating the DLC for goal runs (game setting; +32%
  legendary, +24% rare, +11% common per-item odds); (7) `wave_end` stats and the build on a
  win; (8) dropping locked items from goal data and adding `max_nb` (about 4 of the 16
  bonused items are locked; the field default is locked); (9) reroll pricing; (10) a
  progress checkpoint when the goal is behind.
- Also verified: item price = `int((base + wave + base*wave*0.1) * price_factor)`; reroll
  price = `int(0.75*wave) + max(1, int(0.4*wave)) * (1 + paid_rerolls)`; materials left on
  the floor at wave end become `bonus_gold` paid out double on next wave's pickups, so poor
  collection is delayed rather than lost (lowers the economic urgency of the materials
  work, not its goal relevance); run 2 ended near -5 speed, not -10, and four of its held
  items came from crates.
- Corrections to earlier entries: run 3 bought two speed items (Helmet, Campfire), and
  its offer count was about 80 boards, not 380 offers.

## 2026-10-23 audit B (Opus 5.5, read-only): the rules, not Haiku, spend the gold away from the goal

Report: `.superpowers/sdd/2026-10-23-levers-audit/report-b.md`. Controller verified the
ask thresholds, the reroll count (61), the Piggy Bank payout code and the untranslated
objective text.

- Provenance: every Well Rounded weight and every shop constant (`reroll_keep` 5,
  `LOCK_MIN_SCORE` 28 weapons-only, `SURPLUS_KEEP` 120, `HUNT_KEEP` 30, weapon scores) is
  BOTato's, tuned for survival at danger 1 with no unlock goal under the flat scorer. The
  shaping constants (`DOMINANT_MARGIN` 4, item bonus 1.5/pt cap 30) have no calibration
  record. `ask_floor` 4 and `ask_tie_margin` 3 were set for the flat scale and are stale.
  Under the shaped plan a -1 speed item scores 6.17 while Lens scores 8 and Alien Worm 7:
  dominance holds per unit, not per goal point, so junk keeps beating one-point goal items.
- The ask fires on the wrong boards: 5 of 80 run-3 boards were asked, all dead boards
  where Haiku could only say "reroll" (24 of 28 asks matched the rule). Boards never asked
  because the margin was wide: run 3 w8 Scope 94g, w9 Pile of Books 123g (a w9 Statue costs
  exactly 123), w11 Crystal 147g, w13 340g of junk after Haiku's reroll, w16 Glass Cannon
  211g, w18 Kraken's Eye 326g. Spend split run 3: weapons 863, goal items 135, other items
  3236 (2081 on items scoring under 12), rerolls 1097. Haiku's one bad call (run 2 w13
  `skip` with 328 gold, two +speed items on the board) came from not knowing that skip
  leaves the shop with no rerolls.
- Haiku's view: the objective line reads `CHAL_SLOW: CHAL_STAT_DESC` (untranslated; the
  stat and value still arrive via the progress entry); the goal-item list has no locked
  status, `max_nb`, rarity or current-wave price; no reroll price, no min_buy, no waves
  left, no explanation of what the rules do after each action; 5.7k characters of
  knowledge excerpts including other characters' pages and BOTato's "banked gold is wasted
  at low danger"; past decisions from goal-less run 1 marked "win". `confidence` is unused.
  Haiku never used `revise_plan` or `lock`, and cannot express hold-gold, hunt-an-item,
  lock-across-visits, or crate take/recycle.
- Ranked: (1) retarget the ask on the magnitude scale, ask when a goal id is on the board
  or gold is high with nothing goal-relevant, stop asking dead boards (step 5); (2) let
  Haiku set parameters the rules then apply (keep gold, hunt ids, min_buy, ask_on), action
  plus bounded patch in one reply (step 7); (3) prompt facts: mechanics of skip/reroll/lock,
  reroll price, min_buy, waves left, goal now vs. needed (-25 net: Well Rounded starts at +5, and only items and weapon sets lower speed), goal list
  filtered and priced (step 5); (4) prompt noise out, translate CHAL_STAT_DESC, drop
  "weight survival" for stat goals (step 5); (5) shaping per goal point and danger-aware,
  min_buy rising late, locked items out, `ask_on` filled (step 5); (6) gold floor while an
  interest item is held (new rule); (7) experience feedback carries target and
  target_fired or is dropped (step 5); (8) crate rule and event (step 7); (9) stagnation by
  goal-stat progress plus wave_end stats (new); (10) `plan_patch` guard on the goal stat's
  sign and size (step 7).
- Division of labour recommended: rules decide clear boards and dead boards; Haiku is
  asked when a goal item is on the board or affordable soon, and otherwise sets parameters
  (keep, hunt, min_buy) that the rules apply on every later board of the visit.

## 2026-10-23 owner insight: the character must be chosen for the goal

- Owner, after audits A and B: some characters are better or worse at a given goal. Well
  Rounded starts at +5 speed, so chal_slow (-20) needs -25 of reductions from items and
  sets; the character choice itself was working against the target.
- Measured from `data/brotato.json` and `data/unlock_state.json`: among the 22 unlocked
  characters only Old starts below zero speed (-10, plus +10 harvesting, a smaller map,
  fewer and slower enemies, and a BOTato row in `build_plans.gd`). Old needs -10 more,
  about one Statue or three to four tier-1 items. Explorer starts at +10, Well Rounded at
  +5. Chunky looks neutral at 0 but bans the `speed` item group and has a -100% gain
  modifier on speed, so it cannot reach the goal at all.
- Where the choice is made today: `brotato-next` step 4 takes `requires_character` when
  the target names one, otherwise "an unlocked character that the guides support", with
  no goal-fit criterion. `proposal validate` does not check fit either.
- Proposed harness item (new, about 1-2 h): a goal-fit ranking of unlocked characters for
  a stat-goal target, used by `brotato-next` in step 4 and printed by `proposal shape`:
  sign-aware base bonus on the goal stat, gain modifiers on it (a -100% is a veto),
  banned item groups that cover the goal items (veto), whether a BOTato row exists, DLC,
  and the guide's survival notes. A character switch also satisfies the stagnation rule's
  "material change", so it fits the next proposal naturally.
- Consequence: run 4 on chal_slow should be Old, not Well Rounded v3, once the step 5
  changes land; that run tests the pipeline with a character that can actually get there.

## 2026-10-23 owner rulings after audits A and B

- **Generalised rule for proposals:** when proposing a goal and a run, the character's
  stats and attributes (flat bonuses, gain modifiers, banned item groups, wanted tags,
  specials) and the starting weapon's stats and attributes (type, sets, scaling) must be
  factored in accurately. The character-fit idea in the previous entry is one instance.
  The starting weapon is picked by the owner at launch (the mod's `weapon_selection.gd`
  only routes the mouse), so the proposal must name it under `## Next run` and the
  runbook's launch steps must show it.
- **No hard-blocked strategies.** Nothing the model could pick (a weapon set, a weapon
  type, a melee plan) may be hard-blocked by policy. What gates the Blunt set today is
  policy and a modelling gap, not the mod: (a) `shape.py`'s docstring ruling of
  2026-10-22 that shaping never selects a set (it only prints the set bonuses in the
  goal data), (b) `brotato-next` step 5.i, "do not set `weapon_set` unless the character's
  row or the guides support it", and (c) `score_weapon` has no partial-set credit, so a
  set can only be pursued through the all-or-nothing `weapon_set` key, under which every
  out-of-set weapon scores -1 (`shop_advisor.gd` 76-82). The Well Rounded row's
  `weapon_type: "ranged"` scores every melee weapon -1 (123-125), but a plan with
  `weapon_set` set bypasses that gate (the set check returns first). Both keys are plan
  keys that a proposal or a mid-run `plan_patch` may set. Resolution: drop (a) and (b)
  as rules (the writer may choose a set or a type for the goal, with the goal data and
  the fit ranking as evidence), and add a soft set term to `score_weapon` that credits a
  weapon's sets toward the goal stat without the all-or-nothing gate (mod change,
  small). Starting-weapon sets for the record: Well Rounded's pool has one Blunt start
  (Spiky Shield); Old's has one (Rock).
- **DLC stays on.** No DLC toggling for goal runs.
- **Step 5 scope is paused** until the character-selection rule and the two points
  above are resolved.

## 2026-10-23 owner refinement: sets are allowed once set scoring is granular; auto-start from the menus

- Refinement of the rulings above: the 2026-10-22 "shaping never selects a set" was a
  complexity hold, not a principle. Once `score_weapon` credits sets granularly (a
  weapon's sets count toward the goal stat without the all-or-nothing `weapon_set`
  gate), shaping and the proposal writer may select a set to pursue. The `brotato-next`
  5.i clause is to be adjusted accordingly.
- Owner question: could the bot start at character and starting-weapon selection, so
  the pipeline selects every option from the beginning? Feasible, from the restored
  source and the mod's existing extensions:
  - The game's flow is `main_menu._on_StartButton_pressed` -> character selection ->
    weapon selection -> difficulty selection -> run. Every selection screen extends
    `base_selection.gd`, which has `_find_inventory_element_by_id(my_id_hash, player)`
    and `_on_element_pressed(element, player)`; the difficulty screen's handler sets
    `RunData.current_difficulty = element.item.value`. Selecting is one call per screen.
  - The mod already extends `main_menu.gd`, `character_selection.gd`,
    `weapon_selection.gd` and `difficulty_selection.gd` (mouse routing for co-op), so a
    launcher is additive: on the main menu with the bot profile loaded and a one-shot
    launch token present, press Start, pick `character_id`, `starting_weapon` and
    `danger` from the installed plan/config, and switch the bot on (today's manual
    Shift+Space) when the run starts.
  - Guards: the profile stays a manual choice (a wrong profile would play the owner's
    save); the token is written by `prepare` and consumed on launch so a stale plan never
    starts a run on its own; the end-of-run return to the main menu does not relaunch.
    Size: about 100-150 mod lines plus `starting_weapon` in the plan file, `- starting_
    weapon:` in proposals, and `prepare` writing the token.

## 2026-10-23 implemented: fit layer

The harness side of the owner's rulings above is in. The mod side (consuming
`launch.json`, scoring `prefer_sets`, checking the profile) is the next dispatch.

- **Unlock state carries items and weapons.** `unlock-state` adds
  `items_unlocked`/`items_locked` and `weapons_unlocked`/`weapons_locked`: dataset
  ids whose `Keys.generate_hash` is in the save's `items_unlocked` and
  `weapons_unlocked`. The save hashes the base weapon id (`weapon_rock`), not the
  per-tier `weapon_rock_1`; on the bot profile all 197 item hashes and all 56 weapon
  hashes matched (0 of 56 matched a `_<tier>` form): 197/247 items and 56/78 weapons
  unlocked.
- **`proposal fit --target ID [--character ID]`.** For a stat goal only (else
  `no stat goal for <target>`). Characters: every unlocked one, or only
  `requires_character` when the target names one. `need` = (goal - start) in the
  goal's direction, where start is the character's flat bonus on the goal stat,
  scaled by its gain modifier on that stat; a gain of -100% or lower is a veto
  (Chunky's speed: changes are nullified) and sorts last. Rank by `need` ascending,
  vetoes last, then a plan row in `build_plans.gd` first. Each line also shows `base`
  (start with the goal's sign: Old's -10 speed is +10 toward -20, Well Rounded's +5 is
  -5), the banned item groups that touch the goal items' tags, row, economy (flat
  harvesting) and DLC. Starting weapons (the top or chosen character's pool, unlocked
  only): set goal bonus at 6 weapons descending, then a type match with the row's
  `weapon_type`, then the row's weights on the weapon's scaling stats. On chal_slow
  the ranking puts Old first (need 10) with Rock first (Blunt, -10 speed at 6
  weapons); Well Rounded ranks near the bottom (need 25).
- **Proposal `- starting_weapon:`.** A fourth `## Next run` bullet: a dataset weapon id
  in the character's pool and unlocked, or `any`. A proposal without it stays valid
  and means `any` (`validate` returns errors only, so there is no warning line).
- **Launch contract.** `prepare` writes `danger` and `starting_weapon` into `plan.json`
  and `launch.json` beside it: `token` (`<proposal stem or plan_id>-<UTC stamp>`),
  `character_id`, `starting_weapon`, `danger`, `target_challenge`, `created_at`. It
  overwrites a stale token, and `prepare --plan` without `--danger`/`--starting-weapon`
  deletes one. The mod will consume and delete it on launch. The owner still loads the
  bot profile by hand and the mod must check it.
- **Shaping may pick a set.** When a set's bonus at 6 weapons covers at least 25% of the
  character's `need`, `proposal shape` writes `prefer_sets: {set_id: goal units x 1.5,
  at most 30}` and sets `weapon_type` to `any`; it never sets `weapon_set`. The mod
  ignores `prefer_sets` until its `score_weapon` change.

## 2026-10-23 implemented: mod sync (launcher, prefer_sets, telemetry, ask retarget)

The mod side of the owner's rulings is in (mod 0.1.1). Nothing here was run in the game;
the headless tests cover the pure logic and the scene extensions are read-checked only.

- **`prefer_sets`.** A plan key (number map, merged one level deep, accepted in a
  `plan_patch`). `shop_advisor.score_weapon` adds `bonus / 6` per set of the weapon
  (`shopping/set_score.gd`) to both a new weapon and a combine; `weapon_set` stays the
  hard gate. No other weapon constant moved.
- **Launcher.** `launch.json` (read once per process by the main menu) drives Start,
  character, weapon and danger through the screens' own press handlers on deferred
  frames; each step re-checks `Guards.profile_ok` and a failure cancels the launch,
  deletes nothing and sets `Launch refused: wrong profile (<id>)`. A missing or locked
  character, an unoffered weapon or a danger above the character's maximum cancels with
  its own status and deletes the file. `any` leaves the weapon to the owner. At wave 1
  `main.gd` deletes the file, records a `launch` event and enables the bot through
  `AutobattlerOptions.enable_bot()`, the same guarded path as Shift+Space. Starting
  weapons are the tier-1 resources: element `my_id` is `weapon_rock_1`, `weapon_id` is
  `weapon_rock`; the launcher tries the `_1` form first, then the bare id.
- **Telemetry.** New events `offer` (every board: first view and after each reroll),
  `crate` (take or recycle, with the score), `build` (both outcomes); `wave_end.stats`;
  snapshot `mats` (floor count from `main._active_golds`, bag = `bonus_gold`, nearest
  distance). Field list in the runbook's event table. The harness `collect.py` does not
  read them yet.
- **Ask retarget.** Defaults: `ask_floor` 6.0, `ask_tie_margin` 3.0, `ask_gold_floor` 200,
  `ask_big_share` 0.25, `ask_per_visit` 2. On every shop board, in order: the per-visit
  cap; a pivot (an `ask_on` id on the board); a dead board (nothing affordable at or
  above `min_buy`) never asks; a tie (best at least `ask_floor` and within
  `ask_tie_margin` of the second); a big purchase (gold at least `ask_gold_floor` and the
  best affordable option costs at least `ask_big_share` of the gold). Level-ups keep the
  old tie-or-below-floor rule (now with the 6.0 floor).
- **Not changed:** the crate take/recycle rule, `MIN_BUY_UNDER_GOAL`, the sidecar,
  `effect_score.gd`, the steering.

## 2026-10-23 reviewed and synced: mod 0.1.2 (launcher, prefer_sets, telemetry, ask retarget)

- Reviews: the harness fit layer by Opus 5.5 (9 findings, fixed by GPT 6.1 Sol high,
  `.superpowers/sdd/2026-10-23-fit-layer/`), the mod sync by GPT 6.1 Sol xhigh (7
  findings, 4 HIGH in the launcher: no re-evaluation after the owner loads the bot
  profile, Start pressed after a yield without a profile recheck, the token deleted on a
  wrong-profile refusal, co-op attempted; fixed by Opus 5.5 high), a Sol xhigh re-read
  (one gap left: the per-board ask counter advanced on rerolls the game rejects when all
  four slots are locked; fixed by Sol medium, `00239de`). Reports under
  `.superpowers/sdd/2026-10-23-mod-sync/`.
- Launcher rules as shipped: the launch file is evaluated each time the main menu is
  shown; every step re-checks the bot profile and solo mode; a refusal keeps the file
  and shows `Launch refused: ...`; Start, a cancellation or a stale-file discard consumes
  it; `any` as the starting weapon leaves that pick to the owner.
- Ask rules as shipped: never ask a dead board (no affordable option at or above
  `min_buy`), even when a goal item is offered; pivot when an `ask_on` id is on an
  affordable board; ask a genuine tie (best >= `ask_floor` 6 and margin < 3) or a big
  purchase (gold >= 200 and price >= 25% of gold); at most one ask per board view and
  `ask_per_visit` 2 per visit.
- Synced to the hidden Workshop item with the game closed (52 files). The scene
  extensions have never been compiled: the next launch is the compile check (read the
  Mod Loader log for parse errors; on the owner's profile the overlay should refuse the
  launch, and after loading profile 2 and returning to the menu the run should start).
- Accepted debt: `collect.py` does not render the new `offer`, `crate`, `build`, `mats`
  and `wave_end.stats` fields yet; the fit layer's duplicate pool-name helper; stale
  launch-file cleanup at every wave start (owner: keep, `prepare` is never run mid-run).

## 2026-10-23 run 4 (20261023-210533-old-d0): chal_slow FIRED at wave 10; died wave 18

- First run through the whole new chain: mod 0.1.2 compiled on launch, the launcher
  refused on the owner's profile, then picked Old, Rock and danger 0 after profile 2 was
  loaded, and switched the bot on 11 s into wave 1 (`launch` event, token consumed).
- **Target achieved.** Speed went -10 (start) to -13 (Ugly Tooth, wave 3) to -21 at wave
  10 (Ball and Chain -3 and Warrior Helmet -5, both wave 9); chal_slow fired at wave 10
  (`challenge` event, `is_target` true). Streamer is now unlocked. Side unlocks:
  chal_experimentation, chal_bonk_dog, chal_gatherer_4.
- **`ask_on` pivots did the work.** 5 goal-item sightings on 77 boards; 4 were bought,
  every one through a `pivot` ask answered `buy` (Ugly Tooth 35g w3, Ball and Chain 151g
  and Warrior Helmet 161g w9, Barricade 219g w17). The fifth, Bag at 52g with 23 gold on
  hand, was correctly not asked (dead-board rule). 22 asks in all (4 pivots, 1
  checkpoint, 9 shop, 8 level-up) against 11 in run 3; sidecar cost $0.089.
- **The post-target checkpoint ran** for the first time (wave 10): `revise_plan` moved
  weight to max HP 8, armour 7, dodge 5, harvesting 3, set `spend_surplus` and
  `harvest_cap` 30, rationale "target done, shift to survival". Later haiku buys (Acid x2,
  Metal Plate x3, Gentle Alien) followed that patch.
- **Death at wave 18** (junkie; six tier-3 melee weapons, 57 HP, damage per wave rising
  from 35 at w8 to 65 at w17). Old at danger 0 with a melee kit is fragile; the goal was
  met so this does not block the unlock loop, but Old's row is tuned for ranged.
- **`prefer_sets` did not steer.** 15 / 6 = 2.5 per Blunt weapon against a 22 base for
  any weapon, so the board filled with Primitive, Ethereal and Fire; Rock was the only
  Blunt weapon all run. To matter, the per-weapon term must be on the goal-item scale
  (Blunt is -1.67 speed per weapon, about 6.7 at weight 12 plus a bonus): tune in shaping
  (full set value per weapon, not a sixth) or in the mod's divisor. Measure-first done.
- **Crate rule, now with data:** Beanie (+speed) was taken from a crate at wave 10 with
  score -16 (speed -21 to -17 the next wave; the target had already fired). The step 7
  crate rule (recycle below 0) is justified. Six other crate takes scored 0 to 6.2.
- **Materials, first numbers:** mean 10.1 pickups on the floor per snapshot, bag up to 47
  gold swept at a wave end. The step 5 steering audit now has a baseline.
- Follow-ups: `collect.py` still renders none of the new events (offers, crates, build,
  mats, wave_end stats were read by hand); the run-4 report's Outcome line does not
  mention the fired target.

## 2026-10-24 implemented: per-weapon set values and report rendering

- `collect` now renders target firing in Outcome, speed from `wave_end.stats`, launch,
  offers with goal-item stars and purchases matched to the active board, crates, counted
  builds on either outcome, and a materials table. The materials run total uses the
  snapshot-weighted floor mean, maximum floor count and sum of each wave's last bag;
  the death wave's last snapshot is included. Old recordings retain their sections.
  Goal markers use a matching installed plan or saved proposal. `target_fired` was
  already present in the index builder and is retained.
- Read-only run-4 smoke: 77 offer rows, 39 matched buys, 7 crates, 18 material waves,
  and Metal Plate x3. Timing correction to the preceding run-4 entry: the `chal_slow`
  event at JSONL line 539 has no wave field, follows `wave_end` 9 (line 517), and
  occurs immediately before the wave-9 Warrior Helmet buy log (line 540).
  The report follows the requested latest-preceding-wave-end rule and says wave 9;
  wave 10 is the first wave-end stats snapshot showing -21, not the firing event.
- New harness contract: `prefer_sets[set_id]` is the score value of one additional
  weapon of that set, added as is by the mod. Shaping keeps the 25%-of-remaining-need
  selection threshold and caps each value at 30. `SET_WEAPON_FACTOR = 3`:
  Old's Blunt = 10 / 6 / tier-1 speed unit 3 * shaped weight 12 * 3 = 20 points.
  A base-22 Blunt weapon scores 42, above a non-set weapon's 22 and below a 100-point
  combine. This is comparable to mid goal items in the unchanged run-4 plan:
  Reinforced Steel scores 32.5 (26.5 above min_buy 6), Barricade 33.5 (27.5 above).
  The score tool only scores items and does not read `prefer_sets`, so it is unchanged.
- Harness verification: 627 tests pass with SyntaxWarning treated as error; Ruff lint
  and format checks pass. New fixture covers all new telemetry. No game or Godot run.
  The mod still needs its separate removal of the division by 6 before this contract
  takes effect in play. The completed proposal and run artifacts were left unchanged.

## 2026-10-23 owner ruling: the bar is "goal achieved"

- A run is judged on whether its target fired, not on surviving to wave 20, unless
  survival is part of the goal (a difficulty target, a "win with" challenge, a stat goal
  that needs late-wave items). Run 4 is a success by this bar: chal_slow fired at wave 10
  and the death at wave 18 is irrelevant to it.
- Consequences: the stagnation rule already keys on the target (it reads run 4 as
  "progressing"); the fit ranking needs a survival term only for goals that need late
  waves (to add when such a goal comes up, not before); the post-target checkpoint's
  "shift to survival" patch is a bonus, not a requirement; reports should lead with the
  target outcome (item 1 of the 2026-10-24 harness dispatch puts it in the Outcome line).

## 2026-10-24 audit C (GPT 6.1 Sol xhigh, read-only): steering, materials and trees

Report: `.superpowers/sdd/2026-10-24-steering-audit/sol-report.md` (brief beside it).

- **Two premise corrections.** Trees are already scanned out to 900 px (`PICKUP_RANGE`),
  not the pickup radius; Well Rounded's obstacle is only its `tree_value` 0 default (no
  steering row at all). And the bag is not "paid out" at the next wave: the game folds the
  bag into newly spawned pickups and debits it on spawn, so a bag reaching zero proves
  allocation to drops, not redemption into the wallet.
- **Run 4 numbers (first `mats` run).** Mean floor count by wave thirds 2.8 / 9.2 / 17.5:
  the backlog builds through the wave and peaks at its end. 333 material value was
  swept into bags over 17 waves (19.6 per wave, max 47 at wave 17). The quiet-draw
  condition (no enemy within 280 px) held in 24% of Old's snapshots against 88-89% in
  Well Rounded's runs 1 and 3; the stricter 420 px sweep condition in 9% versus 60%.
  Wave 17's backlog of 50 had zero quiet samples, so a quiet-only sweep would not have
  touched it. Death-wave leftovers (38 objects) are the only value lost outright.
- **Every steering constant is upstream BOTato's**, unchanged by the fork, tuned and
  validated at danger 5-6; the gold terms are documented tie-breakers that "cannot
  outbid a dodge", and upstream recorded a flat x1.2 greed dropping Well Rounded from
  waves 18/18/20 to 9/14/20. The per-row `sweep` is dormant on every row; Old already
  prices materials at 1.8 (2.25x Well Rounded's 0.8). Standing continuity (-1.2 after
  standing) can hold the potato on an idle quiet spot against a single distant drop.
  Dropped crates have no reward of their own: they ride the food value, zero at full HP.
  Experimental trap: `--arb-sweep` also toggles the blade swept-hitbox model.
- **Ranked:** (1) measure first: material value (not count), unattached value, bag in
  and out, collected value, trees spawned/felled, resolved reward components, at the
  next mod sync (50-100 lines); (2) a Well Rounded steering row with a positive
  `tree_value` when the goal allows, tested alone; (3) the existing per-row `sweep` at
  1.5 then 2.5, one arm at a time; (4) standing continuity made configurable; (5) a
  danger-aware quiet greed scale; (6) an explicit quiet-floor collection route, parked;
  (7) no scan-range change, it is not the limit. Proposed plan keys: `tree_policy`
  (auto / seek / preserve), material scale, quiet draw, `sweep` and radius, final-seconds
  value, standing continuity; steering reads none of the plan today.
- **Trees:** preserve for chal_forest (10 living at wave end), Cryptid (12 materials and
  3 regen per living tree) and Diver's wave 1; seek for chal_lumberjack (50 felled),
  Explorer, Pacifist and any unrestricted goal; chal_lootworm wants 20 material value
  left on the floor, which a sweep would defeat. `tree_value` 0 means "do not seek",
  not "preserve"; preservation needs spacing against incidental fire and has no row
  today (Cryptid has no steering row at all).
- **Verdict:** general steering changes go after the next target run; add the value and
  tree telemetry at the next routine mod sync and run a separate Well Rounded
  comparison; implement a narrow tree policy before a run only if that run's target
  needs it.

## 2026-10-24 implemented: mod sync 2 (crate rule, per-weapon sets, value and tree telemetry)

- **Crates:** items use the shop's `stat_score + item_bonus`; take at score >= 0,
  recycle below 0. Weapons retain `score_weapon >= 0` as the take rule. The `crate`
  event still records only an accepted action with its score; run 4's -16 Beanie
  would now be recycled. This scene branch is inspection-only here.
- **Sets:** `prefer_sets[set_id]` is added as is for each weapon's sets; the `/ 6`
  is removed. Old's Blunt value 20 therefore adds 20 to each Blunt weapon.
  All other weapon scoring is unchanged.
- **Materials:** snapshot `mats` is now `{floor, floor_value, unattached, bag, nearest}`.
  `floor_value` sums the same pickups' `.value`; `unattached` counts those with no
  `attracted_by`. Attracted pickups remain in floor/value/nearest. `wave_end` adds
  `materials: {floor_count, floor_value, bag_before, bag_after}` and `collected_value`
  (wave-end wallet minus wave-start wallet, before harvesting; net in-wave income).
  Optimized cleanup supplies `bag_after` immediately after cleanup. Animated cleanup
  supplies it on the first frame of the next wave, before material spawns debit it;
  that wave-end line is delayed and retains the completed wave's explicit `wave`.
  Closing the run before observation writes null for `bag_after`, never a guessed
  value. The bag reflects pickup effects/conversions, not just raw floor value.
- **Trees:** `wave_end.trees: {spawned, felled, alive}` counts the initial living
  neutrals plus each later spawn (including pooled respawns), combat deaths and
  living trees before cleanup. Cleanup deaths do not count as felled.
- **Scope and checks:** mod version 0.1.3; pure recorder builders/lifecycle and
  per-weapon set values have headless tests. Scene extensions are read-checked;
  no game launch or sync. `arb.pick`/`arb.threat` are omitted because `last_scores`
  carries totals only. `collect.py` rendering of these fields and its interpretation
  of delayed wave-end lines are follow-ups. Steering and ask rules are unchanged.

## 2026-10-24 reviewed and synced: mod 0.1.3 (crate rule, per-weapon sets, value and tree telemetry)

- Implemented by GPT 6.1 Sol high (three commits), reviewed by Sol xhigh read-only: one
  HIGH (holding `wave_end` until the post-cleanup bag is observed left `checkpoint`
  events without a wave, so the collector filed them one wave early), fixed by Sol medium
  (`58c57b7`: checkpoints carry `wave`, the collector prefers it). All scene hunks
  compiled by eye against the game source; per-snapshot cost is two linear passes at 1 Hz.
- Shipped: crate items scoring below zero are recycled (weapons unchanged); `prefer_sets`
  values add as is (Blunt 20 under Old's plan); `snapshot.mats` gains `floor_value` and
  `unattached`; `wave_end` gains `materials` {floor_count, floor_value, bag_before,
  bag_after, collected_value} and `trees` {spawned, felled, alive}; the arbiter's score
  components were not added (its `last_scores` holds scalar totals only).
- Synced to the hidden Workshop item with the game closed (52 files). Mod tests 129,
  harness 630, ruff clean. `collect.py` does not render the new `materials` and `trees`
  fields yet (follow-up).

## 2026-10-24 run 5 (20261023-233317-apprentice-d0): chal_dying FIRED at wave 10; won wave 20

- Apprentice, double barrel shotgun, danger 0, plan `apprentice-dying-v1`, mod 0.1.3,
  launched by the mod from `launch.json`. HP regeneration went 0 to -1 (wave 7), -2
  (wave 8), -5 at wave 10 (chal_dying fired; Sick unlocked), -9 by wave 19. Won at wave
  20 with 32 HP. Side unlocks: chal_survivor_5, chal_fruit_basket, chal_apprentice.
  Haiku cost $0.083 over 19 calls.
- Goal items: 10 sightings on 75 boards, 5 bought (Broken Mouth x2, Poisonous Tonic
  x3), all through `pivot` asks, plus a Broken Mouth taken from a crate at score 25.2;
  Goblet at wave 10 and two tonics went unbought (affordability or the per-visit cap;
  check the report's Offers table). The crate rule recycled Little Frog at -7.
- **Materials: the bag is not delayed income, it accumulates and is lost.** The new
  `wave_end.materials` shows the floor pinned at the game's 50-pickup cap from wave 5
  on (floor value 100-280 per wave), and `bag_before` growing from wave 11: 141, 227,
  288, 327, 322, 327, 379, 348, 312, 502, with `bag_after` 598 at the end of wave 20.
  The bag pays out only through newly spawned pickups, and with the floor saturated at
  50 almost nothing new spawns to carry it, so about 600 material value sat unspent at
  the end of a won run (and run 4's death-wave floor was lost outright). This is the
  owner's "bag of uncollected materials" from runs 1 and 2, now measured: the
  collection problem costs real gold, not just timing. It moves the Well Rounded
  steering comparison (audit C) from "after the next run" to "next".
- Trees: 31 felled over the run by incidental fire (shotgun); the per-wave counts work.
- Telemetry bug: `wave_end.materials.collected_value` is null on every wave (the wallet
  gain was never recorded); fix with the next mod sync. `collect.py` still renders
  neither `materials` nor `trees`.

## 2026-10-24 implemented: mod sync 3 (steering switches, collected_value)

- Mod 0.1.4 places the wave-start to wave-end wallet delta inside
  `wave_end.materials.collected_value`. The old hook put it at the event's top
  level; the builder now receives both wallet observations and keeps the delta
  through delayed cleanup. The hook fires before harvesting and room cleanup.
- Plan `steering` accepts `tree_value`, `sweep`, `sweep_radius`, `gold_value`,
  `stand_continuity` (numbers), and `tree_policy` (`auto`, `seek`, `preserve`).
  Entries merge one level deep and are available in sidecar patches. The live
  resolver refreshes through `PlanFile.load_cached`; same-second sidecar writes
  invalidate the cache. Character gates/phases remain active. `seek` defaults
  to tree reward 4 unless explicitly given; `preserve` forces reward 0 only,
  with spacing against incidental fire still out of scope.
- Explicit Well Rounded baseline row: material value 0.8, caution 1.0,
  `tree_value` 0, `sweep` 1.0; inherited `sweep_radius` 420 px and
  `stand_continuity` -1.2. The moving-continuity term is unchanged. A `steering`
  event immediately after each run header records the source character,
  applied plan overrides, all six resolved keys, initial material value and
  caution. It records initial settings once, rather than a time series.
- First experiment: Well Rounded on a target that allows trees, arm A with
  `steering: {"tree_policy": "seek", "sweep": 1.5}` versus the empty-object
  baseline. Judge `wave_end.materials` (`bag_before`, `bag_after`,
  `collected_value`) and `trees.felled`, alongside damage and target success.
  Run this arm against baseline before trying another arm; this combined arm
  measures the package, with separate tree/sweep arms needed for attribution.
- Pure logic and harness contracts have automated coverage. Scene extensions
  and steering remain inspection-only here; no game launch or installed-mod sync.

## 2026-10-24 target note: chal_uncorrupted completes only on a win

- The game excludes chal_uncorrupted from the per-effect stat-challenge check
  (`challenge_service.gd` `_should_add_stat_challenge`) and completes it only in the
  run-won path (`run_data.gd` ~1922: curse stat 0 at the win). So for this target the
  success bar includes surviving to wave 20 with curse at 0. The unlock state reports it
  as a stat goal (stat_curse, value 0), which the shaping treats as keep-at-zero: it bans
  the four curse items and weights curse -14. Proposal 7 (`well-rounded-uncorrupted-v1`)
  is steering experiment arm A on Well Rounded (`steering: {"tree_policy": "seek",
  "sweep": 1.5}`), so it is judged twice: the target (a win with 0 curse) and the
  materials numbers against run 5.

## 2026-10-24 owner rule: a curse-0 goal must avoid curse-giving enemies; the launcher must pin the zone

- Owner: at least one enemy type adds curse, so a curse goal must avoid it. Measured: the
  Sea Pig (Abyssal Terrors, `dlc_1`) "gives 1 curse on death" (wiki-enemies cache, line
  753); it is in the dataset's enemy list with `appears_in: []` for zone 1, no zone-1
  wave file under `.decompiled/zones` names it, and runs 4 and 5 saw only base-zone
  enemies (baby_alien, helmet_alien, chaser, charger, pursuer, bruiser, invoker,
  spitter, junkie, fin_alien, horned_charger). So in zone 1 the risk is zero today.
- The zone is not pinned: the character screen reads `ProgressData.settings.zone_selected`
  (a persisted setting, with a RANDOM option, `character_selection.gd` 36-51) and the
  launcher never sets it, so a manual pick of the Abyss or RANDOM on profile 2 would
  carry into a launched run. Fix: `launch.json` gains `zone` (default 0), the
  character-screen extension selects it before picking the character, and the run
  header records the zone.
- For the Abyss zone later: a plan steering key that shuns named enemies (`shun:
  ["sea_pig"]`, strong repulsion so auto-aim never gets in range) and a prompt note for
  Haiku; not needed while runs stay in zone 1. The curse stat also rises from cursed
  items (banned by shaping) and from a level-up option (`main.gd` 920), which the
  level-up scorer already weights at -14 under the shaped plan.

## 2026-10-24 finding: rows without a speed weight buy speed losses for free (run 7)

- Run 7 (`20261024-011838-well_rounded-d1`, danger 1) died at wave 19 pinned at the
  walls; speed fell 6 -> 2 through Helmet x2, Campfire, Honey and Shackles (Shackles also
  caps speed). The Well Rounded row has no `stat_speed` weight, so each item's negative
  speed effect scored 0 and the rules and Haiku treated it as free.
- It is general: 42 of the 50 rows in `shopping/build_plans.gd` carry no `stat_speed`
  weight (the rows that do use 1.4-9). Any of them can walk its speed into the floor.
- Proposal 9 (`well-rounded-difficulty-1-v2`) adds `stat_speed: 4.0` as the only change,
  with arm B steering held, so it is both the fix test and arm B's second reading. If it
  holds, the follow-up is a default speed weight for rows without one (a mod change via
  the usual brief and review), not per-proposal patches.
- Checked against run 6 (snapshots, per wave): through wave 12 run 7 kept enemies as far
  away as run 6 or farther (median nearest enemy 309-552 px vs 340-480) with similar live
  enemy counts, so sweep 2.5 shows no cost while speed was 4-6. From wave 13 run 7 had
  about twice run 6's live enemies, speed 4 then 2, the nearest enemy closed to about
  200-270 px, and wall time rose (edge < 150 px: 12% of wave 17, 30% of wave 19). Wave 19
  was a lap of the arena edge at speed 2 with about 100 enemies until horned bruisers
  caught it (152 damage in about 20 s). That fits speed plus danger-1 density; sweep is
  not ruled out late, which proposal 9 tests by holding it.

## 2026-10-24 owner observations (held as evidence, no action yet)

Ellie, watching runs, during run 8 (proposal 9):

1. **Idle with materials on the floor.** The character often stands still and waits while
   materials lie on the ground that it could collect. Context, not yet checked against
   it: the greedy material draw applies only with no enemy within 280 px; `stand_continuity`
   is -1.2; the arbiter has stand-and-shoot rewards (`FIRE_STILL_*` in `steering/arbiter.gd`);
   the quiet-floor route and the stand-still-bonus change are parked. Testable from the
   snapshots: frames with near-zero movement while `mats.nearest` is small and the nearest
   enemy is far.
2. **Loot enemies are not chased.** High-value enemies such as the looter (drops a crate)
   are not pursued; a kill depends on the looter wandering into weapon range. `grep -i looter`
   over `mod/Ellie-BrotatoBot/steering/` finds nothing, so the steering has no
   looter-specific term today. Testable: a `looter` appears as `nearest_threat` in run 7's
   wave 19 snapshots; count looter sightings against crates gained.

## 2026-10-24 run 8 (proposal 9): killed by its own items at the start of wave 11

- `20261024-080325-well_rounded-d1`, danger 1, `stat_speed: 4.0`. Wave 10 ended at 51 HP;
  wave 11 started at 1 HP and the first drain tick killed it ("killed by yourself", 0 enemy
  damage, position at the spawn point).
- Cause, measured: Blood Donation (wave 9, rule buy, score 40: +40 harvesting, plus
  `lose_hp_per_second` 1, the 60 one-point `?` damage events of wave 10) and Weird Ghost
  (wave 10, rule buy, score 5: +3 max HP, plus `hp_start_next_wave` -100). Together they
  are fatal on the next wave start with no regen tick in between.
- The mod has no handling for either key (`grep` over `mod/Ellie-BrotatoBot/` is empty):
  both are text-key effects capped at one unit of an unweighted stat, i.e. scored as free.
  Drain items: Blood Donation, Bloody Hand. HP-reset items: Weird Ghost, Hourglass, Broken
  Hourglass. This is deferred step 4 ("Weird Ghost's 1-HP downside") turning lethal.
- Speed held (5 through wave 9, 9 at wave 10; run 7 was 3-6 by then), so the weight did
  its job, but the run ended too early to test survival past wave 13 or arm B late.
- Stopgap: proposal 10 gives the three HP-reset items `item_bonus` -100 (the `score` tool
  shows -95 to -100), which keeps them under `min_buy` and makes crates recycle them.
- `ban_items` is a no-op on this profile: `_apply_bans` (`base_shop.gd` ~761) acts only when
  the game's ban mode is active, which needs chal_banned_items (open on profile 1). No run
  has ever logged a `ban` action, so the four curse bans in run 6 never applied; the curse
  weight of -14 kept those items out. Shaping and `brotato-next` should use negative
  `item_bonus` for hard exclusions until the mod enforces `ban_items` itself. Real fix (mod, one
  review): score the combination, never buy an HP-reset item while a drain item is held or
  the reverse, with a hard veto rather than a weight.

## 2026-10-24 owner rulings: review, not bans, for items the scorer cannot value

- Items like Weird Ghost and Blood Donation are not to be hard-banned; they need review. A
  plan routes them to Haiku through `ask_on` in the shop.
- Shop: add a `pass` action ("pass on item, not whole shop"): decline one option for the
  rest of the visit and keep shopping; `skip` still ends the visit.
- Crates: ask when the item has a description effect (a non-empty `text_key`), not only a
  stat block; 156 of 247 items have one.
- Whether such an item is right depends on the run's goal and the held items and weapons,
  so no fixed rule: the decision must carry that context.
- Owner: the review is only as good as the context Haiku gets. Measured in
  `sidecar/prompt.py`: the offered options get full dataset records and the objective gets
  the goal data, but held items render as bare ids and held weapons as id/type/sets, so an
  ask in run 8 would have shown `item_blood_donation x1` with no hint of its HP drain. The
  crate-ask task adds held-item effects to every screen's State section, capped and measured.
