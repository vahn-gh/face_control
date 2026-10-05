# face_control

A macOS menu-bar utility that watches your webcam and nags you (red overlay + sound) when your
posture breaks your own rules: head tilted too far up/down, facing sideways, sitting too low,
standing on a chair, or any position you haven't calibrated. Everything runs locally on the CPU.

## Setup

Requires Python 3.11+ on macOS.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'     # drop [dev] if you don't want pytest
python -m face_control
```

The first run downloads two MediaPipe model files (~9 MB) into `models/`.

### Camera permission

macOS asks for camera access the first time. The permission belongs to the **app that launched
Python** (Terminal, iTerm, VS Code, ...). If you get "Cannot open camera":

1. System Settings → Privacy & Security → Camera → enable your terminal app.
2. Quit and reopen the terminal, then run again.

For launch-at-login (below), the permission prompt may come from `python` itself; approve it
the first time, or run once from a terminal that already has access.

## Calibrate your postures

Profiles describe the postures that are OK. Calibrate each one you use, sitting or standing the
way you normally do, with your head and shoulders in view:

```
python -m face_control calibrate upright      # sitting straight
python -m face_control calibrate reclined     # leaning back
python -m face_control calibrate standing     # standing desk
```

You get a 3-second countdown, then 5 seconds of recording: hold still. The recorded values are
printed and saved to `~/.config/face_control/profiles.json`. You can also calibrate from the
tray menu (Calibrate → ...); the app pauses, records, and resumes.

While running, the app matches your current posture to the nearest profile. If none fits, or
your head turns too far, tilts too far or sits too high/low, that's a violation. Violations
only count after 3 seconds, so brief slips are ignored.

By default head pitch is OK within `pitch_max_deviation` of the profile's calibrated pitch. To
set an explicit OK range for a profile instead (degrees, negative = looking down):

```
python -m face_control pitch-range reclined -- -10 5   # OK from -10 to +5
python -m face_control pitch-range reclined --clear    # back to calibrated +/- deviation
```

The range is kept when you recalibrate that profile.

If your normal posture gets flagged, raise `margin` in the config (e.g. `1.5`) and recalibrate
if needed.

## Running

```
python -m face_control            # menu-bar icon only
python -m face_control --window   # also show the floating mini window
```

Tray icon: green = OK, red = violating, blue-grey = nobody in frame, grey = paused.
Left-click the icon to show/hide the window under it; right-click (or ctrl-click) for the menu:
Show/Hide window, Pause/Resume (pausing releases the camera, so the light turns off),
Calibrate, Quit (right-click the window for the same menu). The mini window can be dragged, resized by scrolling over it, and hidden with
Esc. `kill -USR1 <pid>` toggles it too.

## Config

Optional single TOML file at `~/.config/face_control/config.toml`
(`FACE_CONTROL_CONFIG_DIR` changes the folder, `--config path` uses another file):

```
python -m face_control init-config    # writes a commented file with all defaults
```

Edit it and restart the app. Invalid values stop the app with a message naming the key.
Command-line flags (`--fps`, `--camera`, `--margin`, `--no-sound`, `--volume`, `--sound-file`,
`--repeat-interval`, `--window-width`) override the file for that run.

## Launch at login

```
python -m face_control install-launch-agent      # add --config path before it to bake one in
python -m face_control uninstall-launch-agent
```

This writes `~/Library/LaunchAgents/com.face-control.agent.plist` pointing at the current
Python (so install from the venv you want it to use) and logs to `~/Library/Logs/face_control.log`.

## Development

```
python -m pytest
```

Rules, matching, debounce and alert timing are pure modules with unit tests; camera, UI and
sound are thin wrappers around them.
