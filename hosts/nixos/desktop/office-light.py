#!/usr/bin/env python3
"""Control the office light through the Home Assistant REST API.

Set HA_URL and HA_TOKEN in the environment. With no argument, toggle the
light. Use --on/--off for idempotent boot and shutdown hooks.
"""

import fcntl
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
import urllib.error
import urllib.request

ENTITY_ID = "light.kontorskab_kontorlys"


def request(ha_url: str, token: str, path: str, payload: dict | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{ha_url.rstrip('/')}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        body = response.read()
        return json.loads(body) if body else None


def _screen_state_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_dir:
        raise RuntimeError("XDG_RUNTIME_DIR is required for screen-light state.")
    return Path(runtime_dir) / "office-light-screen.json"


@contextmanager
def _screen_state_lock(state_path: Path) -> Iterator[None]:
    lock_path = state_path.with_suffix(".lock")
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        yield


def _write_screen_state(state_path: Path, state: dict[str, bool]) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=state_path.parent, delete=False
    ) as state_file:
        os.chmod(state_file.name, 0o600)
        json.dump(state, state_file)
        state_file.flush()
        os.fsync(state_file.fileno())
        temp_path = Path(state_file.name)
    os.replace(temp_path, state_path)


def _brightness() -> int:
    return 75 if datetime.now().hour < 18 else 40


def screen_off(ha_url: str, token: str) -> None:
    """Turn the light off for a display-off cycle and remember whether to restore it."""
    state_path = _screen_state_path()
    with _screen_state_lock(state_path):
        if state_path.exists():
            print("Office display is already tracked as off.")
            return

        current = request(ha_url, token, f"/api/states/{ENTITY_ID}").get("state")
        if current not in {"on", "off"}:
            raise ValueError(f"Unexpected state for {ENTITY_ID}: {current!r}")

        restore_light = current == "on"
        _write_screen_state(state_path, {"restore_light": restore_light})
        if restore_light:
            try:
                request(
                    ha_url,
                    token,
                    "/api/services/light/turn_off",
                    {"entity_id": ENTITY_ID},
                )
            except Exception:
                state_path.unlink(missing_ok=True)
                raise
        print(
            "Office light turned off for display sleep."
            if restore_light
            else "Office light was already off; leaving it off on display wake."
        )


def screen_on(ha_url: str, token: str) -> None:
    """Restore the light only if screen-off automation found it on beforehand."""
    state_path = _screen_state_path()
    with _screen_state_lock(state_path):
        if not state_path.exists():
            print("No office-light display-off state to restore.")
            return

        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not isinstance(state.get("restore_light"), bool):
            raise ValueError("Invalid office-light display state.")

        if state["restore_light"]:
            current = request(ha_url, token, f"/api/states/{ENTITY_ID}").get("state")
            if current == "off":
                brightness = _brightness()
                request(
                    ha_url,
                    token,
                    "/api/services/light/turn_on",
                    {"entity_id": ENTITY_ID, "brightness_pct": brightness},
                )
                print(f"Restored office light at {brightness}%.")
            elif current == "on":
                print("Office light is already on; no change needed.")
            else:
                raise ValueError(f"Unexpected state for {ENTITY_ID}: {current!r}")
        else:
            print("Office light was off before display sleep; leaving it off.")
        state_path.unlink()


def main() -> int:
    valid_modes = {"--on", "--off", "--screen-off", "--screen-on"}
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] not in valid_modes):
        print(f"Usage: {sys.argv[0]} [--on|--off|--screen-off|--screen-on]", file=sys.stderr)
        return 2

    ha_url = os.environ.get("HA_URL")
    token = os.environ.get("HA_TOKEN")
    if not ha_url or not token:
        print("Set both HA_URL and HA_TOKEN environment variables.", file=sys.stderr)
        return 2

    try:
        mode = sys.argv[1] if len(sys.argv) == 2 else None
        if mode == "--screen-off":
            screen_off(ha_url, token)
            return 0
        if mode == "--screen-on":
            screen_on(ha_url, token)
            return 0
        if mode is None:
            current = request(ha_url, token, f"/api/states/{ENTITY_ID}").get("state")
            if current not in {"on", "off"}:
                print(f"Unexpected state for {ENTITY_ID}: {current!r}", file=sys.stderr)
                return 1
            turn_on = current == "off"
            turn_off = current == "on"
        else:
            current = None
            turn_on = mode == "--on"
            turn_off = mode == "--off"

        if turn_off and current == "off":
            print("Office light already off; no change needed.")
            return 0

        if turn_on:
            brightness = _brightness()
            service = "turn_on"
            payload = {"entity_id": ENTITY_ID, "brightness_pct": brightness}
        else:
            brightness = None
            service = "turn_off"
            payload = {"entity_id": ENTITY_ID}
        request(ha_url, token, f"/api/services/light/{service}", payload)

        target = "on" if turn_on else "off"
        suffix = f" at {brightness}%" if brightness is not None else ""
        print(f"Requested office light {target}{suffix}.")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"Home Assistant returned HTTP {exc.code}.", file=sys.stderr)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Could not reach Home Assistant: {exc}", file=sys.stderr)
    except (ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(f"Unexpected Home Assistant response: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
