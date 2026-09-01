"""Smoke-test the packaged Desktop and Native Host executables together."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import time


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_directory", type=Path)
    parser.add_argument("--state-directory", type=Path, required=True)
    return parser.parse_args()


def _decode_first_native_message(raw_output: bytes) -> dict[str, object]:
    if len(raw_output) < 4:
        raise RuntimeError("Native Host returned no framed response")
    payload_length = struct.unpack("<I", raw_output[:4])[0]
    payload = raw_output[4 : 4 + payload_length]
    if len(payload) != payload_length:
        raise RuntimeError("Native Host returned a truncated response")
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Native Host response is not a JSON object")
    return value


def main() -> int:
    """Launch packaged Desktop, handshake through packaged host, then stop it."""
    args = _parse_args()
    release_directory = args.release_directory.resolve(strict=True)
    desktop_exe = release_directory / "ShopeeImageDownloader.exe"
    native_host_exe = release_directory / "native_host" / "shopee_native_host.exe"
    for executable in (desktop_exe, native_host_exe):
        if not executable.is_file():
            raise FileNotFoundError(executable)

    state_directory = args.state_directory.resolve()
    local_state = state_directory / "local"
    roaming_state = state_directory / "roaming"
    temp_state = state_directory / "temp"
    for directory in (local_state, roaming_state, temp_state):
        directory.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    environment.update(
        {
            "LOCALAPPDATA": str(local_state),
            "APPDATA": str(roaming_state),
            "TEMP": str(temp_state),
            "TMP": str(temp_state),
            "QT_QPA_PLATFORM": "offscreen",
        }
    )

    startup_info = subprocess.STARTUPINFO()
    startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup_info.wShowWindow = subprocess.SW_HIDE
    desktop = subprocess.Popen(
        [str(desktop_exe)],
        cwd=release_directory,
        env=environment,
        startupinfo=startup_info,
    )
    try:
        time.sleep(3.0)
        if desktop.poll() is not None:
            raise RuntimeError(
                f"Packaged Desktop exited early with code {desktop.returncode}"
            )

        request = json.dumps(
            {"type": "connect_desktop", "protocol_version": 1},
            separators=(",", ":"),
        ).encode("utf-8")
        frame = struct.pack("<I", len(request)) + request
        host_result = subprocess.run(
            [str(native_host_exe)],
            input=frame,
            capture_output=True,
            cwd=release_directory,
            env=environment,
            startupinfo=startup_info,
            timeout=20,
            check=False,
        )
        if host_result.returncode != 0:
            raise RuntimeError(
                f"Packaged Native Host exited with code {host_result.returncode}"
            )
        response = _decode_first_native_message(host_result.stdout)
        if response.get("type") != "bridge_status":
            raise RuntimeError(f"Unexpected Native Host response: {response!r}")
        if response.get("desktop_connected") is not True:
            raise RuntimeError(f"Packaged Desktop handshake failed: {response!r}")

        print("APP_LAUNCH=PASS")
        print("PACKAGED_NATIVE_HOST_HANDSHAKE=PASS")
        return 0
    finally:
        if desktop.poll() is None:
            desktop.terminate()
            try:
                desktop.wait(timeout=10)
            except subprocess.TimeoutExpired:
                desktop.kill()
                desktop.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
