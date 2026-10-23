# Brotato bot runbook

## Mod

This section covers the in-game mod `Ellie-BrotatoBot` for Brotato 1.1.15.4
with Godot Mod Loader 6.0.0. It was written against branch `sdd/mod` at
`ec55a43`. Every path, key and file name below comes from the code at that
commit. Anything the code alone does not settle is marked "(verify)".

Paths used throughout:

| Name | Path |
|---|---|
| Repository (`<repo>` below) | `<workspace>\brotato-bot` |
| Game folder | `D:\SteamLibrary\steamapps\common\Brotato` |
| Installed mod | `D:\SteamLibrary\steamapps\workshop\content\1942280\3825008026\BrotatoBot.zip` (the owner's hidden Workshop item, uploaded 2026-10-22) |
| Bot root (`user://brotato-bot`) | `%APPDATA%\Brotato\brotato-bot` |
| Save folder | `%APPDATA%\Brotato\<steam64 id>` (the one 17-digit folder there) |
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
   "Profile 1", "Profile 2" and "Profile 3", so the bot's id 1 is the button
   labelled **"Profile 2"** (`menu_profile.gd:195-197` maps ProfileButton2 to
   `active_profile_button(1)`). Step 3.1 still has you confirm it in game.
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
   pwsh -File <repo>\scripts\test_mod.ps1
   ```

   - Expect a final line `67 passed, 0 failed` and exit code 0. The count
     was measured at `ec55a43`.
   - `ERROR: Error parsing JSON` and `WARNING: PlanFile: ...` lines are
     expected. They come from the invalid-input tests.
   - If it says `Godot not found`, run
     `<repo>\scripts\get_godot.ps1`
     once, then run the tests again.
3. Once only: upload the mod as a hidden Workshop item and subscribe to
   it. The game loads zips only from Workshop item folders whose id is in
   the account's subscription list (Brotato's fork of the loader,
   `addons/mod_loader/internal/third_party/steam.gd`, filters on
   `Platform.get_subscribed_mods()`, i.e. `Steam.getSubscribedItems()`).
   It never reads `<game>\mods` (`No zipped mods found` with a zip there,
   seen 2026-10-22 21:44), cannot open an unpacked folder (`Can't open
   unpacked mods folder res://mods-unpacked/`, seen 2026-10-22 20:30), and
   lists but never reads an unsubscribed item folder (`Checking workshop
   item path` then `No zipped mods found`, seen 2026-10-22 21:47). The
   release build has no CLI switch for any of this. An unpacked folder
   loads only under a Godot editor binary, which is how the 2026-10-21
   probe was written.
   1. Build the zip: `pwsh -File <repo>\scripts\pack_mod.ps1` prints
      `Packed 49 files and 1 imported assets into <repo>\build\BrotatoBot.zip`.
      The basename `BrotatoBot` becomes the item title; the uploader sets
      the title from the zip name on every upload. The script needs
      `tools\godot` (`get_godot.ps1`): it imports the mod's textures with
      the Godot 3.6 editor, headless, in `build\import-stage`, because the
      release game cannot import a PNG at runtime. The 2026-10-22 22:13
      launch without that step logged `Parse Error: [ext_resource]
      referenced nonexistent resource at: .../ui/defect.png` and the player
      extension installed as `Null`.
   2. Start the uploader by hand (Brotato has no Steam launch option for
      it) with Steam running, from PowerShell:

      ```powershell
      $env:SteamAppId = '1942280'; $env:SteamGameId = '1942280'
      Start-Process 'D:\SteamLibrary\steamapps\common\Brotato\GodotWorkshopUtility.exe' -WorkingDirectory 'D:\SteamLibrary\steamapps\common\Brotato'
      ```

      Its console starts with `Steam initialization OK!` and lists the tags.
      In the window: "Select mod file" = the zip from step 3.1; leave
      "Select preview image" empty (optional); leave the workshop ID field
      empty the first time; pick the tag `Utilities`; press Upload. The
      console prints `Workshop item created successfully. Please take note
      of the generated workshop ID.` and then `Item successfully uploaded.`
      The ID also appears in the workshop ID field. Write it down.
   3. The utility opens the Workshop legal agreement in the Steam overlay.
      Accept it (one-time; required before Steam serves the item). Then
      open the item page,
      `https://steamcommunity.com/sharedfiles/filedetails/?id=<item id>`,
      and under the owner controls on the right set Visibility to Hidden
      if it is not already. Hidden means visible to the owner alone.
   4. On the same page press Subscribe. Steam downloads the zip into
      `D:\SteamLibrary\steamapps\workshop\content\1942280\<item id>\`.
   5. Put the id into `scripts\sync_mod.ps1` as the `-ItemId` default and
      into the path table above. Done 2026-10-22: item `3825008026`,
      title BrotatoBot, Hidden.
   Later uploads (only needed if the local copy in step 4 is not enough,
   e.g. to reinstall from Steam): repeat 3.1 and 3.2 with the ID in the
   workshop ID field.
4. Install the current build into the game:

   ```powershell
   pwsh -File <repo>\scripts\sync_mod.ps1
   ```

   - The script refuses to run while Brotato is open. It first removes
     stale installs from the earlier methods: `Pasha-AutoBattler` and
     `Ellie-BrotatoBot` under `<game>\mods-unpacked`,
     `<game>\mods\Ellie-BrotatoBot.zip` and the fake item folder
     `9999999999`, printing `Removed <path>` for each. With a missing item
     folder it stops with `Workshop item folder not found` and the
     subscribe link.
   - It then runs `pack_mod.ps1` and copies the build over the item
     folder's zip, printing
     `Packed 49 files and 1 imported assets into <repo>\build\BrotatoBot.zip` and
     `Installed D:\SteamLibrary\steamapps\workshop\content\1942280\3825008026\BrotatoBot.zip`.
     Any other zip in that folder is renamed to `*.zip.disabled`. Steam
     rewrites the folder only when the item itself is updated, which is the
     owner's own upload, so the local copy survives game launches. The zip
     holds `.import/defect.png-<md5 of its res path>.stex` and
     `mods-unpacked/Ellie-BrotatoBot/<files>`, the layout the loader
     expects. The count is the number of files in `mod\Ellie-BrotatoBot` at
     `568aaee`, including the `.import` files. `pack_mod.ps1` fails with
     `name a .stex the Godot import did not produce` if a `.import` file in
     the mod carries a stale hash; fix it by copying the regenerated
     `.import` file from `build\import-stage` back into `mod\`.
   - Use `-GameDir <path>` only if the game moves; `-ItemId` / `-WorkshopDir`
     only if the item or library changes.
5. Launch Brotato through Steam. The title screen shows the Mod Loader's
   one-time "mods are loaded" warning (unverified; it may not appear).
   Dismiss it if it does.
6. Check that the mod loaded:
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
   - If `modloader.log` says `Mods are currently disabled` and nothing
     else, the game's own crash reporter (`singletons/crash_reporter.gd`,
     which runs before the loader) found `ERROR` lines naming a mod in the
     previous launch's engine log and switched mods off for this one start.
     Fix whatever that earlier log complained about, then launch again: it
     only reads the latest log, so a clean launch re-enables mods. Seen
     2026-10-22 22:20 after the 22:13 launch logged the `defect.png` parse
     errors.
   - The title screen has a "Mods" button. It should list BrotatoBot 0.1.0
     by Ellie, from `manifest.json` (verify what that page shows). The
     manifest's two Mod Loader options, "Enable Bot" and "Autoshop", are
     **not** the switch. Only Shift+Space turns the bot on.

### 3. One-time setup

#### 3.1 Create the bot profile

1. On the title screen, open the profile menu (the main-menu button reads
   "Profile N").
2. Select the second button ("Profile 2"), then "Load Profile". This is
   profile id 1 (`_on_Select_pressed` loads the highlighted profile's
   `view_id`); step 4 confirms it in game.
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

1. Main menu → Options. Open the **Sound** tab (`MENU_SOUND`,
   `menu_options.tscn:304`) and find the **"On losing focus"** dropdown
   (`MENU_ON_LOST_FOCUS`, `on_lost_focus_button.gd`). Its options are
   "Do nothing", "Pause" and "Pause disable input". The old
   `PauseOnFocusLostButton` checkbox still exists in the scene but is
   `visible = false` (`menu_options.tscn:560-568`), so you cannot reach it.
2. Set "On losing focus" to **"Do nothing"**. That sets
   `pause_on_focus_lost` false; "Pause" or "Pause disable input" sets it true
   (`menu_options.gd:614-619`). The default is "Pause"
   (`progress_data.gd:342-343`). The setting is global
   (`settings.pause_on_focus_lost` in
   `%APPDATA%\Brotato\<steam64 id>\settings.json`), so it also affects
   your own play.
3. If it is on (the dropdown shows "Pause" or "Pause disable input"), the
   warning fires once per run, on any profile
   (`main.gd:84-93`, gated by `focus_warned_run_id`), not on every wave:
   - Overlay line 1 reads `Warning: pause_on_focus_lost is true`.
   - Overlay line 4 reads `focus: pause_on_focus_lost`.
   - The run file gets one `warning` line per run with
     `"reason":"pause_on_focus_lost is true"`.
   - Overlay line 4 persists for as long as the setting is on.
4. Leave "Mouse Only" (Options, Gameplay page) **off** for bot runs. See
   Known limitations.

#### 3.3 Optional: show the overlay while the bot is idle

The overlay always shows while the bot is not idle, and whenever a status
line is set (for example `Bot refused: ...` or `Exported: ...`). To also see
it while idle (`BOT idle` plus the plan line), turn on AI visuals. This also draws the in-world AI highlight canvas
(`ai_canvas.gd:7`), not only the overlay:

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
  A wrong-typed value falls back to its default, with a warning in
  `godot.log`, only for the five numeric keys (`INT_KEYS` / `FLOAT_KEYS` in
  `core/bot_config.gd`). `target_challenge` and `export_hotkey` are coerced
  with `str()` instead.
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
  another character or exists but does not load. Only the keys in the table
  below, with their types, are accepted: the sidecar's schema rejects any
  other key or type, and the mod drops one that still arrives
  (`PlanFile.KEY_TYPES`).

Common `plan` keys. This table is the full set. The header comment in
`shopping/build_plans.gd` is partial: it does not list `ask_on`, `gold_floor`,
`prefer_weapons`, `ban_items` or the last row's keys.

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
| `phase_boost` | `{"until_wave": N, "stats": {stat key → multiplier}}`; before wave N the named stats' weights are multiplied (`build_plans.gd:40-42`); `{}` disables |
| `weapon_set` (string), `deprioritize_weapons` (list of ids), `unique_weapons`, `stack_combine`, `hitrate_pref`, `spend_surplus` (booleans) | per-character shop tweaks read by `shop_advisor.gd` and `base_shop.gd` |

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
     `Bot refused: wrong profile (<id>)`,
     `Bot refused: no plan at user://brotato-bot/plan.json` or
     `Bot refused: invalid plan at user://brotato-bot/plan.json` (the file
     is not valid JSON, or lacks `plan_id`, `character_id` or `plan`). A
     `warning` line goes into the run file and the bot stays off.
   - If it accepts, the AI marker appears on the potato, it starts steering,
     and from then on it shops and picks level-ups.
5. Read the overlay. It sits top-left at (8, 8) and has four lines:

   | Line | Shows |
   |---|---|
   | 1 | The status. It can be `BOT acting`, `BOT idle`, `DECIDING: <kind> <N>s` (counts down), `HALTED: <reason>`, `RUN COMPLETE: win` or `RUN COMPLETE: death`, `TARGET: <id> DONE`, `Bot refused: <reason>`, `Exported: <path>`, `Warning: pause_on_focus_lost is true` or `Export failed (see log)`. |
   | 2 | `plan <plan_id> \| target <id or none>`. The plan id is `builtin` when the plan file does not apply, and `-` when no character is known. |
   | 3 | The last decision: `<kind>: <action> #<option_index> via <source>`. Examples: `shop: buy #2 via haiku`, `shop: - via timeout`. The line is blank until the first decision. |
   | 4 | Warnings, joined by ` \| `: `focus: pause_on_focus_lost`, `no plan.json`, `sidecar: off` (two decisions in a row timed out, so the bot stops asking for the rest of the run). Blank when there are none. |

6. Where files land. All are under `%APPDATA%\Brotato\brotato-bot\`:

   | File | Written when |
   |---|---|
   | `runs\<run_id>.jsonl` | Opened when wave 1 starts, on any profile. `run_id` is `YYYYMMDD-HHMMSS-<character without "character_">-d<danger>`, e.g. `20261022-201500-well_rounded-d0`. A resumed or retried wave with no open run starts a new file whose header has `start_wave > 1`. Returning to the main menu closes the open file with an `end` line `"outcome":"abandoned"`, and a later wave continues an open file only when its header names the same profile and character. |
   | `state\<id>.json` | Each decision and each F9 press. `<id>` is `<run_id>-<NNN>`, or `norun-<YYYYMMDD-HHMMSS>-<NNN>` with no open run. `NNN` counts per run from `001`. |
   | `requests\<id>.json` | Each decision request, with the same `<id>` as its state file. The mod never deletes these. |
   | `responses\<run_id>-<NNN>.json` | Written by the sidecar. The mod reads each one once and deletes it. Responses for any other id are deleted unread. |
   | `options.cfg`, `coop_state.cfg`, `probe.txt` | The mod's own settings, co-op state and load probe. |

   Event kinds in the run file (`{"t": ms since start, "kind": ..., ...}`):

   | Kind | Data | When |
   |---|---|---|
   | `header` | `character_id`, `danger`, `plan_id`, `profile_id`, `game_version`, `mod_version`, `start_wave`, `run_id` | first line |
   | `bot_state` | `state` (`acting`, `idle`, `halted`, `complete`), `reason` (`enabled`, `toggle_off`, `main_menu`, `run_start`, or the halt reason) | Shift+Space on or off, a halt, the main menu, and right after the header (the bot's state when the file opened) |
   | `snapshot` | position, heading, threats, ... | about 1 Hz, only while the bot is enabled |
   | `damage`, `dash`, `bullet_hell` | — | only while the bot is enabled |
   | `death` | `wave`, `position`, `killer`, `last_threats`, `build`, `dmg_w` | player 0 dies |
   | `wave_end` | `wave`, `hp`, `gold`, `damage_taken`, `kills` | every wave end |
   | `warning` | `reason`, or `message` | `reason`: refused enable; `pause_on_focus_lost is true`. `message`: `sidecar timeouts; asking disabled for this run` |
   | `halt` | `reason` (`human input`, `wrong profile`) | the bot halts |
   | `export` | `export_kind`, `path`, `seq` | every state export (F9 or a decision) |
   | `decision` | `request_kind`, `id`, `wave`, `source`, `response` | every decision request. `source` is `haiku` (valid answer), `invalid`, `timeout`, `interrupted` or `busy`. |
   | `decision_applied` | `id`, `action`, `option_index`, `applied` | shop only, after a decision. `applied` is `buy`, `lock`, `reroll`, `skip`, `revise_plan` or `rule`. |
   | `shop` | `wave`, `action` (`buy`, `reroll`, `lock`, `ban`, `go`), `item_id`, `price`, `score`, `source` (`rule`, `haiku`), `gold_after` | every bot shop action. `item_id` is null for `reroll` and `go`; `price` is the reroll's cost (0 when free) and null for `go`; `score` is null for `reroll`, `ban` and `go` |
   | `levelup` | `wave`, `id` (the decision's id, `""` when not asked), `picked`, `alternatives`, `source` (`haiku`, `rule`, `timeout`) | every bot level-up pick that landed |
   | `challenge` | `id`, `is_target` | a challenge completes for the first time on this profile |
   | `checkpoint` | `id`, `action`, `applied`, `reason` | the target checkpoint |
   | `complete` | `outcome` (`win`, `death`), `wave`, `extra` (`killer` on death) | the run ends while the bot plays |
   | `end` | `outcome` (`won`, `death`, `abandoned`, `quit`), `wave`, `hp`, `gold` | always the last line (`abandoned`: the main menu, or a new run started over an open file) |

7. **`DECIDING: <kind>`** (`shop`, `levelup`, `pivot` or `checkpoint`).
   - The bot has written a request and **paused the game**. It polls
     `responses\` every 0.25 s. It waits up to `request_timeout_ms` (45 s),
     or `checkpoint_timeout_ms` (120 s) for a checkpoint. If no answer comes,
     the rules decide and the game resumes.
   - The bot asks only when `%APPDATA%\Brotato\brotato-bot\sidecar.alive`
     was modified within the last **10 s**. Otherwise the rules decide at
     once: no request, no pause and no `decision` line.
   - A shop asks at most once per visit, before its first buy.
   - After two decisions in a row time out, the bot stops asking for the rest
     of the run: a `warning` line (`message`), line 4 `sidecar: off`, and a
     checkpoint then logs `"reason":"asking_disabled"`. Any answer (valid or
     invalid) resets the count; `interrupted` and `busy` neither count nor
     reset. A new run asks again.
   - **ESC during a decision** means "stop waiting, the rules decide": the
     decision ends at once with `"source":"interrupted"`. In the shop, ESC
     also opens the pause menu; the bot leaves the game paused under it and
     does no more shopping this visit (you finish the shop and press GO). At
     a level-up or checkpoint no menu opens: the game resumes and the rules
     decide.
   - **A move key during a decision** ends it the same way, then halts the
     bot (`HALTED: human input`) once the decision is over.
8. **Stopping the bot:**
   - **Shift+Space** turns it off cleanly: `BOT idle`, no `halt` line.
   - **Any move key, arrow, IJKL, gamepad button or stick** halts it:
     `HALTED: human input`, a `halt` line, and the key moves the potato.
     A halt stops a shop visit or level-up at once: no further buy, reroll,
     lock, pick or GO.
   - **ESC in the shop** (the pause menu) ends the bot's shopping for this
     visit, whether or not a decision was pending: nothing is bought behind
     the menu, and after Resume the shop waits for you to finish it and press
     GO. The bot stays on and plays the next wave.
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

#### 4.10 Decision protocol (the sidecar contract)

All files are under `%APPDATA%\Brotato\brotato-bot\` (`user://brotato-bot`).

- **Heartbeat.** The mod asks only if `sidecar.alive` was modified within the
  last 10 s. It checks just before asking, never while waiting, and the
  modification time has 1 s resolution. The sidecar should touch it every
  few seconds while it runs.
- **Request.** `requests\<id>.json`, written as `<id>.json.tmp` and renamed.
  The mod never deletes requests.

  | Field | Meaning |
  |---|---|
  | `id` | the state file's base name: `<run_id>-<NNN>`, or `norun-<YYYYMMDD-HHMMSS>-<NNN>` with no open run |
  | `kind` | `shop`, `levelup`, `pivot` (an offered id is in the plan's `ask_on`) or `checkpoint` |
  | `screen` | `shop`, `levelup` or `checkpoint`: which screen is asking. A `pivot` comes from the shop or a level-up; answer by `screen` |
  | `run_id`, `seq` | the run (`norun` when none) and the export counter |
  | `state_path` | the matching `state\<id>.json` (written before the request) |
  | `options` | the choices, see below (empty for `checkpoint`) |
  | `deadline_ms` | epoch milliseconds after which the mod stops waiting |

- **Options.** `options[i].index == i`.
  - `screen: "shop"`: `{index, id, kind ("weapon" or "item"), price, score}`,
    one per *active* shop slot, compacted.
  - `screen: "levelup"`: `{index, id, stat, value, score}` (`stat` and
    `value` are the upgrade's first effect).
- **`option_index` indexes `request.options[]` only.** It is not the state
  file's `shop[].index`, which is the raw slot index with gaps. The two
  differ as soon as a slot is inactive (e.g. after a ban). Always answer from
  the request.
- **Response.** `responses\<id>.json`, written as `<id>.json.tmp` and then
  renamed (the mod reads only `*.json`). The mod reads it once and deletes
  it; responses for any other id are deleted unread.

  | Field | Rule |
  |---|---|
  | `action` | `buy`, `lock`, `reroll`, `skip` (shop); `pick` (level-up); `revise_plan` (shop and `checkpoint` only); `skip` (`checkpoint`) |
  | `option_index` | int >= 0, required for `buy`, `lock` and `pick` |
  | `confidence` | number in 0..1, required |
  | `rationale` | string, optional |
  | `plan_patch` | object of section 3.5 plan keys, required for `revise_plan` (merged into `plan.json`; unknown or wrong-typed keys are dropped) |
  | `tags` | optional, ignored |

  A response that fails these rules counts as `invalid` and the rules decide.
  An action that does not fit the screen (e.g. `pick` in the shop) is applied
  as `rule`. The sidecar rejects such an answer, and an `option_index` that
  is not in `options[].index`, before writing it, so its retry and repair
  steps run instead.
- **Sources** in the `decision` line: `haiku` (valid answer), `invalid`,
  `timeout` (no answer by the deadline; also a failed write or a halt while
  waiting), `interrupted` (ESC, a move key or the pause menu during the wait)
  and `busy` (a second decision while one is pending: no request).

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

1. Do section 2 steps 4-6. Expect: a fresh `probe.txt`, no `ERROR` line in
   `modloader.log` that names the mod, and no `SCRIPT ERROR` in `godot.log`.
   - In `modloader.log`, also look for the positive signals: `Ellie-BrotatoBot`
     is listed among the loaded mods, and the line
     `DONE: Installed all script extensions` appears.
   - Confirm Ellie-BrotatoBot is the only mod listed (the loader cache files
     were regenerated).
   - Also note whether `godot.log` complains about `defect.png` or a missing
     `.stex`. That would be the AI marker icon, inherited from BOTato.
2. Quit the game. Wait one minute. Then run:

   ```powershell
   Get-ChildItem 'C:\Program Files (x86)\Steam\userdata\*\1942280\remotecache.vdf' |
       Select-String -SimpleMatch 'brotato-bot'
   ```

   Expect no output, which means Steam Cloud does not sync the bot root.
   Record the result under "Result" in
   `<repo>\learnings\steam-cloud.md`.
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
4. While the bot acts, press Shift+Space twice, waiting about half a second
   between presses (presses under 350 ms apart collapse into one toggle,
   `autobattler_options.gd:88`). The first press turns it off
   with no `HALTED`: the status clears, and the block hides unless AI
   visuals are on. The next shop is not auto-bought. The second press turns it on again.
5. Turn the bot on, then quit and restart the game. Expect the bot to start
   off (no marker), even though `options.cfg` says `ENABLE_AUTOBATTLER=true`.
6. With Options > Sound > "On losing focus" set to **"Pause"** (the
   default), start a bot-profile run. Expect
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
   `Exported: %USERPROFILE%/AppData/Roaming/Brotato/brotato-bot/state/<run_id>-001.json`
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
4. After `RUN COMPLETE`, advance into any post-run shop or level-up. Expect
   no purchase and no pick (T7 Step 4: the post-run shop does not auto-buy).
   `end_run` has already closed the JSONL, so this is observation-only, with
   no file evidence. Note which outcome and wave occurred.

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
   while `DECIDING` shows. Expect the pause menu to open over the shop
   within about 0.25 s, and the countdown to stop. The game stays paused
   under the menu. Line 3 reads `shop: - via interrupted`. Choose Resume.
   Expect the bot to buy nothing more and not to press GO: finish the shop
   yourself. Evidence: a `decision` line with `"source":"interrupted"`, no
   `decision_applied` and no `shop` line after it for this visit, and a
   `BOTLOG SHOP ... abandoned` line in `godot.log`. The next wave plays
   with the bot on.
5. **Alt-tab** away during a decision and back. Expect: nothing changes and
   no pause menu appears. Drop a response afterwards. Expect one resume, one
   buy, and exactly one `decision` line for that id.
6. Optional, **level-up.** With the loop running and a close level-up,
   expect `DECIDING: levelup`. A response
   `{"action":"pick","option_index":1,"confidence":0.8}` picks the second
   option. Evidence: `decision` (`"source":"haiku"`) and `levelup` with
   `"source":"haiku"` and the same `id`. With no response, after the
   timeout `levelup` says `"source":"timeout"`.
7. **ESC during DECIDING: levelup.** With the loop running and a close
   level-up, press ESC once while `DECIDING: levelup` shows. Expect no pause
   menu: the game resumes within about 0.25 s and the rules pick. Evidence:
   `decision` `"source":"interrupted"`, then `levelup` `"source":"rule"`.
8. **ESC during an auto-shop, no decision pending.** Stop the keep-alive
   loop (so no shop asks). In a shop where the bot has gold to spend, press
   ESC while it is still buying or rerolling. Expect the pause menu, and no
   buys, rerolls or locks while it is open. Choose Resume. Expect the bot
   to do nothing more in this shop: you finish it and press GO. Evidence: no
   `shop` line after the pause, and `BOTLOG SHOP ... abandoned` in
   `godot.log`. The next wave plays with the bot on.
9. **A move key mid-shop.** In a shop where the bot is still buying, press
   W. Expect `HALTED: human input` and zero further `shop` lines; the shop is
   yours.
10. **Two-timeout breaker.** Keep the loop running but write no responses.
    Let two decisions in a row time out (shop or level-up). Expect, after
    the second: a `warning` line
    `{"message":"sidecar timeouts; asking disabled for this run"}`, line 4
    `sidecar: off`, and no further `DECIDING` pause for the rest of this run
    even with the loop running. A new run asks again.

Stop the keep-alive loop and remove `ask_on` entries when done.

#### 6.7 Target checkpoint (Task 9)

1. Pick a target the bot profile has **not** completed yet:
   `chal_gatherer_1` (collect 300 materials, counted across the profile's
   lifetime). If the bot profile already has it, the fallbacks are much
   bigger: `chal_gatherer_2` is 2000 lifetime materials and `chal_survivor_1`
   is 300 kills (`challenge_service.gd:633-646`).
2. In `config.json` set `"target_challenge": "chal_gatherer_1"`. Optionally
   also set `"checkpoint_timeout_ms": 20000`. Leave `plan.json`'s
   `target_challenge` empty, or set it to the same id. Restart the game.
   Expect line 2 `plan <id> | target chal_gatherer_1` once the run starts.
3. Start the keep-alive loop from 6.6. Without it, the checkpoint does not
   pause: it logs `checkpoint` with `"applied":"skip"` and
   `"reason":"no_sidecar"`. The loop also makes close shops ask and wait.
4. Bot run on Danger 0. For `chal_gatherer_1` (300 materials) the target should fire within about
   4-7 waves (an unmeasured estimate; the fallbacks take far longer). Expect line 1
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
   `DECIDING: checkpoint` shows. In Main no pause menu can open during the
   decision; expect the countdown to stop within about 0.25 s, the wave end
   to carry on as usual, the overlay to return to the bot's status, a
   `decision` line with `"source":"interrupted"` and a `checkpoint` line
   with `"applied":"skip"` and `"reason":"interrupted"`. After that the bot
   is still on (verify that the next wave plays normally). Press W instead
   on a later attempt: the same lines, then `HALTED: human input`.

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
- **Taking over during a decision.** While the game is paused for a
  decision, a move key ends the wait and halts the bot once the decision is
  over; the key itself does not move the potato (the game is paused). Press
  it again after the game resumes. Navigating the shop's pause menu with
  WASD or the arrows during a decision also halts the bot.
- **The pause menu ends a shop visit.** Opening the pause menu in the shop
  stops the bot's shopping for that visit even after Resume; you finish the
  shop. A pause at a level-up only freezes the bot's picks until Resume.
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
  after every sync (section 2, step 6).
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
   New-Item -ItemType Directory -Force "<repo>\backups\$stamp-pre-reset" | Out-Null
   Copy-Item -Recurse "$env:APPDATA\Brotato\<steam64 id>" `
       "<repo>\backups\$stamp-pre-reset\<steam64 id>"
   ```

3. **Preferred: the in-game reset.** Use this because Steam Cloud is on and
   file deletes may be undone.
   1. Launch the game and open the profile menu.
   2. Select "Profile 2" (the bot profile, id 1, see 3.1).
   3. Press "Reset". The game warns "Resetting this profile will erase all
      your progress for this profile." Press Confirm.
   4. "Reset" acts on the highlighted profile (`menu_profile.gd:268-269`
      calls `reset_save_profile(view_id)`). As a second check, look at the
      profile stats on screen before you confirm.
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

### 1. One-time setup

1. Open PowerShell in this checkout's root and run `uv sync`.
   Package: `brotato_bot/`; Python >= 3.12; only runtime dependency: `pydantic>=2`.
   The dev group adds pytest and ruff.
2. Run the commands below from that root with `uv run python -m brotato_bot`.
   The harness never launches Brotato or injects input. You launch the game,
   start each run and enable the mod as described in Mod section 4.
3. `brotato_bot/paths.py` resolves these defaults; set overrides before commands.

| Environment override | Default / meaning |
|---|---|
| `BROTATO_BOT_GAME_DIR` | `D:\SteamLibrary\steamapps\common\Brotato` |
| `BROTATO_BOT_PCK`, `BROTATO_BOT_DLC_PCK` | Game folder's `Brotato.pck`, `BrotatoAbyssalTerrors.pck` |
| `BROTATO_BOT_SAVE_DIR` | Explicit save folder; takes priority over Steam ID discovery. |
| `BROTATO_BOT_STEAM_ID` | Select `%APPDATA%\Brotato\<steam64 id>` by name. |
| `BROTATO_BOT_SETTINGS_JSON` | Save folder's `settings.json` |
| `BROTATO_BOT_MOD_USER_DIR` | `%APPDATA%\Brotato\brotato-bot` (the bot root) |
| `BROTATO_BOT_PLAN_JSON`, `BROTATO_BOT_CONFIG_JSON` | Bot root's `plan.json`, `config.json` |
| `BROTATO_BOT_RUNS_IN`, `BROTATO_BOT_STATE_DIR` | Bot root's `runs/`, `state/` |
| `BROTATO_BOT_REQUESTS_DIR`, `BROTATO_BOT_RESPONSES_DIR` | Bot root's `requests/`, `responses/` |
| `BROTATO_BOT_PROJECT_ROOT` | Directory containing `brotato_bot/` |
| `BROTATO_BOT_DATA_DIR`, `BROTATO_BOT_KNOWLEDGE_DIR` | Project root's `data/`, `knowledge/` |
| `BROTATO_BOT_KNOWLEDGE_CACHE` | Knowledge directory's `cache/` |
| `BROTATO_BOT_RUNS_OUT`, `BROTATO_BOT_DECISIONS_DIR` | Project root's `runs/`, `decisions/` |
| `BROTATO_BOT_PROPOSALS_DIR`, `BROTATO_BOT_ADVICE_DIR` | Project root's `proposals/`, `advice/` |

Without an override, it selects the single 17-digit folder under `%APPDATA%\Brotato`.
Zero or several matching folders raise
`RuntimeError: cannot find the Brotato save folder`, with count and location.
Set `BROTATO_BOT_SAVE_DIR` to the folder or `BROTATO_BOT_STEAM_ID` to its name.
Discovery waits until a command needs the save; path loading requires `APPDATA`.

### 2. After each game update

1. Rebuild the local dataset:

   ```powershell
   uv run python -m brotato_bot dataset build
   ```

   Reads the base PCK, then the Abyssal Terrors DLC PCK into `data/extracted/`
   and writes `data/brotato.json`. A missing DLC is reported and skipped.
   `data/` is gitignored; commit none of the extracted or derived game data.
   Optional flags are `--pck`, `--dlc-pck` (`none` skips DLC), repeatable
   `--translations` (later CSVs win), and `--out`.
2. Read profile id 1's save without changing it:

   ```powershell
   uv run python -m brotato_bot unlock-state --profile 1
   ```

   Reads `save_v3_1.json` and writes `data/unlock_state.json`, including the
   `challenges` key used for the prompt's objective text. Profile ids are
   0-based: id 1 is the menu's "Profile 2" (Mod section 3.1).
   `--profile` defaults to 1; `--save`, `--translations`, `--out` override the
   save, translation CSV and output JSON. Refresh after unlocks too.
   `proposal validate` and `prepare --from-proposal` refuse a file built for
   another profile: `<path> was built for profile <n>; run unlock-state --profile 1`.

### 3. Knowledge

1. Refresh wiki pages listed in `knowledge/sources.json`:

   ```powershell
   uv run python -m brotato_bot knowledge fetch
   ```

2. Use `--characters` to add dataset character pages before fetching, or
   `--only SLUG` to refresh one source. Results land in `knowledge/cache/`.
   Failed fetches keep the previous cached text. Bundled guide files there
   are also loaded into prompts; fetch refreshes only listed sources.
3. The wiki pages (`wiki-*.md`, `character-*.md`) are fetched, not shipped:
   the wiki's licence is undeclared, so they are gitignored and a clean
   checkout has only `knowledge/sources.json` and the MIT `botato-*.md`
   guides until the first fetch. Prompts work without them.

This is the only wiki/guide network operation; dataset, saves, prepare and
collect are local. Decisions also need the authenticated `claude` CLI's model service.

### 4. Each session

1. Install a plan JSON (`FILE` is your file) and select a challenge:

   ```powershell
   uv run python -m brotato_bot prepare --plan FILE --target chal_gatherer_1
   ```

   `--plan FILE` requires non-empty `plan_id` and `character_id` strings and
   a `plan` object. Prepare copies it to the mod's `plan.json`, and merges
   `--target ID` into `config.json`'s `target_challenge`, preserving other keys.
   Read its profile/focus warnings. Restart Brotato after a config target change.
2. For no target, omit `--target`; prepare clears the config's stale target
   to `""`. A non-empty target in the input plan still wins and triggers a
   warning if it differs. Use `"target_challenge": ""` or omit that key in
   the plan too. Both target keys absent or empty mean "no target".
   `prepare --from-proposal FILE` validates the proposal (with `runs/index.json` when
   present) and writes its `## Next run` target into both `config.json` and the plan.
3. In its own terminal at the project root, start:

   ```powershell
   uv run python -m brotato_bot sidecar
   ```

   It prints the requests directory and whether auto-next is on. For each
   handled decision it prints `[<id>] <kind> -> <action> via <source> in <ms> ms`.
   It polls every 0.25 s and touches the bot root's `sidecar.alive` between
   requests. The mod asks only while that heartbeat is at most 10 s old (whole
   seconds); see
   Mod section 4.10 Decision protocol for the request/response contract.
4. Launch Brotato yourself, select profile id 1, start the run and press
   Shift+Space (Mod section 4). The request's absolute `deadline_ms` gives
   the sidecar its remaining total budget: normally 45000 ms, or 120000 ms
   for checkpoints, less time already spent. Each CLI call gets at most
   40% of the configured timeout (18 s / 48 s by default); later ladder
   steps are skipped if a full call's budget no longer remains.
   The ladder is `haiku`, `haiku-retry`, `repair`, then `fallback`.
   On `fallback` no response is written: the mod times out and its rules
   decide. Expired requests are deleted without a call.
5. Press Ctrl+C in the sidecar terminal to stop it. Shutdown removes the
   heartbeat, so the mod stops asking. An existing pending wait follows
   the protocol in Mod section 4.10.

### 5. Optional auto-next

1. Start `uv run python -m brotato_bot sidecar --auto-next` instead.
2. It tails the newest run recording by modification time, ignoring lines
   already present at startup. On a new `end` line whose outcome is `won` or
   `death` (not `quit` or `abandoned`) it collects in-process,
   then runs `claude -p --model <next_model> /brotato-next` from the project
   root with a 600 s timeout, once per run file; no CLI call if collect fails.
   A run whose header `profile_id` is not the bot profile (`config.json`
   `bot_profile_id`, default 1) is skipped: no collect, no call.
3. While that call runs, the loop answers no requests and does not refresh
   the heartbeat. Once it is more than 10 s old the mod's rules decide until
   the call returns. The flag is wired; the `/brotato-next` skill exists at
   `.claude/skills/brotato-next/SKILL.md`.

### 6. After a run

1. Collect the newest recording, or select one with `collect RUN_ID`:

   ```powershell
   uv run python -m brotato_bot collect --latest
   ```

   `--latest` is the default. Input is the bot root's `runs/<run_id>.jsonl`.
2. Re-collecting a finished run is safe: report and index row are replaced;
   joined experience is appended only for unseen `(run_id, id)` pairs.
3. Every run gets a report and an index row (with its `profile_id`), but
   experience is appended only for a finished run (outcome `won` or `death`, not
   `incomplete`) on the bot profile (`config.json` `bot_profile_id`, default 1),
   so the owner's own runs never reach it and a run in progress is not frozen.
4. `stagnation [--target ID]` prints `<state> (<target>): <reason> [runs: ...]` from
   bot-profile index rows; a row with `target_fired` true counts like a win.
   `--mark-paused PROPOSAL` adds one `paused:` line per target to `targets.md`;
   when it is already there it prints `already paused: <target>` and writes nothing.

| Project output | Contents |
|---|---|
| `runs/<run_id>.md` | Run report; decisions table has `kind`, `action`, `source`, `confidence`, `rationale`, `outcome`. |
| `runs/<run_id>.jsonl` | Copy of the mod's recording. |
| `runs/index.json` | Run summary index. |
| `runs/<run_id>-checkpoint.md` | Sidecar note written when it handles a checkpoint. |
| `decisions/<run_id>.jsonl` | One sidecar record per handled decision. |
| `decisions/experience.jsonl` | Decisions joined to run outcomes at collect time. |

The sidecar record's fields, in write order, are `id`, `kind`, `ts`, `model`,
`source`, `attempts`, `elapsed_ms`, `decision`, `prompt_sha256`, `run_id`,
`screen`, `character_id`, `wave`, `options`, `response`. `ts` is UTC;
`decision` and `response` are the same object, or null for fallback.
Each attempt has `model`, `source_label`, `elapsed_ms`, `returncode`, `raw`,
`errors`; inspect those when a call fails.

Joined experience adds `action`, `applied`, `chosen`, `confidence`,
`outcome`, `death_wave`, `hp_next_wave` and `kept_to_end` to the
identifying/context fields. `applied` comes from the run file's
`decision_applied`, `levelup` and `checkpoint` lines for the decision id
(null when there is none); when the mod did not apply the answer, `chosen`
and `kept_to_end` are null and the prompt shows the row as not applied. The live loop feeds the latest 20 same-character, same-kind rows
from `decisions/experience.jsonl` to the prompt's "Past decisions" section.

### 7. Smoke without the game

1. Use an F9 state export (Mod section 5 Advisor mode); `STATE_FILE` is its path.
2. Print the prompt without calling the Claude CLI:

   ```powershell
   uv run python -m brotato_bot decide-once STATE_FILE --kind shop --plan FILE --print-prompt
   ```

3. Omit `--print-prompt` to run one real decision ladder and print its
   outcome/attempts JSON. `--kind` is `shop` (default), `levelup` or `checkpoint`;
   `--plan FILE` defaults to the mod's `plan.json`. No past experience is used
   and no mod response is sent.

### 8. Harness config

The harness reads the bot root's `config.json`; missing/unreadable JSON uses
defaults. `decide.settings` keeps non-null keys without type validation.
Restart the sidecar after changes and the game for shared timeouts (Mod section 3.4).

| Key | Default | Use |
|---|---|---|
| `model` | `claude-haiku-5-5` | First decision and retry. |
| `repair_model` | `claude-sonnet-5-5` | Repair an invalid answer. |
| `checkpoint_model` | `claude-sonnet-5-5` | Checkpoint first call and retry. |
| `next_model` | `claude-sonnet-5-5` | Auto-next; default added by the sidecar loop. |
| `request_timeout_ms` | `45000` | Normal decision timeout. |
| `checkpoint_timeout_ms` | `120000` | Checkpoint timeout. |

### 9. Troubleshooting

| Symptom | Check / action |
|---|---|
| Sidecar prints `fallback` every time | Inspect `attempts` in the decision log for CLI startup, authentication, timeout or validation errors; check configured models and local dataset/cache. |
| `RuntimeError: cannot find the Brotato save folder` | Set `BROTATO_BOT_SAVE_DIR` or `BROTATO_BOT_STEAM_ID`; create profile id 1 in game if its save is absent (Mod section 3.1). |
| Mod never asks | Check heartbeat age, profile id (0 is your profile), bot enabled, and asking conditions. Two consecutive timeouts disable asking for that run; see Mod sections 4.10 and 6.6. |
| `error_max_turns` or 4xx in attempts | The ladder stops early on `error_max_turns` and HTTP 400/401/403; inspect the recorded CLI error. The wrapper uses two turns for structured output; other 4xx are not all classified deterministic. |

## Full session

One bot run from proposal to next proposal, then the advisor pass. Each step
points to the section that has the detail; this section only orders them.
Run every command from the project root.

Three windows:

1. **Sidecar terminal** (project root): `uv run python -m brotato_bot sidecar`. Keep it open for the whole run.
2. **Claude Code terminal** (project root): where `/brotato-next`, `/brotato-decide` and `/brotato-advise` are invoked. The `uv run` commands below can run here too.
3. **Game**: you launch it. Profile id 1 for bot runs (the button labelled "Profile 2"; Mod section 1).

Order for one bot run:

1. Claude Code: `/brotato-next` prints the proposal path and an install line. Use `/brotato-next-sonnet` instead when Haiku's proposal keeps failing validation.
2. Project-root terminal: `uv run python -m brotato_bot prepare --from-proposal <path>` (Harness section 4).
3. Sidecar terminal: `uv run python -m brotato_bot sidecar` (Harness section 4, step 3). Start it before the run so the heartbeat is fresh.
4. Game: launch (restart the game if `prepare` printed `config.json changed: restart Brotato`), select profile 1, check that `plan.json` names the character (Mod section 4, step 2). Pick the proposal's character and danger, start the run, then press Shift+Space once wave 1 has started (Mod section 4, step 4).
5. Game: play until the run ends, at wave 20 cleared or death (Mod section 4, step 9).
6. Sidecar terminal: Ctrl+C (Harness section 4, step 5).
7. Project-root terminal: `uv run python -m brotato_bot collect --latest` (Harness section 6).
8. Project-root terminal: `uv run python -m brotato_bot unlock-state --profile 1`.
9. Project-root terminal, optional: `uv run python -m brotato_bot stagnation --target <id>`. `/brotato-next` runs it anyway.
10. Claude Code: `/brotato-next` for the next proposal.

Advisor mode during your own play (Mod section 5):

1. Game, any profile: press F9 (or `export_hotkey`) while you play. It also works from the ESC pause menu.
2. Claude Code: `/brotato-advise`, optionally with the state file path from `%APPDATA%\Brotato\brotato-bot\state\`. The advice note is written under `advice/`.
3. The sidecar does not need to run. F9 never acts on the game.

Where to look when something stalls:

- Mod overlay, top-left (Mod section 4, step 5): line 1 is the status (`HALTED: <reason>`, `Bot refused: <reason>`, `DECIDING: <kind>`); line 4 `sidecar: off` means two decisions timed out in a row.
- Sidecar console, `[<id>] <kind> -> <action> via <source> in <ms> ms`: one line per handled decision. No line at all means the mod never asked; check the heartbeat (Harness section 4, step 3).
- `decisions/<run_id>.jsonl`: one record per decision. `attempts` lists each model call, with its `returncode`, `raw` and `errors`.
- `runs/<run_id>.md`: the run report, with the decisions table and the outcome.
- `%APPDATA%\Brotato\logs\modloader.log`: mod load and error output. Check it first when the overlay never appears (Mod section 2).

The three rules:

- Profile 1 only for bot runs.
- Any bot action on profile 0 or during your own play means halt the bot: Shift+Space turns it off, a move key halts it (Mod section 1, rule 3 and section 4, step 8).
- The bot never runs unattended: you start every run and press Shift+Space yourself (Mod section 1, rule 2).
