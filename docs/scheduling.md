# Scheduling fontctl on login and periodically

Two commands benefit from being run automatically:

- `fontctl startup` — re-applies all active fonts after login/reboot. Essential on Windows (GDI registration is session-only); a harmless no-op on macOS/Linux where symlinks persist across reboots.
- `fontctl deactivate-expired` — deactivates fonts whose `--for` expiry has passed. Run this periodically; how often depends on the shortest expiry you use.

The tool has no background daemon by design. Wire these up yourself using the OS scheduler.

---

## Linux — systemd user timer (recommended)

No root needed. Works on any systemd-based distro.

**1. Create the service unit** (`~/.config/systemd/user/fontctl-expired.service`):

```ini
[Unit]
Description=fontctl deactivate-expired

[Service]
Type=oneshot
ExecStart=%h/.local/bin/fontctl deactivate-expired
```

**2. Create the timer unit** (`~/.config/systemd/user/fontctl-expired.timer`):

```ini
[Unit]
Description=Run fontctl deactivate-expired every 15 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
```

**3. Enable and start:**

```sh
systemctl --user daemon-reload
systemctl --user enable --now fontctl-expired.timer
```

**4. For `fontctl startup` on login**, create a one-shot service (no timer):

`~/.config/systemd/user/fontctl-startup.service`:

```ini
[Unit]
Description=fontctl startup — restore active fonts
After=graphical-session.target

[Service]
Type=oneshot
ExecStart=%h/.local/bin/fontctl startup

[Install]
WantedBy=graphical-session.target
```

```sh
systemctl --user daemon-reload
systemctl --user enable fontctl-startup.service
```

**Adjust `fontctl` path** if installed in a virtualenv:

```ini
ExecStart=/path/to/venv/bin/fontctl deactivate-expired
```

---

## Linux — cron (fallback)

If systemd user units aren't available:

```sh
crontab -e
```

Add:

```cron
*/15 * * * * /home/yourname/.local/bin/fontctl deactivate-expired
@reboot      /home/yourname/.local/bin/fontctl startup
```

Use the full path to `fontctl` — cron runs with a minimal `PATH`.

---

## macOS — launchd

**1. Create a plist** (`~/Library/LaunchAgents/tech.glyphmatrix.expired.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>tech.glyphmatrix.expired</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/fontctl</string>
        <string>deactivate-expired</string>
    </array>
    <key>StartInterval</key>
    <integer>900</integer>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

**2. For `fontctl startup`** (`~/Library/LaunchAgents/tech.glyphmatrix.startup.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>tech.glyphmatrix.startup</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/fontctl</string>
        <string>startup</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

**3. Load both:**

```sh
launchctl load ~/Library/LaunchAgents/tech.glyphmatrix.expired.plist
launchctl load ~/Library/LaunchAgents/tech.glyphmatrix.startup.plist
```

**Adjust `fontctl` path** as needed (e.g. `/opt/homebrew/bin/fontctl` on Apple Silicon, or the full venv path).

To unload: `launchctl unload <plist>`.

---

## Windows — Task Scheduler

Run these once in an elevated PowerShell (or adapt to the GUI).

**`fontctl startup` — at login:**

```powershell
$action  = New-ScheduledTaskAction -Execute "fontctl" -Argument "startup"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "GlyphMatrix Startup" `
    -Action $action -Trigger $trigger `
    -RunLevel Limited -Force
```

**`fontctl deactivate-expired` — every 15 minutes:**

```powershell
$action   = New-ScheduledTaskAction -Execute "fontctl" -Argument "deactivate-expired"
$trigger  = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 15) `
                -Once -At (Get-Date)
Register-ScheduledTask -TaskName "GlyphMatrix Expire" `
    -Action $action -Trigger $trigger `
    -RunLevel Limited -Force
```

If `fontctl` isn't on the system `PATH` for the scheduled user, use the full path to the executable (e.g. `C:\Users\you\AppData\Local\Programs\glyphmatrix\fontctl.exe` or the Scripts path of a venv).

To remove a task: `Unregister-ScheduledTask -TaskName "GlyphMatrix Startup" -Confirm:$false`.

---

## Choosing an interval for `deactivate-expired`

The interval only matters relative to the shortest expiry you use. If you never use `--for` shorter than 1 hour, running every 15–30 minutes is fine. A missed tick just means a font stays active a bit longer than requested — it's not harmful, and the next `fontctl deactivate-expired` (manual or scheduled) cleans it up.
