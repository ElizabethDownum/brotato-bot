# Brotato bot runbook

## Mod

This section covers the in-game mod `Ellie-BrotatoBot` for Brotato 1.1.15.4
with Godot Mod Loader 6.0.0. It was written against branch `sdd/mod` at
`ec55a43`. Every path, key and file name below comes from the code at that
commit. Anything the code alone does not settle is marked "(verify)".

Paths used throughout:

| Name | Path |
|---|---|
| Repository | `C:\Users\eliza\Desktop\ClaudeFiles\brotato-bot` |
| Game folder | `D:\SteamLibrary\steamapps\common\Brotato` |
| Installed mod | `D:\SteamLibrary\steamapps\common\Brotato\mods-unpacked\Ellie-BrotatoBot` |
| Bot root (`user://brotato-bot`) | `%APPDATA%\Brotato\brotato-bot` |
| Save folder | `%APPDATA%\Brotato\<steam64 id>` |
| Game logs | `%APPDATA%\Brotato\logs` (`godot.log`, `modloader.log`) |

### 1. What this is, and the three rules

The mod plays a run by itself. It steers the potato, shops and picks
level-ups. It records each run to a JSON Lines file. When the rules cannot
pick a clear winner, it pauses the game and asks a file-based sidecar for a
decision. On any profile, F9 writes a snapshot of the game state for an
advisor without acting on anything.

The three rules:

1. **The bot profile belongs to the bot.** The bot acts only when the game's
   `current_profile_id` equals `bot_profile_id` in `config.json` (default
   `1`). Profile ids are 0-based. The profile menu labels its buttons
   "Profile 1", "Profile 2" and "Profile 3", so the bot's id 1 is most likely
   the button labelled **"Profile 2"** (verify). Step 3.1 shows how to
   confirm this.
2. **You launch the game and start every run by hand.** The bot never starts
   a run, never survives a return to the main menu, and never starts a game
   session enabled. Each run you press Shift+Space yourself.
3. **Any bot action on another profile, or during your own play, halts the
   bot.** If the bot tries to act on a non-bot profile, it halts with
   "wrong profile". A move key, an arrow key, IJKL, any gamepad button or a
   stick pushed past half-way halts it with "human input". The key also moves
   the potato on that same press.

### 2. Install / sync

1. Quit Brotato. The sync script refuses to run while `Brotato.exe` is
   running.
2. Run the headless tests:

   ```powershell
   pwsh -File C:\Users\eliza\Desktop\ClaudeFiles\brotato-bot\scripts\test_mod.ps1
   ```

   - Expect a final line `67 passed, 0 failed` and exit code 0. The count
     was measured at `ec55a43`.
   - `ERROR: Error parsing JSON` and `WARNING: PlanFile: ...` lines are
     expected. They come from the invalid-input tests.
   - If it says `Godot not found`, run
     `C:\Users\eliza\Desktop\ClaudeFiles\brotato-bot\scripts\get_godot.ps1`
     once, then run the tests again.
3. Copy the mod into the game:

   ```powershell
   pwsh -File C:\Users\eliza\Desktop\ClaudeFiles\brotato-bot\scripts\sync_mod.ps1
   ```

   - The script removes any `Pasha-AutoBattler` and `Ellie-BrotatoBot`
     folders under `mods-unpacked`. For each folder it removes it prints
     `Removed <path>`.
   - It then prints
     `Copied 46 files to D:\SteamLibrary\steamapps\common\Brotato\mods-unpacked\Ellie-BrotatoBot`.
     The count is the number of files in `mod\Ellie-BrotatoBot` at
     `ec55a43`, including the `.import` files.
   - Use `-GameDir <path>` only if the game moves.
4. Launch Brotato through Steam. The title screen shows the Mod Loader's
   one-time "mods are loaded" warning. Dismiss it.
5. Check that the mod loaded:
   - Open `%APPDATA%\Brotato\brotato-bot\probe.txt`. The mod writes the
     launch time there (local ISO time) every time it loads. A fresh
     timestamp means the mod ran.
   - Open `%APPDATA%\Brotato\logs\modloader.log`. There must be no `ERROR`
     line that mentions `Ellie-BrotatoBot`. The line
     `ERROR ModLoader:ThirdParty:Steam: Can't open workshop folder ...` was
     there before the mod existed. It is not ours.
   - Open `%APPDATA%\Brotato\logs\godot.log` and search it for
     `SCRIPT ERROR` and `Parse Error`. The game-side scripts are
     parse-checked only by this load (see Known limitations).
   - The title screen has a "Mods" button. It should list BrotatoBot 0.1.0
     by Ellie, from `manifest.json` (verify what that page shows). The
     manifest's two Mod Loader options, "Enable Bot" and "Autoshop", are
     **not** the switch. Only Shift+Space turns the bot on.

### 3. One-time setup

#### 3.1 Create the bot profile

1. On the title screen, open the profile menu (the main-menu button reads
   "Profile N").
2. Select the second button ("Profile 2"), then "Load Profile". Most likely
   this is profile id 1 (verify).
3. Start any run and play at least one wave by hand. The harness notes say
   the save file may only appear after a save point (verify).
4. Confirm the id. Load a run on the profile you are about to use and press
   Shift+Space:
   - On your own profile (id 0) the overlay must read
     `Bot refused: wrong profile (0)`. The number in brackets is the
     current profile id.
   - On the bot profile it must not say "wrong profile". If `plan.json`
     does not exist yet, it says `Bot refused: no plan at user://brotato-bot/plan.json`.
     That is fine at this point.
5. Press Shift+Space again if the bot turned on, then quit to the main menu.

The game stores the selected profile in `settings.json` (`current_profile_id`)
and starts on it next time. Switch back to your own profile before you play
by hand.

#### 3.2 Turn off "Pause on losing focus"

1. Main menu → Options. Open the Audio page; its right-hand column has
   "On losing focus" and below it the switch **"Pause on losing focus"**.
   This comes from `ui/menus/pages/menu_options.tscn`, node
   `Audio_Container/.../RightContainer/PauseOnFocusLostButton`.
2. Turn it off. The setting is global (`settings.pause_on_focus_lost` in
   `%APPDATA%\Brotato\<steam64 id>\settings.json`), so it also affects
   your own play.
3. If it is on, at the start of every bot-profile wave:
   - Overlay line 1 reads `Warning: pause_on_focus_lost is true`.
   - Overlay line 4 reads `focus: pause_on_focus_lost`.
   - The run file gets one `warning` line per run with
     `"reason":"pause_on_focus_lost is true"`.
4. Leave "Mouse Only" (Options, Gameplay page) **off** for bot runs. See
   Known limitations.

#### 3.3 Optional: show the overlay while the bot is idle

The overlay always shows while the bot is not idle, and whenever a status
line is set (for example `Bot refused: ...` or `Exported: ...`). To also see
it while idle (`BOT idle` plus the plan line), turn on AI visuals:

1. Quit the game. The mod rewrites the file on every toggle.
2. In `%APPDATA%\Brotato\brotato-bot\options.cfg`, section `[options]`, set
   `ENABLE_AI_VISUALS=true`. The mod first writes this file when the bot is
   toggled or the main menu is shown again, so it may not exist before
   that.
3. `ENABLE_AUTOBATTLER` and `ENABLE_AUTOSHOP` in that file are written but
   never read back. The bot always starts a session off.

#### 3.4 `config.json`

- **Location:** `%APPDATA%\Brotato\brotato-bot\config.json`.
- **Optional.** A missing, unreadable or invalid file means every default
  applies. Keys you leave out keep their defaults. Unknown keys are ignored.
  A value of the wrong type falls back to its default, with a warning in
  `godot.log`.
- **Read once, at game start** (`BotRuntime._ready`). After you edit it,
  restart the game.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `bot_profile_id` | int | `1` | The only profile the bot may act on. |
| `request_timeout_ms` | int | `45000` | How long a `shop`, `levelup` or `pivot` decision waits for a response. |
| `checkpoint_timeout_ms` | int | `120000` | How long a `checkpoint` decision waits. |
| `ask_tie_margin` | float | `3.0` | The bot asks when the best two affordable scores are closer than this. |
| `ask_floor` | float | `4.0` | The bot asks when the best affordable score is below this. |
| `target_challenge` | string | `""` | The challenge id to watch for, e.g. `chal_gatherer_1`. A non-empty `target_challenge` in `plan.json` overrides it. |
| `export_hotkey` | string | `"F9"` | Key name for the advisor export, as Godot names keys (`OS.find_scancode_from_string`). An unknown name falls back to F9. |

The ask rule needs at least two affordable options. Every level-up option
counts as affordable. The rule applies only while a sidecar heartbeat is
fresh (section 4).

Copy-pasteable, all defaults:

```json
{
  "bot_profile_id": 1,
  "request_timeout_ms": 45000,
  "checkpoint_timeout_ms": 120000,
  "ask_tie_margin": 3.0,
  "ask_floor": 4.0,
  "target_challenge": "",
  "export_hotkey": "F9"
}
```

#### 3.5 `plan.json`

- **Location:** `%APPDATA%\Brotato\brotato-bot\plan.json`.
- **Must exist** for the bot to turn on. Shift+Space checks only that the
  file exists. A file that fails to load is ignored, with a warning in
  `godot.log`, and the built-in plan is used.
- **Required keys:** `plan_id`, `character_id` and `plan`, where `plan` is
  an object.
- **Optional key:** `target_challenge` (string, default `""`). When it is
  non-empty it wins over `config.json`'s.
- **Wrong character:** a plan written for another character never applies.
  The bot then uses its built-in plan for the character you picked, and
  `plan_id` reads `builtin` in the run header, state exports and overlay.
- **How `plan` combines with the built-in plan:** the keys in `plan` are laid
  over the built-in plan for that character (`shopping/build_plans.gd`).
  `stats` and `item_bonus` merge one level deep. Every other key replaces the
  built-in value whole. An empty `"plan": {}` means "use the built-in plan".
- **Re-read when changed.** The shop and level-up code reload the file when
  its modification time changes, so an edit takes effect at the next shop or
  level-up.
- **Sidecar patches:** a `revise_plan` response's `plan_patch` is merged the
  same way and saved back to `plan.json` (written to a temp file, then
  renamed). If `plan.json` is missing, it is created with `plan_id`
  `sidecar-<decision id>`. A patch is refused when the file belongs to
  another character or exists but does not load.

Common `plan` keys. `shopping/build_plans.gd` documents the full set.

| Key | Meaning |
|---|---|
| `weapon_type` | `"ranged"`, `"melee"` or `"any"` |
| `stats` | stat key → weight, e.g. `"stat_ranged_damage": 8.0` |
| `harvest_cap` | stop favouring harvesting once it reaches this |
| `item_bonus` | item id → extra score |
| `max_weapons`, `reroll_keep`, `max_rerolls`, `min_buy` | shop economy (ints, except `min_buy`) |
| `gold_floor` | gold held back from wave 5 on (int) |
| `prefer_weapons`, `ban_items` | lists of weapon / item ids |
| `ask_on` | ids that always trigger a `pivot` decision when offered |

`ask_on` is matched against shop offers (item and weapon ids, e.g.
`item_bag`, `item_scar`, `weapon_smg_1`) and level-up options (upgrade ids,
e.g. `upgrade_armor_1`). All five ids above exist in the game's resources. A
match matters only while the sidecar heartbeat is fresh. Leave `ask_on` empty
(`[]`) for normal runs. Use it only to force a decision during testing.

Example for Well Rounded. The `plan` values repeat the built-in ones, except
`stat_ranged_damage`, so the effect is small and easy to see:

```json
{
  "plan_id": "well-rounded-v1",
  "character_id": "character_well_rounded",
  "target_challenge": "",
  "plan": {
    "weapon_type": "ranged",
    "stats": {"stat_ranged_damage": 9.0},
    "max_rerolls": 15,
    "min_buy": 2.0,
    "ask_on": []
  }
}
```

### 4. Running a bot run

1. Launch Brotato. Select the bot profile (section 3.1).
2. Check that `%APPDATA%\Brotato\brotato-bot\plan.json` exists and names the
   character you will pick.
3. Start a run as usual: pick the character, weapon and danger. To navigate
   the menus, use the mouse rather than WASD or the arrows. Navigating with
   keys while the bot is on halts it.
4. When wave 1 has started, take your hands off the move keys and the
   gamepad, then press **Shift+Space**. A held move key repeats and halts the
   bot at once.
   - If the bot refuses, line 1 reads
     `Bot refused: wrong profile (<id>)` or
     `Bot refused: no plan at user://brotato-bot/plan.json`. A `warning`
     line goes into the run file and the bot stays off.
   - If it accepts, the AI marker appears on the potato, it starts steering,
     and from then on it shops and picks level-ups.
5. Read the overlay. It sits top-left at (8, 8) and has four lines:

   | Line | Shows |
   |---|---|
   | 1 | The status. It can be `BOT acting`, `BOT idle`, `DECIDING: <kind> <N>s` (counts down), `HALTED: <reason>`, `RUN COMPLETE: win` or `RUN COMPLETE: death`, `TARGET: <id> DONE`, `Bot refused: <reason>`, `Exported: <path>` or `Warning: pause_on_focus_lost is true`. |
   | 2 | `plan <plan_id> \| target <id or none>`. The plan id is `builtin` when the plan file does not apply, and `-` when no character is known. |
   | 3 | The last decision: `<kind>: <action> #<option_index> via <source>`. Examples: `shop: buy #2 via haiku`, `shop: - via timeout`. The line is blank until the first decision. |
   | 4 | Warnings: `focus: pause_on_focus_lost` and/or `no plan.json`. Blank when there are none. |

6. Where files land. All are under `%APPDATA%\Brotato\brotato-bot\`:

   | File | Written when |
   |---|---|
   | `runs\<run_id>.jsonl` | Opened when wave 1 starts, on any profile. `run_id` is `YYYYMMDD-HHMMSS-<character without "character_">-d<danger>`, e.g. `20261022-201500-well_rounded-d0`. A resumed or retried wave with no open run starts a new file whose header has `start_wave > 1`. |
   | `state\<run_id>-<NNN>.json` | Each decision and each F9 press. `NNN` counts per run from `001`. |
   | `requests\<run_id>-<NNN>.json` | Each decision request, with the same `NNN` as its state file. The mod never deletes these. |
   | `responses\<run_id>-<NNN>.json` | Written by the sidecar. The mod reads each one once and deletes it. Responses for any other id are deleted unread. |
   | `options.cfg`, `coop_state.cfg`, `probe.txt` | The mod's own settings, co-op state and load probe. |

   Event kinds in the run file (`{"t": ms since start, "kind": ..., ...}`):

   | Kind | Data | When |
   |---|---|---|
   | `header` | `character_id`, `danger`, `plan_id`, `profile_id`, `game_version`, `mod_version`, `start_wave`, `run_id` | first line |
   | `snapshot` | position, heading, threats, ... | about 1 Hz, only while the bot is enabled |
   | `damage`, `dash`, `bullet_hell` | — | only while the bot is enabled |
   | `death` | `wave`, `position`, `killer`, `last_threats`, `build`, `dmg_w` | player 0 dies |
   | `wave_end` | `wave`, `hp`, `gold`, `damage_taken`, `kills` | every wave end |
   | `warning` | `reason` | refused enable; `pause_on_focus_lost is true` |
   | `halt` | `reason` (`human input`, `wrong profile`) | the bot halts |
   | `export` | `export_kind`, `path`, `seq` | every state export (F9 or a decision) |
   | `decision` | `request_kind`, `id`, `source`, `response` | every decision request. `source` is `haiku` (valid answer), `invalid`, `timeout`, `interrupted` or `busy`. |
   | `decision_applied` | `id`, `action`, `option_index`, `applied` | shop only, after a decision. `applied` is `buy`, `lock`, `reroll`, `skip`, `revise_plan` or `rule`. |
   | `levelup` | `picked`, `alternatives`, `source` (`haiku`, `rule`, `timeout`) | every bot level-up pick |
   | `challenge` | `id`, `is_target` | a challenge completes for the first time on this profile |
   | `checkpoint` | `id`, `action`, `applied`, `reason` | the target checkpoint |
   | `complete` | `outcome` (`win`, `death`), `wave`, `extra` (`killer` on death) | the run ends while the bot plays |
   | `end` | `outcome` (`won`, `death`, `abandoned`, `quit`), `wave`, `hp`, `gold` | always the last line |

7. **`DECIDING: <kind>`** (`shop`, `levelup`, `pivot` or `checkpoint`).
   - The bot has written a request and **paused the game**. It polls
     `responses\` every 0.25 s. It waits up to `request_timeout_ms` (45 s),
     or `checkpoint_timeout_ms` (120 s) for a checkpoint. If no answer comes,
     the rules decide and the game resumes.
   - The bot asks only when `%APPDATA%\Brotato\brotato-bot\sidecar.alive`
     was modified within the last **10 s**. Otherwise the rules decide at
     once: no request, no pause and no `decision` line.
   - A shop asks at most once per visit, before its first buy.
   - Move keys do nothing while the game is paused. See Known limitations
     for how to take over afterwards.
8. **Stopping the bot:**
   - **Shift+Space** turns it off cleanly: `BOT idle`, no `halt` line.
   - **Any move key, arrow, IJKL, gamepad button or stick** halts it:
     `HALTED: human input`, a `halt` line, and the key moves the potato.
   - **Switching profile** needs the main menu, which already turns the bot
     off. If the bot is ever acting while the profile is not the bot
     profile, its next action (or the next wave start) halts it with
     `HALTED: wrong profile`.
   - **Returning to the main menu** always turns the bot off. A halted or
     stopped bot comes back only through Shift+Space, which re-checks the
     profile and the plan.
9. **Run end.** On death, or when the run is won, line 1 reads
   `RUN COMPLETE: death` or `RUN COMPLETE: win`. Both bot flags switch off.
   The post-run screens are not touched. The run file ends with a `complete`
   line and then exactly one `end` line. The end line says `won` where the
   complete line says `win`. For the next run, start it by hand and press
   Shift+Space again.

### 5. Advisor mode (any profile)

1. During your own play, on any profile and with the bot on or off, press
   **F9** (or the key in `export_hotkey`). It also works from the ESC pause
   menu.
2. For 5 s, line 1 reads `Exported: <full path>`. Then the previous status
   comes back.
3. The file goes to `%APPDATA%\Brotato\brotato-bot\state\`:
   - `<run_id>-<NNN>.json` while a run file is open. That is any run started
     with the mod loaded, on any profile. The open run file also gets an
     `export` line.
   - `norun-<YYYYMMDD-HHMMSS>-<NNN>.json` with no open run (e.g. at the main
     menu).
4. The file holds `schema_version` 1, `kind` (`"advise"` for F9), `run_id`,
   `seq`, `exported_at`, `wave`, `danger`, `character_id`, `hp`, `max_hp`,
   `gold`, `stats`, `weapons`, `items`, `shop`, `levelup_options`,
   `unlocks_this_run`, `recent`, `plan_id` and `target_challenge`.
   - In the shop, `hp` and `max_hp` are null and `shop` lists the unbought
     slots.
   - `recent` is empty unless the bot was enabled.
5. F9 never buys, picks, steers or changes the bot's state.

### 6. Attended verification checklist

These are the checks the implementers could not run without the game. Do them
in order. Note pass or fail, and anything unexpected, for each numbered step.

Helper for reading the newest run file. Paste it into PowerShell once per
session:

```powershell
$Bot = "$env:APPDATA\Brotato\brotato-bot"
function Show-BotRun([string[]]$Kind) {
    $run = Get-ChildItem "$Bot\runs\*.jsonl" | Sort-Object LastWriteTime | Select-Object -Last 1
    "== $($run.Name)"
    Get-Content -LiteralPath $run.FullName | ForEach-Object { $_ | ConvertFrom-Json } |
        Where-Object { -not $Kind -or $Kind -contains $_.kind } |
        ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 8 }
}
# e.g. Show-BotRun header,wave_end,halt,warning
```

#### 6.1 Load and Steam Cloud (Task 1 Step 5, Task 4 Step 0)

1. Do section 2 steps 3-5. Expect: a fresh `probe.txt`, no `ERROR` line in
   `modloader.log` that names the mod, and no `SCRIPT ERROR` in `godot.log`.
   - Also note whether `godot.log` complains about `defect.png` or a missing
     `.stex`. That would be the AI marker icon, inherited from BOTato.
2. Quit the game. Wait one minute. Then run:

   ```powershell
   Get-ChildItem 'C:\Program Files (x86)\Steam\userdata\*\1942280\remotecache.vdf' |
       Select-String -SimpleMatch 'brotato-bot'
   ```

   Expect no output, which means Steam Cloud does not sync the bot root.
   Record the result under "Result" in
   `C:\Users\eliza\Desktop\ClaudeFiles\brotato-bot\learnings\steam-cloud.md`.
   If anything matches, stop and report it: the root must move to
   `%LOCALAPPDATA%`.

#### 6.2 One recorded wave (Task 4 Step 6)

1. Bot profile, Danger 0, `plan.json` present. Start a run, press Shift+Space
   in wave 1, let the bot play one wave, then quit the game.
2. Expect a new `runs\<run_id>.jsonl` with one `header` (`profile_id` 1), at
   least 10 `snapshot` lines and at least one `wave_end`. Quitting adds
   `end` with `"outcome":"quit"`.
   Evidence: `Show-BotRun header,wave_end,end`.

#### 6.3 Safety guards (Task 5 Step 6)

1. Your own profile (id 0), in a run, press Shift+Space. Expect: no AI marker,
   no self-movement, line 1 `Bot refused: wrong profile (0)`. Evidence: a
   `warning` line with `"reason":"wrong profile (0)"`.
2. Bot profile, with `plan.json` renamed (e.g. to `plan.off.json`): press
   Shift+Space. Expect `Bot refused: no plan at user://brotato-bot/plan.json`.
   The bot stays off. Line 4 reads `no plan.json` within about 1 s. Rename
   the file back.
3. Bot profile with `plan.json`: press Shift+Space. Expect the AI marker,
   steering, and no refusal text. At the end of wave 1 the shop buys by
   itself and level-ups are picked. Then press W. Expect `HALTED: human input`,
   the marker gone, and the potato moving on that very press. Evidence: a
   `halt` line with `"reason":"human input"`. Repeat with an arrow key and a
   gamepad stick push. Shift+Space turns it back on.
4. While the bot acts, press Shift+Space twice. The first press turns it off
   with no `HALTED`: the status clears, and the block hides unless AI
   visuals are on. The next shop is not auto-bought. The second press turns it on again.
5. Turn the bot on, then quit and restart the game. Expect the bot to start
   off (no marker), even though `options.cfg` says `ENABLE_AUTOBATTLER=true`.
6. With "Pause on losing focus" **on**, start a bot-profile run. Expect
   `Warning: pause_on_focus_lost is true` on line 1 and
   `focus: pause_on_focus_lost` on line 4. Evidence: exactly one `warning`
   line with that reason in the run file. Turn the setting off again.
7. Turn the bot on in a menu, then navigate with arrows or WASD. Expect
   `HALTED: human input`. This is by design.
8. After a bot-profile session with the bot on, quit to the main menu,
   switch to your own profile and press Continue. Expect: the shop does not
   buy anything and no level-up is picked for you.
9. Return to the main menu from a bot run. Expect: the status text clears.
   The next run has no marker until you press Shift+Space.
10. Optional: with "Mouse Only" on (single player), move the mouse while the
    bot acts. Expect `HALTED: human input`. Turn Mouse Only off afterwards.

#### 6.4 Advisor export (Task 6 Step 6)

1. Your own profile, mid-wave, bot off: press F9. Expect line 1
   `Exported: C:/Users/eliza/AppData/Roaming/Brotato/brotato-bot/state/<run_id>-001.json`
   for about 5 s, then the previous text. The file has `"kind": "advise"`,
   `"schema_version": 1`, and `wave`, `gold`, `hp` and `max_hp` matching the
   HUD. It also has `character_id`, non-empty `stats`, your weapons and
   items, `"shop": []` and `"levelup_options": []`. The bot's state does not
   change.
2. In the shop, press F9. Expect `-002.json`, with `shop` listing the
   unbought slots (price, `locked`, `advisor_score`) and `hp`/`max_hp`
   null.
3. At a level-up screen, press F9. Expect `levelup_options` with up to 4
   entries (`stat`, `value`, `advisor_score`).
4. During a bot run, run `Show-BotRun export`. Expect `export` lines. After a
   few seconds of bot play, an exported file's `recent` holds up to 10
   snapshots.
5. At the main menu, press F9. Expect
   `state\norun-<YYYYMMDD-HHMMSS>-<NNN>.json`.
6. Mid-wave, open the ESC pause menu and press F9. Expect a file and
   `Exported: <path>`. The text reverts after 5 s even while paused.
7. With a `plan.json` for a different character, press F9. Expect
   `"plan_id": "builtin"`.

#### 6.5 Run completion (Task 7 Step 4)

1. Bot profile, Danger 0, a strong plan. Let the bot play to death or to the
   wave 20 win.
2. Expect line 1 `RUN COMPLETE: death` or `RUN COMPLETE: win`.
3. Evidence: `Show-BotRun complete,end`. The last two lines must be
   `complete` (`"outcome":"win"` or `"death"`, `wave`, `extra`; on death
   `extra.killer` equals the `death` line's `killer`) and then `end`
   (`"outcome":"won"` or `"death"`). There must be exactly one `end` in the
   file.
4. Any post-run shop or level-up is not automated. Note which outcome and
   wave occurred.

#### 6.6 Decisions with a fake sidecar (Task 8 Step 7)

Setup:

- Bot profile, bot on, `plan.json` present.
- To make a shop ask reliably, put an item you expect to see into the plan's
  `ask_on`, e.g. `"ask_on": ["item_scar"]`. Otherwise a shop asks only on a
  near-tie (within `ask_tie_margin`, 3.0) or a weak offer (best score under
  `ask_floor`, 4.0).
- Optional: to shorten the waits, set `"request_timeout_ms": 20000` in
  `config.json` and restart the game.

Keep-alive loop (the heartbeat). Run it in a **separate** PowerShell window.
Ctrl+C stops it. Once it stops, the file is stale within 10 s and the bot
stops asking.

```powershell
$f = "$env:APPDATA\Brotato\brotato-bot\sidecar.alive"
while ($true) {
    if (-not (Test-Path $f)) { New-Item $f | Out-Null } else { (Get-Item $f).LastWriteTime = Get-Date }
    Start-Sleep 3
}
```

Hand-written response. The mod reads only `*.json` names, so writing a
`.json.tmp` first and renaming it avoids a half-read file:

```powershell
$Bot = "$env:APPDATA\Brotato\brotato-bot"
$req = Get-ChildItem "$Bot\requests\*.json" | Sort-Object LastWriteTime | Select-Object -Last 1
Get-Content $req.FullName      # read the options; pick an affordable index
$id = $req.BaseName
New-Item -ItemType Directory -Force "$Bot\responses" | Out-Null
'{"action":"buy","option_index":0,"confidence":0.9,"rationale":"test","tags":[]}' |
    Set-Content -NoNewline -Encoding ascii "$Bot\responses\$id.json.tmp"
Move-Item "$Bot\responses\$id.json.tmp" "$Bot\responses\$id.json"
```

1. **No heartbeat.** Make sure the loop is not running and `sidecar.alive`
   is older than 10 s, or absent. Expect: shops never pause, no new file in
   `requests\`, and no `decision` line. Level-ups log `levelup` with
   `"source":"rule"`.
2. **Heartbeat, no response.** Start the loop. At the next shop that asks,
   expect the game frozen and line 1 `DECIDING: shop 45s` (or
   `DECIDING: pivot 45s` for an `ask_on` hit), counting down.
   `requests\<run_id>-<NNN>.json` exists, and so does `state\<run_id>-<NNN>.json`
   with the same `NNN`. After the timeout the game resumes, line 1 returns
   to its previous text, and the bot shops by its rules. Evidence:
   `Show-BotRun export,decision,decision_applied` shows `export`, then
   `decision` (`"request_kind":"shop"`, `"source":"timeout"`,
   `"response":null`), then `decision_applied` (`"applied":"rule"`).
   Optional: press F9 during the wait. Line 1 shows `Exported: ...`, and
   after the decision it shows the pre-decision text, not `DECIDING`.
3. **Hand-written response.** With the loop running, at the next asking shop
   run the response block above, with an affordable `option_index`. Expect
   the game to resume within about 1 s and buy that slot. The response file
   is gone. Evidence: `decision` with `"source":"haiku"` and the response
   object, then `decision_applied` with `"action":"buy"` and
   `"applied":"buy"`. Line 3 reads `shop: buy #<n> via haiku`.
4. **ESC during DECIDING: shop.** At the next asking shop, press ESC once
   while `DECIDING` shows. Expect the game to resume at once without waiting
   for the timeout. Line 3 reads `shop: - via interrupted`. Evidence: a
   `decision` line with `"source":"interrupted"`, then `decision_applied`
   `"applied":"rule"`. If a pause menu opens instead and the game stays
   frozen, write down exactly what you saw, then choose Resume.
5. **Alt-tab** away during a decision and back. Expect: nothing changes and
   no pause menu appears. Drop a response afterwards. Expect one resume, one
   buy, and exactly one `decision` line for that id.
6. Optional, **level-up.** With the loop running and a close level-up,
   expect `DECIDING: levelup`. A response
   `{"action":"pick","option_index":1,"confidence":0.8}` picks the second
   option. Evidence: `decision` (`"source":"haiku"`) and `levelup` with
   `"source":"haiku"`. With no response, after the timeout `levelup` says
   `"source":"timeout"`.

Stop the keep-alive loop and remove `ask_on` entries when done.

#### 6.7 Target checkpoint (Task 9)

1. Pick a target the bot profile has **not** completed yet:
   `chal_gatherer_1` (collect 300 materials, counted across the profile's
   lifetime). If the bot profile already has it, use `chal_gatherer_2` or
   `chal_survivor_1`.
2. In `config.json` set `"target_challenge": "chal_gatherer_1"`. Optionally
   also set `"checkpoint_timeout_ms": 20000`. Leave `plan.json`'s
   `target_challenge` empty, or set it to the same id. Restart the game.
   Expect line 2 `plan <id> | target chal_gatherer_1` once the run starts.
3. Start the keep-alive loop from 6.6. Without it, the checkpoint does not
   pause: it logs `checkpoint` with `"applied":"skip"` and
   `"reason":"no_sidecar"`. The loop also makes close shops ask and wait.
4. Bot run on Danger 0. Within about 4-7 waves the target fires. Expect line 1
   `TARGET: chal_gatherer_1 DONE`. At the end of that wave, expect
   `DECIDING: checkpoint <N>s` with the game paused. It resumes on a response
   or at the timeout.
5. Evidence: `Show-BotRun challenge,wave_end,export,decision,checkpoint`
   shows `challenge` (`"id":"chal_gatherer_1"`, `"is_target":true`),
   `wave_end`, `export` (`"export_kind":"checkpoint"`), `decision`
   (`"request_kind":"checkpoint"`), then `checkpoint` (`applied` `timeout`,
   `skip` or `revise_plan`).
6. Optional: answer with
   `{"action":"revise_plan","plan_patch":{"max_rerolls":5},"confidence":0.7}`
   using the response block in 6.6. Expect `checkpoint` `"applied":"revise_plan"`,
   `plan.json` now containing `"max_rerolls": 5`, and line 3
   `checkpoint: revise_plan via haiku`.
7. **ESC during DECIDING: checkpoint.** Do this on another run, or with a new
   target, since the checkpoint happens once per run. Press ESC once while
   `DECIDING: checkpoint` shows. Expect the game to resume, the overlay to
   return to the bot's status, a `decision` line with
   `"source":"interrupted"` and a `checkpoint` line with `"applied":"skip"`
   and `"reason":"interrupted"`. After that the bot is still on (verify that
   the next wave plays normally).

#### 6.8 Overlay (Task 10)

1. Bot profile, AI visuals on (section 3.3), bot off. Expect four lines:
   `BOT idle`, `plan <id or -> | target <id or none>`, a blank line, and the
   warnings line. With AI visuals off and nothing set, the block disappears.
   F9 shows `Exported: <path>` for 5 s even then.
2. Shift+Space in a run: `BOT acting`, and line 2 shows `builtin` or the
   plan file's id, plus the target.
3. During a decision: `DECIDING: <kind> 45s` counting down (120s for a
   checkpoint) while the game is paused. Afterwards line 1 is back to the
   previous status and line 3 shows the decision.
4. Halt: `HALTED: <reason>`, and the block stays.
5. Run end: `RUN COMPLETE: win|death`. Back at the menu: `BOT idle` (visible
   only with AI visuals on).
6. The block survives shop ↔ wave scene changes.

### 7. Known limitations

- **Mouse Only halts the bot.** With the game's "Mouse Only" setting on in
  single player, any mouse movement or click counts as human input. Keep it
  off for bot runs.
- **A held key halts at once.** A move key still held when you press
  Shift+Space repeats and halts the bot immediately. Menu navigation with
  WASD or the arrows also halts it.
- **Restarting from the pause menu keeps the bot's state.** Only the main
  menu turns the bot off. A run restarted from the pause menu starts with
  the bot still on, if it was on.
- **Taking over after a decision.** While the game is paused for a decision,
  move keys are not processed and do not halt the bot. When the game
  resumes, press a move key to take control.
- **AI buys skip the rule limits.** A `buy` from the sidecar checks only that
  the slot is still there and affordable. It ignores `min_buy`, `gold_floor`
  and the locked-weapon `save_floor`.
- **No fresh heartbeat means no asking.** Without a `sidecar.alive` touched
  within 10 s, the rules decide instantly, with no request and no pause. The
  heartbeat check has 1 s resolution.
- **The plan line is cached.** Line 2 refreshes only at run start or after a
  sidecar plan patch. A hand edit to `plan.json` mid-run takes effect at the
  next shop or level-up, but line 2 still shows the old id. Line 4's
  `no plan.json` refreshes within about 1 s.
- **`config.json` is read only at game start.** Restart the game after
  editing it.
- **Game-side code is checked only by loading the game.** The headless tests
  cover the pure `core/` scripts. `bot_runtime.gd`, `autobattler_options.gd`,
  `extensions/main.gd`, `base_shop.gd` and `upgrades_ui.gd` reference game
  globals, so their first real compile is a game launch. Check `godot.log`
  after every sync (section 2, step 5).
- **The bot profile is a guess until confirmed.** Profile ids are 0-based and
  the menu labels are 1-based. Do 3.1 step 4 once.
- **Runs are recorded on every profile.** Any run started with the mod loaded
  gets a `runs\*.jsonl` file: `header`, `wave_end`, `death`, `end`, `warning`
  and `export` lines. The input-level events (`snapshot`, `damage`, `dash`,
  `bullet_hell`) are written only while the bot is enabled, so your own
  play's inputs are not logged.
- **A mid-wave toggle leaves gaps.** Snapshots and damage are logged only
  while the bot is enabled, so a wave where it was toggled has a `wave_end`
  `damage_taken` and `kills` that do not match the logged damage events.
- **A target that fires during a decision.** If the target fires while
  `DECIDING` shows, the decision restores the status from before it started,
  so `TARGET: ... DONE` is not shown. The `challenge` line is still written.
- **Target timing.** The target is announced only while the bot plays. The
  checkpoint waits for a wave end where the bot is acting. It never runs at
  the final wave of a normal run.
- **`run_id` collisions.** Two runs started within the same second would
  share a `run_id`, and the second file would overwrite the first.
- **The mod never cleans `requests\`.** Delete old request files by hand when
  they pile up.
- **Co-op is out of scope.** A co-op bot partner (F1) acts only while the
  global bot is on and acting.
- **Steam ID in this document.** The save path names the Steam account id.
  Keep that in mind before publishing the repository.

### 8. Reset the bot profile

Back up first, every time.

1. Quit Brotato.
2. Back up the whole save folder. `backups\` is gitignored:

   ```powershell
   $stamp = Get-Date -Format 'yyyy-MM-dd-HHmmss'
   Copy-Item -Recurse "$env:APPDATA\Brotato\<steam64 id>" `
       "C:\Users\eliza\Desktop\ClaudeFiles\brotato-bot\backups\$stamp-pre-reset\<steam64 id>"
   ```

3. **Preferred: the in-game reset.** Use this because Steam Cloud is on and
   file deletes may be undone.
   1. Launch the game and open the profile menu.
   2. Select "Profile 2" (the bot profile, see 3.1).
   3. Press "Reset". The game warns "Resetting this profile will erase all
      your progress for this profile." Press Confirm.
   4. Which profile "Reset" acts on, the highlighted one or the loaded one,
      is not settled by the code (verify). Check the profile stats on screen
      before you confirm.
4. **Fallback: delete the files.** Do this with the game closed. The game's
   save loader (`ProgressDataLoaderV3`) names the files per profile id, so
   for id 1 they are:
   - `save_v3_1.json` and `run_v3_1.json`
   - their backups, `save_v3_1_01.json.bak` to `save_v3_1_05.json.bak` and
     `run_v3_1_01.json.bak` to `run_v3_1_05.json.bak` (profile 0's backups
     follow this `_<id>_0N.json.bak` pattern)
   - any leftover `save_v3_1.json.tmp` or `run_v3_1.json.tmp`

   Never touch the `_0` files (your profile), `settings.json` or
   `steam_autocloud.vdf`.

   Steam Cloud caveat: on 2026-10-21, Steam's `remotecache.vdf` tracked only
   `save_v3_0.json`, `run_v3_0.json` and `settings.json`. Profile 1 did not
   exist yet. Once it does, its files may be tracked too (verify with
   `Select-String -SimpleMatch 'v3_1'` on `remotecache.vdf`). If they are,
   Steam may restore deleted files at the next launch. Use the in-game reset
   instead.
5. The bot's own files under `%APPDATA%\Brotato\brotato-bot\` are not part
   of the profile. Keep or archive `runs\` and `state\` as you like. To
   start clean, delete `requests\`, `responses\` and `sidecar.alive`.

## Harness

Filled in by the harness plan.
