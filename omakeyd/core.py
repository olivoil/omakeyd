from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


APP_ID = "io.github.olivoil.omakeyd"
APP_VERSION = "0.3.0"
SCHEMA_VERSION = 3

DISPLAY_ROWS = (
    ("q", "w", "e", "r", "t", "y", "u", "i", "o", "p"),
    ("a", "s", "d", "f", "g", "h", "j", "k", "l", ";"),
    ("z", "x", "c", "v", "b", "n", "m", ",", ".", "/"),
)
COLEMAK_DH_ROWS = (
    ("q", "w", "f", "p", "b", "j", "l", "u", "y", ";"),
    ("a", "r", "s", "t", "g", "m", "n", "e", "i", "o"),
    ("z", "x", "c", "d", "v", "k", "h", ",", ".", "/"),
)
# Import-compatible alias for configurations and scripts written against 0.2.
COLEMAK_DH_YOGA_ROWS = COLEMAK_DH_ROWS

ROW_CODES = (
    tuple(f"AD{index:02d}" for index in range(1, 11)),
    tuple(f"AC{index:02d}" for index in range(1, 11)),
    tuple(f"AB{index:02d}" for index in range(1, 11)),
)
KEY_ALIASES = {
    ";": "semicolon",
    ",": "comma",
    ".": "period",
    "/": "slash",
    "dot": "period",
}
DISPLAY_ALIASES = {
    "semicolon": ";",
    "comma": ",",
    "period": ".",
    "slash": "/",
}
SHIFTED_KEYSYM = {
    "semicolon": "colon",
    "comma": "less",
    "period": "greater",
    "slash": "question",
}
PRIMARY_KEYS = tuple(KEY_ALIASES.get(key, key) for row in DISPLAY_ROWS for key in row)
PRIMARY_KEY_SET = frozenset(PRIMARY_KEYS)
DEVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
LAYOUT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
UNTYPED_RE = re.compile(
    r"(?:^|[-_])(?:power-button|sleep-button|lid-switch|video-bus|"
    r"consumer-control|system-control|extra-buttons?)(?:$|[-_])"
)
VIRTUAL_RE = re.compile(r"(?:^|[-_])virtual(?:$|[-_])")
GENERATED_PREFIX = "omakeyd_"


class OmakeydError(RuntimeError):
    def __init__(self, code: str, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def payload(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail:
            error["detail"] = self.detail
        return {"ok": False, "error": error}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str]], CommandResult]


def default_runner(command: Sequence[str]) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command), check=False, capture_output=True, text=True, timeout=20
        )
    except FileNotFoundError as error:
        raise OmakeydError(
            "command-missing", f"Required command is unavailable: {command[0]}", str(error)
        ) from error
    except subprocess.TimeoutExpired as error:
        raise OmakeydError("command-timeout", f"Timed out while running {command[0]}.") from error
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def config_path() -> Path:
    override = os.environ.get("OMAKEYD_CONFIG")
    return Path(override) if override else config_home() / "omakeyd" / "config.json"


def xkb_symbols_dir() -> Path:
    override = os.environ.get("OMAKEYD_XKB_DIR")
    return Path(override) if override else config_home() / "xkb" / "symbols"


def empty_config() -> dict[str, Any]:
    return {"version": SCHEMA_VERSION, "selectedProfile": "", "profiles": {}, "layouts": {}}


def atomic_write_text(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_config(config: dict[str, Any], path: Path | None = None) -> None:
    target = path or config_path()
    serializable = {
        "version": SCHEMA_VERSION,
        "selectedProfile": str(config.get("selectedProfile", "")),
        "profiles": config.get("profiles", {}) if isinstance(config.get("profiles"), dict) else {},
        "layouts": config.get("layouts", {}) if isinstance(config.get("layouts"), dict) else {},
    }
    atomic_write_text(target, json.dumps(serializable, indent=2, sort_keys=True) + "\n")


def normalize_key(value: Any) -> str:
    key = str(value).strip().lower()
    return KEY_ALIASES.get(key, key)


def display_key(value: Any) -> str:
    key = normalize_key(value)
    return DISPLAY_ALIASES.get(key, key)


def validate_rows(rows: Sequence[Sequence[Any]]) -> list[list[str]]:
    if len(rows) != 3 or any(len(row) != 10 for row in rows):
        raise OmakeydError("layout-shape", "A layout needs three rows of ten keys.")
    normalized = [normalize_key(key) for row in rows for key in row]
    counts = Counter(normalized)
    missing = [display_key(key) for key in PRIMARY_KEYS if counts[key] == 0]
    duplicate = [display_key(key) for key, count in counts.items() if count > 1]
    unsupported = [display_key(key) for key in normalized if key not in PRIMARY_KEY_SET]
    if missing or duplicate or unsupported:
        details = []
        if missing:
            details.append("Missing: " + " ".join(missing))
        if duplicate:
            details.append("Repeated: " + " ".join(duplicate))
        if unsupported:
            details.append("Unsupported: " + " ".join(unsupported))
        raise OmakeydError(
            "layout-permutation",
            "Each primary key must appear exactly once.",
            ". ".join(details),
        )
    return [
        [display_key(key) for key in normalized[index : index + 10]]
        for index in range(0, 30, 10)
    ]


def _split_row(value: str, label: str) -> list[str]:
    try:
        tokens = shlex.split(str(value))
    except ValueError as error:
        raise OmakeydError("layout-row", f"{label} row could not be parsed.", str(error)) from error
    if len(tokens) != 10:
        raise OmakeydError(
            "layout-row-count", f"{label} row needs exactly 10 keys.", f"Received {len(tokens)}."
        )
    return tokens


def rows_from_strings(top: str, home: str, bottom: str) -> list[list[str]]:
    return validate_rows(
        (_split_row(top, "Top"), _split_row(home, "Home"), _split_row(bottom, "Bottom"))
    )


def normalized_flat_rows(rows: Sequence[Sequence[Any]]) -> list[str]:
    return [normalize_key(key) for row in validate_rows(rows) for key in row]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "custom-layout"


def humanize_identifier(value: str) -> str:
    known = {
        "at-translated-set-2-keyboard": "Built-in keyboard",
        "zsa-technology-labs-voyager": "ZSA Voyager",
        "zsa-technology-labs-voyager-keyboard": "ZSA Voyager",
    }
    if value in known:
        return known[value]
    words = re.sub(r"[-_]+", " ", value).strip().split()
    return " ".join(
        word.upper() if word.lower() in {"dh", "rgb", "usb", "us"} else word.title()
        for word in words
    ) or value


def brief_for(name: str) -> str:
    lower = name.lower()
    if "qwerty" in lower or name == "English (US)":
        return "US"
    if "colemak" in lower:
        return "DH" if "dh" in lower else "CM"
    if "dvorak" in lower:
        return "DV"
    words = re.findall(r"[A-Za-z0-9]+", name)
    return (words[0] if words else "KB")[:3].upper()


def _builtin_layouts() -> list[dict[str, Any]]:
    return [
        {
            "id": "qwerty",
            "name": "QWERTY (US)",
            "brief": "US",
            "rows": [list(row) for row in DISPLAY_ROWS],
            "source": "built-in",
            "editable": False,
            "removable": False,
        },
        {
            "id": "colemak-dh",
            "name": "Colemak-DH",
            "brief": "DH",
            "rows": [list(row) for row in COLEMAK_DH_ROWS],
            "source": "built-in",
            "editable": False,
            "removable": False,
        },
    ]


def _canonical_layout_id(value: Any) -> str:
    identifier = str(value or "")
    return "colemak-dh" if identifier == "colemak-dh-yoga" else identifier


def _migrate_config(loaded: dict[str, Any]) -> dict[str, Any]:
    migrated = empty_config()
    version = loaded.get("version")
    if version == 1:
        migrated["selectedProfile"] = str(loaded.get("selectedDevice", ""))
        custom = loaded.get("customLayouts", {})
        if isinstance(custom, dict):
            for identifier, definition in custom.items():
                if not isinstance(definition, dict) or not isinstance(definition.get("rows"), list):
                    continue
                try:
                    rows = validate_rows(definition["rows"])
                except OmakeydError:
                    continue
                layout_id = slugify(str(identifier).removeprefix("omakeyd_"))
                migrated["layouts"][layout_id] = {
                    "id": layout_id,
                    "name": str(definition.get("name") or humanize_identifier(layout_id)),
                    "brief": str(definition.get("brief") or brief_for(layout_id)),
                    "rows": rows,
                    "source": "custom",
                }
        devices = loaded.get("devices", {})
        if isinstance(devices, dict):
            for device, state in devices.items():
                if not isinstance(state, dict):
                    continue
                active = state.get("active", {})
                if isinstance(active, dict):
                    layout_id = _canonical_layout_id(active.get("id") or active.get("layout"))
                    if layout_id in {"us", "qwerty-us"}:
                        layout_id = "qwerty"
                    if layout_id:
                        migrated["profiles"][str(device)] = {"lastLayout": layout_id}
        return migrated
    if version == 2:
        migrated["selectedProfile"] = str(loaded.get("selectedProfile", ""))
        if isinstance(loaded.get("profiles"), dict):
            for profile, state in loaded["profiles"].items():
                if not isinstance(state, dict):
                    continue
                migrated["profiles"][str(profile)] = {
                    "lastLayout": _canonical_layout_id(state.get("lastLayout"))
                }
        if isinstance(loaded.get("layouts"), dict):
            migrated["layouts"] = loaded["layouts"]
        return migrated
    raise OmakeydError("config-version", "Omakeyd configuration has an unsupported version.")


def load_config(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    if not target.exists():
        return empty_config()
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OmakeydError(
            "config-invalid", "Omakeyd could not read its configuration.", str(error)
        ) from error
    if not isinstance(loaded, dict):
        raise OmakeydError("config-invalid", "Omakeyd configuration is not an object.")
    if loaded.get("version") != SCHEMA_VERSION:
        migrated = _migrate_config(loaded)
        save_config(migrated, target)
        return migrated
    baseline = empty_config()
    baseline["selectedProfile"] = str(loaded.get("selectedProfile", ""))
    if isinstance(loaded.get("profiles"), dict):
        baseline["profiles"] = loaded["profiles"]
    if isinstance(loaded.get("layouts"), dict):
        baseline["layouts"] = loaded["layouts"]
    return baseline


def _stored_layouts(config: dict[str, Any]) -> list[dict[str, Any]]:
    layouts: list[dict[str, Any]] = []
    for identifier, raw in config.get("layouts", {}).items():
        if not isinstance(raw, dict):
            continue
        try:
            rows = validate_rows(raw.get("rows", []))
        except OmakeydError:
            continue
        layout_id = _canonical_layout_id(raw.get("id") or identifier)
        if not LAYOUT_ID_RE.fullmatch(layout_id) or layout_id in {"qwerty", "colemak-dh"}:
            continue
        name = str(raw.get("name") or humanize_identifier(layout_id))
        layouts.append(
            {
                "id": layout_id,
                "name": name,
                "brief": str(raw.get("brief") or brief_for(name))[:4].upper(),
                "rows": rows,
                "source": "custom",
                "editable": True,
                "removable": True,
            }
        )
    return sorted(layouts, key=lambda item: item["name"].lower())


def all_layouts(config: dict[str, Any], _profiles: Sequence[dict[str, Any]] = ()) -> list[dict[str, Any]]:
    return [*_builtin_layouts(), *_stored_layouts(config)]


def search_layouts(
    layouts: Sequence[dict[str, Any]], query: str, limit: int = 60
) -> list[dict[str, Any]]:
    tokens = [token for token in query.lower().split() if token]
    matches = [
        layout
        for layout in layouts
        if all(
            token
            in f"{layout.get('name', '')} {layout.get('id', '')} {layout.get('brief', '')}".lower()
            for token in tokens
        )
    ]
    return [dict(layout) for layout in matches[: max(1, min(limit, 100))]]


def hypr_keyboards(runner: Runner = default_runner) -> list[dict[str, Any]]:
    result = runner(["hyprctl", "-j", "devices"])
    if result.returncode != 0:
        raise OmakeydError(
            "hyprland-unavailable",
            "Hyprland keyboard devices are unavailable.",
            result.stderr.strip() or result.stdout.strip(),
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise OmakeydError(
            "hyprland-response", "Hyprland returned an invalid device list.", str(error)
        ) from error
    keyboards = payload.get("keyboards", []) if isinstance(payload, dict) else []
    if not isinstance(keyboards, list):
        raise OmakeydError("hyprland-response", "Hyprland returned an invalid keyboard list.")
    return [item for item in keyboards if isinstance(item, dict)]


def _is_typing_keyboard(name: str) -> bool:
    if not name or not DEVICE_RE.fullmatch(name):
        return False
    if name == "keyd-virtual-keyboard" or VIRTUAL_RE.search(name):
        return False
    return not UNTYPED_RE.search(name)


def discover_profiles(runner: Runner = default_runner) -> list[dict[str, Any]]:
    profiles = []
    for keyboard in hypr_keyboards(runner):
        name = str(keyboard.get("name", ""))
        if not _is_typing_keyboard(name):
            continue
        profiles.append(
            {
                "id": name,
                "label": humanize_identifier(name),
                "activeKeymap": str(keyboard.get("active_keymap", "")),
                "activeLayoutIndex": int(keyboard.get("active_layout_index", 0) or 0),
                "runtimeLayouts": str(keyboard.get("layout", "")),
                "runtimeVariants": str(keyboard.get("variant", "")),
            }
        )
    profiles.sort(key=lambda item: (item["label"] != "Built-in keyboard", item["label"].lower()))
    return profiles


def _keyd_active(runner: Runner = default_runner) -> bool:
    result = runner(["systemctl", "is-active", "keyd.service"])
    return result.returncode == 0 and result.stdout.strip() == "active"


def _runtime_layout_name(layout: dict[str, Any]) -> str:
    if layout["id"] == "qwerty":
        return "us"
    fingerprint = ",".join(normalized_flat_rows(layout["rows"]))
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:10]
    safe = re.sub(r"[^a-z0-9_]+", "_", str(layout["id"]).replace("-", "_"))[:32]
    return f"{GENERATED_PREFIX}{safe}_{digest}"


def _xkb_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _xkb_content(layout: dict[str, Any]) -> str:
    lines = [
        "// Generated by Omakeyd. Safe to regenerate.",
        "default partial alphanumeric_keys",
        'xkb_symbols "basic" {',
        '    include "us(basic)"',
        f'    name[Group1] = "{_xkb_string(str(layout["name"]))}";',
        "",
    ]
    for codes, row in zip(ROW_CODES, validate_rows(layout["rows"])):
        for code, key in zip(codes, row):
            lower = normalize_key(key)
            if len(lower) == 1 and lower.isalpha():
                upper = lower.upper()
                key_type = "ALPHABETIC"
            else:
                upper = SHIFTED_KEYSYM[lower]
                key_type = "TWO_LEVEL"
            lines.append(
                f'    key <{code}> {{ type[Group1] = "{key_type}", [ {lower}, {upper} ] }};'
            )
        lines.append("")
    lines.extend(["};", ""])
    return "\n".join(lines)


def _command_detail(result: CommandResult) -> str:
    return result.stderr.strip() or result.stdout.strip() or "The command returned no details."


def materialize_layout(layout: dict[str, Any], runner: Runner = default_runner) -> str:
    runtime = _runtime_layout_name(layout)
    if runtime == "us":
        return runtime
    target = xkb_symbols_dir() / runtime
    content = _xkb_content(layout)
    previous = target.read_text(encoding="utf-8") if target.exists() else None
    if previous is not None and not previous.startswith("// Generated by Omakeyd"):
        raise OmakeydError("xkb-owned", f"Omakeyd will not overwrite {target}.")
    if previous != content:
        atomic_write_text(target, content, 0o644)
    compiled = runner(["xkbcli", "compile-keymap", "--layout", runtime])
    if compiled.returncode != 0:
        if previous is None:
            target.unlink(missing_ok=True)
        elif previous != content:
            atomic_write_text(target, previous, 0o644)
        raise OmakeydError(
            "layout-invalid", f"XKB could not compile {layout['name']}.", _command_detail(compiled)
        )
    return runtime


def _lua_string(value: str) -> str:
    # JSON string literals are valid Lua literals for the restricted ASCII
    # identifiers accepted by this backend.
    return json.dumps(value, ensure_ascii=True)


def _device_lua(device: str, layouts: str, variants: str) -> str:
    if not DEVICE_RE.fullmatch(device):
        raise OmakeydError("profile-id", "Invalid keyboard identifier.")
    return (
        "hl.device({ name = "
        + _lua_string(device)
        + ", kb_layout = "
        + _lua_string(layouts)
        + ", kb_variant = "
        + _lua_string(variants)
        + " })"
    )


def _apply_runtime(device: str, runtimes: Sequence[str], index: int, runner: Runner) -> None:
    layouts = ",".join(runtimes)
    variants = ",".join("" for _ in runtimes)
    configured = runner(["hyprctl", "eval", _device_lua(device, layouts, variants)])
    if configured.returncode != 0 or "error" in configured.stdout.lower():
        raise OmakeydError(
            "apply-failed",
            "Hyprland did not configure the keyboard layouts.",
            _command_detail(configured),
        )
    switched = runner(["hyprctl", "switchxkblayout", device, str(index)])
    if switched.returncode != 0 or "error" in switched.stdout.lower():
        raise OmakeydError(
            "apply-failed", "Hyprland did not switch the keyboard layout.", _command_detail(switched)
        )


def _rollback_runtime(profile: dict[str, Any], runner: Runner) -> None:
    old_layouts = str(profile.get("runtimeLayouts") or "us")
    old_variants = str(profile.get("runtimeVariants") or "")
    runner(["hyprctl", "eval", _device_lua(str(profile["id"]), old_layouts, old_variants)])
    runner(
        [
            "hyprctl",
            "switchxkblayout",
            str(profile["id"]),
            str(int(profile.get("activeLayoutIndex", 0) or 0)),
        ]
    )


def _current_layout(
    profile: dict[str, Any], layouts: Sequence[dict[str, Any]]
) -> dict[str, Any] | None:
    runtime = str(profile.get("runtimeLayouts", "")).split(",")
    index = int(profile.get("activeLayoutIndex", 0) or 0)
    token = runtime[index] if 0 <= index < len(runtime) else ""
    active_name = str(profile.get("activeKeymap", ""))
    for layout in layouts:
        if token == _runtime_layout_name(layout) or active_name == str(layout["name"]):
            return layout
        if layout["id"] == "qwerty" and active_name == "English (US)":
            return layout
    return None


def _select_profile(
    config: dict[str, Any], profiles: Sequence[dict[str, Any]], path: Path | None
) -> str:
    available = {str(profile["id"]) for profile in profiles}
    previous = str(config.get("selectedProfile", ""))
    selected = previous if previous in available else str(profiles[0]["id"]) if profiles else ""
    changed = selected != previous
    if selected and previous and previous not in available:
        old_state = config.get("profiles", {}).get(previous, {})
        new_state = config.setdefault("profiles", {}).setdefault(selected, {})
        if isinstance(old_state, dict) and not new_state.get("lastLayout"):
            last = _canonical_layout_id(old_state.get("lastLayout"))
            if last:
                new_state["lastLayout"] = last
                changed = True
    if changed:
        config["selectedProfile"] = selected
        save_config(config, path)
    return selected


def snapshot(
    query: str = "",
    limit: int = 60,
    runner: Runner = default_runner,
    path: Path | None = None,
) -> dict[str, Any]:
    config = load_config(path)
    profiles = discover_profiles(runner)
    layouts = all_layouts(config)
    selected = _select_profile(config, profiles, path)
    conflict = _keyd_active(runner)
    rendered = []
    layout_ids = {str(layout["id"]) for layout in layouts}
    for profile in profiles:
        current = _current_layout(profile, layouts)
        state = config.get("profiles", {}).get(profile["id"], {})
        configured = _canonical_layout_id(state.get("lastLayout")) if isinstance(state, dict) else ""
        if configured not in layout_ids:
            configured = ""
        payload = dict(profile)
        payload.update(
            {
                "currentLayoutId": str(current.get("id", "")) if current else "",
                "configuredLayoutId": configured,
                "currentName": str(current.get("name"))
                if current
                else str(profile.get("activeKeymap") or "Unknown layout"),
                "currentBrief": str(current.get("brief")) if current else "?",
                "ready": not conflict,
                "canApply": not conflict,
                "needsSetup": False,
            }
        )
        rendered.append(payload)
    return {
        "ok": True,
        "version": SCHEMA_VERSION,
        "backend": "Hyprland/XKB",
        "selectedProfile": selected,
        "profiles": rendered,
        "layouts": search_layouts(layouts, query, limit) if query else layouts,
        "keydConflict": conflict,
        "conflictMessage": (
            "keyd is running and owns the keyboard input path. Stop or disable keyd before using Omakeyd."
            if conflict
            else ""
        ),
        "configPath": str(path or config_path()),
        "xkbSymbolsPath": str(xkb_symbols_dir()),
    }


def select_profile(profile_id: str, path: Path | None = None) -> dict[str, Any]:
    if not DEVICE_RE.fullmatch(profile_id):
        raise OmakeydError("profile-id", "Invalid keyboard identifier.")
    config = load_config(path)
    config["selectedProfile"] = profile_id
    save_config(config, path)
    return {"ok": True, "selectedProfile": profile_id, "message": "Selected keyboard."}


def save_layout(
    name: str,
    brief: str,
    top: str,
    home: str,
    bottom: str,
    identifier: str = "",
    path: Path | None = None,
) -> dict[str, Any]:
    clean_name = name.strip()
    if not clean_name:
        raise OmakeydError("layout-name", "Give the layout a name.")
    rows = rows_from_strings(top, home, bottom)
    layout_id = identifier.strip() or slugify(clean_name)
    if not identifier and layout_id in {"qwerty", "colemak-dh"}:
        layout_id += "-custom"
    if not LAYOUT_ID_RE.fullmatch(layout_id) or layout_id in {"qwerty", "colemak-dh"}:
        raise OmakeydError("layout-id", "That layout identifier is reserved or invalid.")
    config = load_config(path)
    entry = {
        "id": layout_id,
        "name": clean_name,
        "brief": (brief.strip() or brief_for(clean_name))[:4].upper(),
        "rows": rows,
        "source": "custom",
    }
    config.setdefault("layouts", {})[layout_id] = entry
    save_config(config, path)
    return {
        "ok": True,
        "layout": {**entry, "editable": True, "removable": True},
        "message": f"Saved {clean_name}.",
    }


def remove_layout(identifier: str, path: Path | None = None) -> dict[str, Any]:
    if identifier in {"qwerty", "colemak-dh"}:
        raise OmakeydError("layout-required", "Built-in layouts cannot be removed.")
    config = load_config(path)
    layouts = config.setdefault("layouts", {})
    if identifier not in layouts:
        raise OmakeydError("layout-missing", "That custom layout no longer exists.")
    used_by = [
        profile
        for profile, state in config.get("profiles", {}).items()
        if isinstance(state, dict) and _canonical_layout_id(state.get("lastLayout")) == identifier
    ]
    if used_by:
        raise OmakeydError("layout-active", "Switch keyboards using this layout before removing it.")
    name = (
        str(layouts[identifier].get("name", identifier))
        if isinstance(layouts[identifier], dict)
        else identifier
    )
    del layouts[identifier]
    save_config(config, path)
    return {"ok": True, "id": identifier, "message": f"Removed {name}."}


def apply_layout(
    profile_id: str,
    layout_id: str,
    runner: Runner = default_runner,
    path: Path | None = None,
) -> dict[str, Any]:
    if _keyd_active(runner):
        raise OmakeydError(
            "keyd-conflict",
            "keyd is running, so Omakeyd will not change the keyboard input path.",
            "Stop or disable keyd first; Omakeyd now switches layouts through Hyprland and XKB.",
        )
    config = load_config(path)
    layouts = all_layouts(config)
    layout_id = _canonical_layout_id(layout_id)
    layout = next((item for item in layouts if item["id"] == layout_id), None)
    if not layout:
        raise OmakeydError("layout-missing", "That saved layout no longer exists.")
    profiles = discover_profiles(runner)
    profile = next((item for item in profiles if item["id"] == profile_id), None)
    if not profile:
        raise OmakeydError(
            "profile-missing", "That keyboard is no longer connected. No layout was changed."
        )
    runtimes = [materialize_layout(item, runner) for item in layouts]
    index = next(index for index, item in enumerate(layouts) if item["id"] == layout_id)
    try:
        _apply_runtime(profile_id, runtimes, index, runner)
        refreshed = next(
            (item for item in discover_profiles(runner) if item["id"] == profile_id), None
        )
        if not refreshed or int(refreshed.get("activeLayoutIndex", -1)) != index:
            raise OmakeydError(
                "apply-unverified", f"{layout['name']} could not be verified after switching."
            )
    except OmakeydError:
        _rollback_runtime(profile, runner)
        raise
    config["selectedProfile"] = profile_id
    saved_profile = config.setdefault("profiles", {}).setdefault(profile_id, {})
    if not isinstance(saved_profile.get("baseline"), dict):
        saved_profile["baseline"] = {
            "layouts": str(profile.get("runtimeLayouts") or "us"),
            "variants": str(profile.get("runtimeVariants") or ""),
            "index": int(profile.get("activeLayoutIndex", 0) or 0),
        }
    saved_profile["lastLayout"] = layout_id
    save_config(config, path)
    return {
        "ok": True,
        "profile": profile_id,
        "layout": layout_id,
        "name": layout["name"],
        "brief": layout["brief"],
        "message": f"Switched {profile['label']} to {layout['name']}.",
    }


def restore_layouts(
    runner: Runner = default_runner, path: Path | None = None
) -> dict[str, Any]:
    if _keyd_active(runner):
        return {
            "ok": False,
            "restored": [],
            "errors": [{"message": "keyd is running; no XKB layouts were restored."}],
        }
    config = load_config(path)
    profiles = discover_profiles(runner)
    selected = _select_profile(config, profiles, path)
    restored = []
    errors = []
    for profile in profiles:
        state = config.get("profiles", {}).get(profile["id"], {})
        layout_id = _canonical_layout_id(state.get("lastLayout")) if isinstance(state, dict) else ""
        if not layout_id:
            continue
        try:
            restored.append(apply_layout(profile["id"], layout_id, runner, path))
        except OmakeydError as error:
            errors.append({"profile": profile["id"], "message": error.message})
    return {"ok": not errors, "selectedProfile": selected, "restored": restored, "errors": errors}


def reset_layouts(
    runner: Runner = default_runner, path: Path | None = None
) -> dict[str, Any]:
    """Restore the per-device settings that preceded Omakeyd's first apply."""
    config = load_config(path)
    connected = {profile["id"]: profile for profile in discover_profiles(runner)}
    reset = []
    errors = []
    for profile_id, state in config.get("profiles", {}).items():
        baseline = state.get("baseline", {}) if isinstance(state, dict) else {}
        if profile_id not in connected or not isinstance(baseline, dict):
            continue
        layouts = str(baseline.get("layouts") or "")
        variants = str(baseline.get("variants") or "")
        try:
            if not layouts:
                continue
            configured = runner(
                ["hyprctl", "eval", _device_lua(profile_id, layouts, variants)]
            )
            if configured.returncode != 0 or "error" in configured.stdout.lower():
                raise OmakeydError("reset-failed", "Hyprland did not restore the keyboard.")
            switched = runner(
                [
                    "hyprctl",
                    "switchxkblayout",
                    profile_id,
                    str(int(baseline.get("index", 0) or 0)),
                ]
            )
            if switched.returncode != 0 or "error" in switched.stdout.lower():
                raise OmakeydError("reset-failed", "Hyprland did not restore the layout index.")
            reset.append(profile_id)
        except (OmakeydError, TypeError, ValueError) as error:
            errors.append({"profile": profile_id, "message": str(error)})
    return {"ok": not errors, "reset": reset, "errors": errors}


def doctor(runner: Runner = default_runner, path: Path | None = None) -> dict[str, Any]:
    report = snapshot("", 60, runner, path)
    xkb = runner(["xkbcli", "--version"])
    report["checks"] = {
        "hyprland": True,
        "xkb": xkb.returncode == 0,
        "typingKeyboards": len(report["profiles"]),
        "keydConflict": report["keydConflict"],
        "privilegedHelpers": False,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omakeyd")
    parser.add_argument("--version", action="version", version=f"Omakeyd {APP_VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Print panel state as JSON")
    snapshot_parser.add_argument("--query", default="")
    snapshot_parser.add_argument("--limit", type=int, default=60)

    layouts_parser = subparsers.add_parser(
        "layouts", aliases=["catalog"], help="Search saved layouts"
    )
    layouts_parser.add_argument("--query", default="")
    layouts_parser.add_argument("--limit", type=int, default=60)

    select_parser = subparsers.add_parser("select-profile", help="Select a keyboard")
    select_parser.add_argument("--profile", required=True)

    apply_parser = subparsers.add_parser(
        "apply", help="Apply a saved layout through Hyprland"
    )
    apply_parser.add_argument("--profile", required=True)
    apply_parser.add_argument("--layout-id", required=True)

    save_parser = subparsers.add_parser(
        "layout-save", aliases=["custom-save"], help="Save a positional layout"
    )
    save_parser.add_argument("--id", default="")
    save_parser.add_argument("--name", required=True)
    save_parser.add_argument("--brief", default="")
    save_parser.add_argument("--top", required=True)
    save_parser.add_argument("--home", required=True)
    save_parser.add_argument("--bottom", required=True)

    remove_parser = subparsers.add_parser(
        "layout-remove", aliases=["favorite-remove"], help="Remove a custom layout"
    )
    remove_parser.add_argument("--id", required=True)

    subparsers.add_parser("restore", help="Reapply saved per-keyboard layouts")
    subparsers.add_parser("reset", help="Restore keyboard settings from before Omakeyd")
    subparsers.add_parser("doctor", help="Print Hyprland/XKB diagnostics")
    return parser


def dispatch(args: argparse.Namespace, runner: Runner = default_runner) -> dict[str, Any]:
    if args.command == "snapshot":
        return snapshot(args.query, args.limit, runner)
    if args.command in ("layouts", "catalog"):
        state = snapshot(args.query, args.limit, runner)
        return {"ok": True, "layouts": state["layouts"]}
    if args.command == "select-profile":
        return select_profile(args.profile)
    if args.command == "apply":
        return apply_layout(args.profile, args.layout_id, runner)
    if args.command in ("layout-save", "custom-save"):
        return save_layout(args.name, args.brief, args.top, args.home, args.bottom, args.id)
    if args.command in ("layout-remove", "favorite-remove"):
        return remove_layout(args.id)
    if args.command == "restore":
        return restore_layouts(runner)
    if args.command == "reset":
        return reset_layouts(runner)
    if args.command == "doctor":
        return doctor(runner)
    raise OmakeydError("command", "Unknown Omakeyd command.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = dispatch(args)
        print(json.dumps(payload, separators=(",", ":")))
        return 0 if payload.get("ok", True) else 1
    except OmakeydError as error:
        print(json.dumps(error.payload(), separators=(",", ":")))
        return 1
    except Exception as error:  # defensive boundary for a long-lived shell host
        payload = OmakeydError(
            "unexpected",
            "Omakeyd hit an unexpected error. No further action was taken.",
            str(error),
        ).payload()
        print(json.dumps(payload, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    sys.exit(main())
