# Steam Cloud and the mod's user directory

Question (spec section 8): does Steam Cloud sync files the mod writes under the
game's `user://` (`%APPDATA%\Brotato\`)? If it does, the mod's files would be
uploaded and could be overwritten by another machine's copy, so the root must
move out of `user://`.

The mod's single game-side root is `BotPaths.ROOT` in
`mod/Ellie-BrotatoBot/core/bot_paths.gd`, currently `user://brotato-bot`.

## Measurement procedure

1. Sync the mod (`.\scripts\sync_mod.ps1`). `mod_main.gd` `_init` writes
   `BotPaths.ROOT + "/probe.txt"` (an ISO local timestamp) every time the mod
   loads, so `%APPDATA%\Brotato\brotato-bot\probe.txt` exists after a launch.
2. Launch Brotato through Steam once, reach the main menu, quit.
3. Wait one minute for Steam to finish its post-exit sync.
4. Search every Steam remote cache index for the folder name:

   ```powershell
   Get-ChildItem 'C:\Program Files (x86)\Steam\userdata\*\1942280\remotecache.vdf' |
       Select-String -SimpleMatch 'brotato-bot'
   ```

5. If any match appears, change `ROOT` to
   `OS.get_environment("LOCALAPPDATA").plus_file("brotato-bot")` and change the
   plan 2 `paths.py` default `mod_user_dir` to match. Otherwise keep
   `user://brotato-bot`.
6. Record the date, the command output and the decision below.

## Result

Result: pending (attended measurement not yet run).
