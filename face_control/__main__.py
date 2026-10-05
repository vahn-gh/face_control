"""Entry point: python -m face_control."""

import argparse
import logging
import sys
from pathlib import Path

from face_control import config as config_module
from face_control.camera import CameraError
from face_control.config import Config, ConfigError
from face_control.config import parse as parse_config
from face_control.profiles import PROFILE_NAMES, CalibrationError

log = logging.getLogger("face_control")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="face_control", description="Webcam posture monitor")
    parser.add_argument("--config", type=Path, help="config file (default: ~/.config/face_control/config.toml)")
    parser.add_argument("--window", action="store_true", help="show the mini window on start")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    # Overrides for single config values; flags win over the config file.
    parser.add_argument("--camera", type=int, help="camera device index")
    parser.add_argument("--fps", type=float, help="target capture FPS")
    parser.add_argument("--margin", type=float, help="profile tolerance multiplier")
    parser.add_argument("--no-sound", action="store_true", help="disable the alert sound")
    parser.add_argument("--volume", type=float, help="alert volume 0-1")
    parser.add_argument("--sound-file", type=Path, help="custom alert sound")
    parser.add_argument("--repeat-interval", type=float, help="seconds between repeat alerts; 0 = off")
    parser.add_argument("--window-width", type=int, help="mini window width")
    sub = parser.add_subparsers(dest="command")
    cal = sub.add_parser("calibrate", help="record a posture as a profile")
    cal.add_argument("profile", choices=PROFILE_NAMES)
    cal.add_argument("--seconds", type=float, default=5.0, help="recording length (default 5)")
    cal.add_argument("--countdown", type=float, default=3.0, help="get-ready time (default 3)")
    pr = sub.add_parser("pitch-range", help="set the OK head pitch range (degrees) for a profile")
    pr.add_argument("profile", choices=PROFILE_NAMES)
    pr.add_argument("min", type=float, nargs="?", help="lowest OK pitch (negative = looking down)")
    pr.add_argument("max", type=float, nargs="?", help="highest OK pitch")
    pr.add_argument("--clear", action="store_true", help="go back to calibrated neutral +/- deviation")
    sub.add_parser("init-config", help="write a commented default config file")
    sub.add_parser("install-launch-agent", help="start face_control at login (macOS)")
    sub.add_parser("uninstall-launch-agent", help="remove the login item")
    return parser


def apply_overrides(config: Config, args: argparse.Namespace) -> Config:
    """Command-line flags win over the config file. Values are re-validated."""
    data = {
        "camera": {"index": args.camera, "fps": args.fps},
        "rules": {"margin": args.margin},
        "sound": {
            "enabled": False if args.no_sound else None,
            "volume": args.volume,
            "file": str(args.sound_file) if args.sound_file else None,
            "repeat_interval": args.repeat_interval,
        },
        "window": {"width": args.window_width},
    }
    cur = config_module.to_data(config)
    for section, values in data.items():
        cur[section].update({k: v for k, v in values.items() if v is not None})
    return parse_config(cur)


def set_pitch_range(args: argparse.Namespace) -> int:
    import dataclasses

    from face_control import profile_store

    if args.clear == (args.min is not None):
        raise RuntimeError("Give either MIN MAX or --clear.")
    if not args.clear and (args.max is None or args.min > args.max):
        raise RuntimeError("Give MIN MAX with MIN <= MAX.")
    store = profile_store.load()
    profile = store.profiles.get(args.profile)
    if profile is None:
        raise RuntimeError(f"No '{args.profile}' profile yet. Run: python -m face_control calibrate {args.profile}")
    pitch_range = None if args.clear else (args.min, args.max)
    store.profiles[args.profile] = dataclasses.replace(profile, pitch_range=pitch_range)
    profile_store.save(store)
    print(f"{args.profile}: pitch range " + ("cleared" if args.clear else f"{args.min:g} to {args.max:g}"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.command == "init-config":
            print(f"Wrote {config_module.write_default(args.config)}")
            return 0
        if args.command == "install-launch-agent":
            from face_control import launchagent

            path = launchagent.install(args.config)
            print(f"Installed {path}\nface_control will start at login. Logs: {launchagent.log_path()}")
            return 0
        if args.command == "uninstall-launch-agent":
            from face_control import launchagent

            print("Removed." if launchagent.uninstall() else "Launch agent was not installed.")
            return 0

        if args.command == "pitch-range":
            return set_pitch_range(args)

        config = apply_overrides(config_module.load(args.config), args)

        # Imported lazily: Qt and MediaPipe are slow to load and --help shouldn't pay for them.
        if args.command == "calibrate":
            from face_control.calibrate import calibrate

            calibrate(args.profile, config.camera.index, config.camera.fps, args.countdown, args.seconds)
            return 0

        from face_control import profile_store

        if not profile_store.load().profiles:
            log.warning("No profiles yet. Run: python -m face_control calibrate upright")

        from face_control.app import run_app

        return run_app(config, args.window or config.window.show_on_start)
    except (CameraError, CalibrationError, ConfigError, RuntimeError) as e:
        log.error("%s", e)
        return 1
    except KeyboardInterrupt:
        log.info("Interrupted, shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
