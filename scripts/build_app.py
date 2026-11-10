"""Native build helper. Run on the platform required by Flet/Flutter."""

import argparse
import importlib.util
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from prepare_app import prepare


def preflight(target):
    host = platform.system()
    errors = []
    if target == "windows" and host != "Windows":
        errors.append("Windows installers must be built on Windows (or a Windows CI runner).")
    if target in ("macos", "ipa", "ios-simulator") and host != "Darwin":
        errors.append("Apple targets require macOS.")
    if target in ("macos", "ipa", "ios-simulator") and not Path("/Applications/Xcode.app").exists():
        errors.append(
            "Install full Xcode and its required platform components before this Apple build."
        )
    if target in ("apk", "aab"):
        import os

        sdk = Path(
            os.environ.get("ANDROID_HOME")
            or os.environ.get("ANDROID_SDK_ROOT")
            or Path.home() / "Library" / "Android" / "sdk"
        )
        if not sdk.exists():
            errors.append(
                "Install Android SDK/command-line tools and accept its licences before this Android build."
            )
    if importlib.util.find_spec("flet_cli") is None:
        errors.append('Install the build extra: python -m pip install ".[build]".')
    return dict(
        target=target,
        host=host,
        ready=not errors,
        issues=errors,
        note="Build readiness is preliminary; signing, SDK licences and a real device/build check are still required.",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target", choices=["apk", "aab", "ipa", "ios-simulator", "macos", "windows"]
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Inspect prerequisites without building or starting a server.",
    )
    args = parser.parse_args()
    report = preflight(args.target)
    print(json.dumps(report, indent=2))
    if args.check:
        return
    if not report["ready"]:
        raise SystemExit(2)
    prepare()
    subprocess.run(
        [sys.executable, "-m", "flet.cli", "build", args.target, "--python-version", "3.13"],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
