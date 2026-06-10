---
description: Install (or remove) a macOS launchd agent that runs /collect-jobs every hour.
argument-hint: [install | remove | status]
allowed-tools: Bash, Read, Write
---

You are setting up the hourly auto-collection schedule for the user.

## What the user wants

A launchd agent on their Mac that fires `scripts/collect-jobs-hourly.sh` every
hour while the laptop is awake. The user invoked: $ARGUMENTS

If $ARGUMENTS is empty or "install" → install the schedule.
If $ARGUMENTS is "remove" → unload + delete the plist.
If $ARGUMENTS is "status" → show whether it's loaded and last/next fire.

## Steps for `install` (the default)

1. **Verify prerequisites.** From the project root:
   ```bash
   test -x scripts/collect-jobs-hourly.sh || echo "missing"
   test -f .venv/bin/python              || echo "no venv"
   test -f profile/profile.md            || echo "no profile"
   ```
   If any are missing, stop and tell the user to run `./install.sh` first
   (or create the missing file).

2. **Compute the user-specific paths.**
   ```bash
   PROJECT_ROOT="$(pwd)"
   PLIST="$HOME/Library/LaunchAgents/com.${USER}.wat-collect-jobs.plist"
   LABEL="com.${USER}.wat-collect-jobs"
   ```

3. **Write the plist** by piping a here-doc into `$PLIST`. Use `$PROJECT_ROOT`
   and `$LABEL` so it's portable; the body should mirror the template in
   README.md §Scheduling but with absolute paths derived from `$PROJECT_ROOT`
   and the user's `$HOME`. StartInterval = 3600 (1 hour). RunAtLoad = false.

4. **Load it**:
   ```bash
   launchctl unload "$PLIST" 2>/dev/null || true   # idempotent
   launchctl load "$PLIST"
   launchctl list | grep "$LABEL" || { echo "load failed"; exit 1; }
   ```

5. **Fire it once for a smoke test**:
   ```bash
   launchctl start "$LABEL"
   sleep 3
   tail -20 temp/outputs/launchd.log
   ```
   You should see a `── … /collect-jobs ──` block ending with the stats line.

6. **Report back** to the user:
   - Plist path that was written
   - Confirmation that the smoke fire succeeded (or the error)
   - How they can stop / re-enable / inspect logs:
     - `launchctl unload "$PLIST"` to pause
     - `launchctl load "$PLIST"` to resume
     - `tail -f temp/outputs/launchd.log` to watch live

## Steps for `remove`

```bash
PLIST="$HOME/Library/LaunchAgents/com.${USER}.wat-collect-jobs.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "  removed $PLIST"
```

## Steps for `status`

```bash
launchctl list | grep "wat-collect-jobs" || echo "  not loaded"
ls -la "$HOME/Library/LaunchAgents/com.${USER}.wat-collect-jobs.plist" 2>/dev/null
echo ""
echo "Most recent runs from temp/outputs/launchd.log:"
grep "/collect-jobs" temp/outputs/launchd.log | tail -5
```

## Constraints

- **macOS only** for now. If `uname -s` returns anything other than `Darwin`,
  tell the user this command only handles launchd; for Linux they want
  `crontab -e` with `0 * * * * cd <project-root> && ./scripts/collect-jobs-hourly.sh`.
- **Don't silently overwrite** an existing plist with different content — diff
  first if `$PLIST` exists, and ask the user before clobbering.
- **No remote dependencies.** This is purely a launchd configuration; nothing
  needs to be installed beyond what `./install.sh` already set up.
