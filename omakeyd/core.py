from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import signal
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


APP_ID = "io.github.olivoil.omakeyd"
SCHEMA_VERSION = 2
PLUGIN_ROOT = Path(__file__).resolve().parent.parent

DISPLAY_ROWS = (
    ("q", "w", "e", "r", "t", "y", "u", "i", "o", "p"),
    ("a", "s", "d", "f", "g", "h", "j", "k", "l", ";"),
    ("z", "x", "c", "v", "b", "n", "m", ",", ".", "/"),
)

COLEMAK_DH_YOGA_ROWS = (
    ("q", "w", "f", "p", "b", "j", "l", "u", "y", ";"),
    ("a", "r", "s", "t", "g", "m", "n", "e", "i", "o"),
    ("z", "x", "c", "d", "v", "k", "h", ",", ".", "/"),
)

KEY_ALIASES = {
    ";": "semicolon",
    ",": "comma",
    ".": "dot",
    "/": "slash",
}
DISPLAY_ALIASES = {value: key for key, value in KEY_ALIASES.items()}
KEYD_ROWS = tuple(
    tuple(KEY_ALIASES.get(key, key) for key in row) for row in DISPLAY_ROWS
)
PRIMARY_KEYS = tuple(key for row in KEYD_ROWS for key in row)
PRIMARY_KEY_SET = frozenset(PRIMARY_KEYS)

PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
LAYOUT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SECTION_RE = re.compile(r"^\s*\[([^\]]+)]\s*(?:#.*)?$")
MANAGED_BEGIN = "# >>> OMAKEYD MANAGED LAYOUT >>>"
MANAGED_END = "# <<< OMAKEYD MANAGED LAYOUT <<<"
DEFAULT_HELPER = Path("/usr/local/libexec/omakeyd-helper")
DEFAULT_KEYD_DIR = Path("/etc/keyd")


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
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError as error:
        raise OmakeydError(
            "command-missing",
            f"Required command is unavailable: {command[0]}",
            str(error),
        ) from error
    except subprocess.TimeoutExpired as error:
        raise OmakeydError(
            "command-timeout",
            f"Timed out while running {command[0]}.",
        ) from error
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def config_path() -> Path:
    override = os.environ.get("OMAKEYD_CONFIG")
    return Path(override) if override else config_home() / "omakeyd" / "config.json"


def helper_path() -> Path:
    override = os.environ.get("OMAKEYD_HELPER")
    return Path(override) if override else DEFAULT_HELPER


def setup_path() -> Path:
    return PLUGIN_ROOT / "helper" / "omakeyd-setup"


def keyd_directory() -> Path:
    override = os.environ.get("OMAKEYD_KEYD_DIR")
    return Path(override) if override else DEFAULT_KEYD_DIR


def empty_config() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "selectedProfile": "",
        "profiles": {},
        "layouts": {},
    }


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


def _migrate_v1(loaded: dict[str, Any]) -> dict[str, Any]:
    migrated = empty_config()
    custom = loaded.get("customLayouts", {})
    if isinstance(custom, dict):
        for identifier, definition in custom.items():
            if not isinstance(definition, dict) or not isinstance(definition.get("rows"), list):
                continue
            try:
                rows = validate_rows(definition["rows"])
            except OmakeydError:
                continue
            layout_identifier = slugify(str(identifier))
            migrated["layouts"][layout_identifier] = {
                "id": layout_identifier,
                "name": str(definition.get("name") or humanize_identifier(layout_identifier)),
                "brief": str(definition.get("brief") or brief_for(str(definition.get("name", "")))),
                "rows": rows,
                "source": "custom",
            }
    return migrated


def load_config(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    if not target.exists():
        return empty_config()
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OmakeydError(
            "config-invalid",
            "Omakeyd could not read its configuration.",
            str(error),
        ) from error
    if not isinstance(loaded, dict):
        raise OmakeydError("config-invalid", "Omakeyd configuration is not an object.")
    if loaded.get("version") == 1:
        migrated = _migrate_v1(loaded)
        save_config(migrated, target)
        return migrated
    if loaded.get("version") != SCHEMA_VERSION:
        raise OmakeydError(
            "config-version",
            "Omakeyd configuration has an unsupported version.",
        )
    baseline = empty_config()
    baseline["selectedProfile"] = str(loaded.get("selectedProfile", ""))
    if isinstance(loaded.get("profiles"), dict):
        baseline["profiles"] = loaded["profiles"]
    if isinstance(loaded.get("layouts"), dict):
        baseline["layouts"] = loaded["layouts"]
    return baseline


def normalize_key(value: Any) -> str:
    key = str(value).strip().lower()
    return KEY_ALIASES.get(key, key)


def display_key(value: Any) -> str:
    key = normalize_key(value)
    return DISPLAY_ALIASES.get(key, key)


def _split_row(value: str, label: str) -> list[str]:
    try:
        tokens = shlex.split(str(value))
    except ValueError as error:
        raise OmakeydError("layout-row", f"{label} row could not be parsed.", str(error)) from error
    if len(tokens) != 10:
        raise OmakeydError(
            "layout-row-count",
            f"{label} row needs exactly 10 keys.",
            f"Received {len(tokens)}.",
        )
    return tokens


def validate_rows(rows: Sequence[Sequence[Any]]) -> list[list[str]]:
    if len(rows) != 3 or any(len(row) != 10 for row in rows):
        raise OmakeydError(
            "layout-shape",
            "A layout needs three rows of ten keys.",
        )
    normalized = [normalize_key(key) for row in rows for key in row]
    counts = Counter(normalized)
    missing = [display_key(key) for key in PRIMARY_KEYS if counts[key] == 0]
    duplicate = [display_key(key) for key, count in counts.items() if count > 1]
    unsupported = [display_key(key) for key in normalized if key not in PRIMARY_KEY_SET]
    if missing or duplicate or unsupported:
        detail_parts = []
        if missing:
            detail_parts.append("Missing: " + " ".join(missing))
        if duplicate:
            detail_parts.append("Repeated: " + " ".join(duplicate))
        if unsupported:
            detail_parts.append("Unsupported: " + " ".join(unsupported))
        raise OmakeydError(
            "layout-permutation",
            "Each primary key must appear exactly once.",
            ". ".join(detail_parts),
        )
    return [
        [display_key(key) for key in normalized[index : index + 10]]
        for index in range(0, 30, 10)
    ]


def rows_from_strings(top: str, home: str, bottom: str) -> list[list[str]]:
    return validate_rows(
        (
            _split_row(top, "Top"),
            _split_row(home, "Home"),
            _split_row(bottom, "Bottom"),
        )
    )


def normalized_flat_rows(rows: Sequence[Sequence[Any]]) -> list[str]:
    validated = validate_rows(rows)
    return [normalize_key(key) for row in validated for key in row]


def qwerty_layout() -> dict[str, Any]:
    return {
        "id": "qwerty",
        "name": "QWERTY (US)",
        "brief": "US",
        "rows": [list(row) for row in DISPLAY_ROWS],
        "source": "built-in",
        "editable": False,
        "removable": False,
    }


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "custom-layout"


def humanize_identifier(value: str) -> str:
    words = re.sub(r"[-_]+", " ", value).strip().split()
    rendered = " ".join(word.upper() if word.lower() in {"dh", "usb", "us"} else word.title() for word in words)
    return rendered or value


def brief_for(name: str) -> str:
    lower = name.lower()
    if "qwerty" in lower:
        return "US"
    if "colemak" in lower:
        return "DH" if "dh" in lower else "CM"
    if "dvorak" in lower:
        return "DV"
    words = re.findall(r"[A-Za-z0-9]+", name)
    return (words[0] if words else "KB")[:3].upper()


def managed_layer_name(profile_id: str) -> str:
    safe = re.sub(r"[^a-z0-9_]", "_", profile_id.lower().replace("-", "_"))
    return f"omakeyd_{safe}"[:63]


def _simple_mapping(source: str, target: str) -> tuple[str, str] | None:
    source_key = normalize_key(source)
    target_text = target.strip().split("#", 1)[0].strip()
    if any(character in target_text for character in "(),+") or " " in target_text:
        return None
    target_key = normalize_key(target_text)
    if source_key not in PRIMARY_KEY_SET or target_key not in PRIMARY_KEY_SET:
        return None
    return source_key, target_key


def _sections(text: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    sections: dict[str, dict[str, str]] = {}
    ids: list[str] = []
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        header = SECTION_RE.fullmatch(line)
        if header:
            current = header.group(1).split(":", 1)[0].strip().lower()
            sections.setdefault(current, {})
            continue
        clean = raw_line.split("#", 1)[0].strip()
        if not clean:
            continue
        if current == "ids":
            ids.append(clean)
            continue
        if "=" not in clean:
            continue
        source, target = (part.strip() for part in clean.split("=", 1))
        sections.setdefault(current, {})[source.lower()] = target
    return sections, ids


def _mapped_rows(*mappings: dict[str, str]) -> list[list[str]]:
    effective = {key: key for key in PRIMARY_KEYS}
    for mapping in mappings:
        for source, target in mapping.items():
            simple = _simple_mapping(source, target)
            if simple:
                effective[simple[0]] = simple[1]
    return [
        [display_key(effective[key]) for key in row]
        for row in KEYD_ROWS
    ]


def parse_keyd_profile(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    sections, ids = _sections(text)
    if "ids" not in sections:
        return None
    profile_id = path.stem
    if not PROFILE_RE.fullmatch(profile_id):
        return None
    global_section = sections.get("global", {})
    default_layout = str(global_section.get("default_layout", "main")).strip().lower()
    main = sections.get("main", {})
    base_rows = _mapped_rows(main)
    active_section = sections.get(default_layout, {}) if default_layout != "main" else {}
    current_rows = _mapped_rows(main, active_section)
    expected_layer = managed_layer_name(profile_id)
    markers = MANAGED_BEGIN in text and MANAGED_END in text
    ready = markers and default_layout == expected_layer and expected_layer in sections
    if ready:
        setup_reason = ""
    elif markers:
        setup_reason = "The managed keyd layer exists but is not the default layout."
    elif "setlayout(" in text.lower():
        setup_reason = "This profile already switches named keyd layouts and needs manual migration."
    else:
        setup_reason = "One-time setup is required before Omakeyd can switch this profile."
    lower_stem = profile_id.lower()
    label = "Built-in keyboard" if any(word in lower_stem for word in ("laptop", "builtin", "built-in")) else humanize_identifier(profile_id)
    return {
        "id": profile_id,
        "label": label,
        "configPath": str(path),
        "ids": ids,
        "managedLayer": expected_layer,
        "defaultLayout": default_layout,
        "ready": ready,
        "setupReason": setup_reason,
        "baseRows": base_rows,
        "currentRows": current_rows,
    }


def discover_profiles(directory: Path | None = None) -> list[dict[str, Any]]:
    root = directory or keyd_directory()
    if not root.is_dir():
        return []
    profiles = []
    for path in sorted(root.glob("*.conf")):
        parsed = parse_keyd_profile(path)
        if parsed:
            profiles.append(parsed)
    profiles.sort(key=lambda item: (item["label"] != "Built-in keyboard", item["label"].lower()))
    return profiles


def _rows_equal(left: Sequence[Sequence[Any]], right: Sequence[Sequence[Any]]) -> bool:
    try:
        return normalized_flat_rows(left) == normalized_flat_rows(right)
    except OmakeydError:
        return False


def _detected_layout(rows: Sequence[Sequence[Any]], label: str) -> dict[str, Any]:
    validated = validate_rows(rows)
    if _rows_equal(validated, COLEMAK_DH_YOGA_ROWS):
        return {
            "id": "colemak-dh-yoga",
            "name": "Colemak-DH Yoga",
            "brief": "DH",
            "rows": validated,
            "source": "detected",
            "editable": False,
            "removable": False,
        }
    fingerprint = ",".join(normalized_flat_rows(validated))
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:8]
    name = f"{label} layout"
    return {
        "id": f"detected-{digest}",
        "name": name,
        "brief": brief_for(name),
        "rows": validated,
        "source": "detected",
        "editable": False,
        "removable": False,
    }


def _stored_layouts(config: dict[str, Any]) -> list[dict[str, Any]]:
    layouts: list[dict[str, Any]] = []
    for identifier, raw in config.get("layouts", {}).items():
        if not isinstance(raw, dict):
            continue
        try:
            rows = validate_rows(raw.get("rows", []))
        except OmakeydError:
            continue
        layout_id = str(raw.get("id") or identifier)
        if not LAYOUT_ID_RE.fullmatch(layout_id) or layout_id == "qwerty":
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
    return layouts


def all_layouts(config: dict[str, Any], profiles: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    layouts = [qwerty_layout(), *_stored_layouts(config)]
    for profile in profiles:
        for rows in (profile.get("baseRows", []), profile.get("currentRows", [])):
            if not rows or _rows_equal(rows, DISPLAY_ROWS):
                continue
            detected = _detected_layout(rows, str(profile.get("label", "Detected")))
            if not any(_rows_equal(item["rows"], detected["rows"]) for item in layouts):
                layouts.append(detected)
    layouts.sort(key=lambda item: (item["id"] != "qwerty", item["name"].lower()))
    return layouts


def _selected_profile(config: dict[str, Any], profiles: Sequence[dict[str, Any]]) -> str:
    available = {str(profile["id"]) for profile in profiles}
    selected = str(config.get("selectedProfile", ""))
    if selected in available:
        return selected
    return str(profiles[0]["id"]) if profiles else ""


def _helper_status() -> dict[str, Any]:
    runtime = helper_path()
    setup = setup_path()
    pkexec = shutil.which("pkexec")
    return {
        "installed": runtime.is_file() and os.access(runtime, os.X_OK),
        "path": str(runtime),
        "setupAvailable": setup.is_file() and os.access(setup, os.X_OK) and bool(pkexec),
        "setupPath": str(setup),
        "pkexecAvailable": bool(pkexec),
    }


def _latest_keyd_crash(runner: Runner = default_runner) -> dict[str, Any] | None:
    result = runner(["coredumpctl", "--json=short", "--no-pager", "list", "keyd"])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        records = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(records, list) or not records:
        return None
    record = records[-1]
    if not isinstance(record, dict) or str(record.get("exe", "")) != "/usr/bin/keyd":
        return None
    try:
        pid = int(record["pid"])
        signal_number = int(record["sig"])
        signal_name = signal.Signals(signal_number).name
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "pid": pid,
        "process": "keyd",
        "executable": "/usr/bin/keyd",
        "signal": signal_name,
    }


def _match_layout(rows: Sequence[Sequence[Any]], layouts: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    return next((layout for layout in layouts if _rows_equal(rows, layout["rows"])), None)


def snapshot(
    query: str = "",
    limit: int = 60,
    path: Path | None = None,
    keyd_dir: Path | None = None,
    keyd_active: bool | None = None,
) -> dict[str, Any]:
    config = load_config(path)
    profiles = discover_profiles(keyd_dir)
    layouts = all_layouts(config, profiles)
    helper = _helper_status()
    if keyd_active is None:
        if keyd_dir is not None:
            keyd_active = True
        else:
            service = default_runner(["systemctl", "is-active", "keyd.service"])
            keyd_active = service.returncode == 0 and service.stdout.strip() == "active"
    crash = None if keyd_active or keyd_dir is not None else _latest_keyd_crash()
    agent_configured = False
    if crash:
        agent = default_runner(["omarchy-default-agent"])
        agent_configured = agent.returncode == 0 and bool(agent.stdout.strip())
    selected = _selected_profile(config, profiles)
    changed = selected != str(config.get("selectedProfile", ""))
    if changed:
        config["selectedProfile"] = selected
        save_config(config, path)
    rendered_profiles = []
    for profile in profiles:
        current = _match_layout(profile["currentRows"], layouts)
        payload = dict(profile)
        payload["configuredLayoutId"] = str(current.get("id", "")) if current else ""
        payload["currentLayoutId"] = str(current.get("id", "")) if current and keyd_active else ""
        payload["currentName"] = (
            str(current.get("name", "Unknown layout"))
            if current and keyd_active
            else "keyd is not running"
            if not keyd_active
            else "Unknown layout"
        )
        payload["currentBrief"] = str(current.get("brief", "KB")) if current and keyd_active else "!"
        payload["keydActive"] = keyd_active
        payload["canApply"] = bool(profile["ready"] and helper["installed"] and helper["pkexecAvailable"])
        payload["needsSetup"] = bool(not profile["ready"] or not helper["installed"])
        if profile["ready"] and not helper["installed"]:
            payload["setupReason"] = "The managed keyd layout is ready, but its runtime helper needs to be installed."
        rendered_profiles.append(payload)
    filtered = search_layouts(layouts, query, limit) if query else layouts
    return {
        "ok": True,
        "version": SCHEMA_VERSION,
        "selectedProfile": selected,
        "keydActive": keyd_active,
        "keydCrash": crash,
        "agentConfigured": agent_configured,
        "profiles": rendered_profiles,
        "layouts": filtered,
        "helper": helper,
        "configPath": str(path or config_path()),
        "keydDirectory": str(keyd_dir or keyd_directory()),
    }


def search_layouts(
    layouts: Sequence[dict[str, Any]], query: str, limit: int = 60
) -> list[dict[str, Any]]:
    tokens = [token for token in query.lower().split() if token]
    matches = [
        layout
        for layout in layouts
        if all(token in f"{layout.get('name', '')} {layout.get('id', '')} {layout.get('brief', '')}".lower() for token in tokens)
    ]
    return [dict(layout) for layout in matches[: max(1, min(limit, 100))]]


def select_profile(profile_id: str, path: Path | None = None) -> dict[str, Any]:
    if not PROFILE_RE.fullmatch(profile_id):
        raise OmakeydError("profile-id", "Invalid keyd profile identifier.")
    config = load_config(path)
    config["selectedProfile"] = profile_id
    save_config(config, path)
    return {"ok": True, "selectedProfile": profile_id}


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
    if not LAYOUT_ID_RE.fullmatch(layout_id) or layout_id == "qwerty":
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
    if identifier == "qwerty":
        raise OmakeydError("layout-required", "QWERTY is the safe layout and cannot be removed.")
    config = load_config(path)
    layouts = config.setdefault("layouts", {})
    if identifier not in layouts:
        raise OmakeydError("layout-missing", "That custom layout no longer exists.")
    name = str(layouts[identifier].get("name", identifier)) if isinstance(layouts[identifier], dict) else identifier
    del layouts[identifier]
    save_config(config, path)
    return {"ok": True, "id": identifier, "message": f"Removed {name}."}


def _find_profile(profile_id: str, keyd_dir: Path | None = None) -> dict[str, Any]:
    if not PROFILE_RE.fullmatch(profile_id):
        raise OmakeydError("profile-id", "Invalid keyd profile identifier.")
    profile = next(
        (item for item in discover_profiles(keyd_dir) if item["id"] == profile_id),
        None,
    )
    if not profile:
        raise OmakeydError(
            "profile-missing",
            "That keyd profile no longer exists. No layout was changed.",
        )
    return profile


def _pkexec_path() -> str:
    override = os.environ.get("OMAKEYD_PKEXEC")
    resolved = override or shutil.which("pkexec")
    if not resolved:
        raise OmakeydError(
            "pkexec-missing",
            "pkexec is required for the constrained keyd helper.",
        )
    return resolved


def _command_failure(result: CommandResult) -> str:
    text = result.stderr.strip() or result.stdout.strip()
    if not text:
        return "The helper returned no diagnostic output."
    try:
        payload = json.loads(result.stdout)
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            error = payload["error"]
            return str(error.get("detail") or error.get("message") or text)
    except json.JSONDecodeError:
        pass
    return text


def apply_layout(
    profile_id: str,
    layout_id: str,
    runner: Runner = default_runner,
    path: Path | None = None,
    keyd_dir: Path | None = None,
) -> dict[str, Any]:
    profile = _find_profile(profile_id, keyd_dir)
    if not profile["ready"]:
        raise OmakeydError("setup-required", str(profile["setupReason"]))
    config = load_config(path)
    layouts = all_layouts(config, discover_profiles(keyd_dir))
    layout = next((item for item in layouts if item["id"] == layout_id), None)
    if not layout:
        raise OmakeydError("layout-missing", "That saved layout no longer exists.")
    runtime_helper = helper_path()
    if not runtime_helper.is_file() or not os.access(runtime_helper, os.X_OK):
        raise OmakeydError(
            "helper-missing",
            "Omakeyd setup must install its constrained keyd helper before switching.",
        )
    row_argument = ",".join(normalized_flat_rows(layout["rows"]))
    command = [
        _pkexec_path(),
        str(runtime_helper),
        "apply",
        "--profile",
        profile_id,
        "--rows",
        row_argument,
    ]
    result = runner(command)
    if result.returncode != 0:
        raise OmakeydError(
            "apply-failed",
            f"{layout['name']} was not applied.",
            _command_failure(result),
        )
    config["selectedProfile"] = profile_id
    profile_state = config.setdefault("profiles", {}).setdefault(profile_id, {})
    profile_state["lastLayout"] = layout_id
    save_config(config, path)
    return {
        "ok": True,
        "profile": profile_id,
        "layout": layout_id,
        "name": layout["name"],
        "brief": layout["brief"],
        "message": f"Switched {profile['label']} to {layout['name']}.",
    }


def setup_profile(
    profile_id: str,
    runner: Runner = default_runner,
    path: Path | None = None,
    keyd_dir: Path | None = None,
) -> dict[str, Any]:
    profile = _find_profile(profile_id, keyd_dir)
    helper = _helper_status()
    if profile["ready"] and helper["installed"]:
        return {
            "ok": True,
            "profile": profile_id,
            "message": f"{profile['label']} is already ready.",
        }
    installer = setup_path()
    if not installer.is_file() or not os.access(installer, os.X_OK):
        raise OmakeydError("setup-missing", "The Omakeyd setup program is unavailable.")
    if keyd_dir is not None and keyd_dir.resolve() != DEFAULT_KEYD_DIR:
        raise OmakeydError("setup-test-path", "Authenticated setup only operates on /etc/keyd.")
    command = [_pkexec_path(), str(installer), "--profile", profile_id]
    if profile["ready"]:
        command.append("--install-only")
    result = runner(command)
    if result.returncode != 0:
        raise OmakeydError(
            "setup-failed",
            "Omakeyd setup did not change the keyd profile.",
            _command_failure(result),
        )
    config = load_config(path)
    config["selectedProfile"] = profile_id
    save_config(config, path)
    return {
        "ok": True,
        "profile": profile_id,
        "message": (
            f"Reinstalled the constrained helper for {profile['label']}."
            if profile["ready"]
            else f"{profile['label']} is ready. Its current mapping was preserved."
        ),
    }


def restore_layouts(path: Path | None = None, keyd_dir: Path | None = None) -> dict[str, Any]:
    # The selected mapping lives in the root-owned keyd profile and therefore
    # survives daemon, compositor, and shell reloads without replaying commands.
    state = snapshot(path=path, keyd_dir=keyd_dir)
    return {
        "ok": True,
        "restored": [],
        "selectedProfile": state["selectedProfile"],
        "message": "keyd already owns the persistent layout state.",
    }


def doctor(
    runner: Runner = default_runner,
    path: Path | None = None,
    keyd_dir: Path | None = None,
) -> dict[str, Any]:
    version = runner(["keyd", "--version"])
    service = runner(["systemctl", "is-active", "keyd.service"])
    keyd_active = service.returncode == 0 and service.stdout.strip() == "active"
    report = snapshot(path=path, keyd_dir=keyd_dir, keyd_active=keyd_active)
    report["checks"] = {
        "keydInstalled": version.returncode == 0,
        "keydVersion": version.stdout.strip(),
        "keydActive": keyd_active,
        "profiles": len(report["profiles"]),
        "readyProfiles": len([profile for profile in report["profiles"] if profile["ready"]]),
        "helperInstalled": report["helper"]["installed"],
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omakeyd")
    parser.add_argument("--version", action="version", version="Omakeyd 0.2.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Print panel state as JSON")
    snapshot_parser.add_argument("--query", default="")
    snapshot_parser.add_argument("--limit", type=int, default=60)

    layouts_parser = subparsers.add_parser("layouts", aliases=["catalog"], help="Search saved keyd layouts")
    layouts_parser.add_argument("--query", default="")
    layouts_parser.add_argument("--limit", type=int, default=60)

    select_parser = subparsers.add_parser("select-profile", help="Select a keyd profile")
    select_parser.add_argument("--profile", required=True)

    apply_parser = subparsers.add_parser("apply", help="Apply a saved layout through keyd")
    apply_parser.add_argument("--profile", required=True)
    apply_parser.add_argument("--layout-id", required=True)

    save_parser = subparsers.add_parser("layout-save", aliases=["custom-save"], help="Save a positional layout")
    save_parser.add_argument("--id", default="")
    save_parser.add_argument("--name", required=True)
    save_parser.add_argument("--brief", default="")
    save_parser.add_argument("--top", required=True)
    save_parser.add_argument("--home", required=True)
    save_parser.add_argument("--bottom", required=True)

    remove_parser = subparsers.add_parser("layout-remove", aliases=["favorite-remove"], help="Remove a custom layout")
    remove_parser.add_argument("--id", required=True)

    setup_parser = subparsers.add_parser("setup", help="Prepare one keyd profile")
    setup_parser.add_argument("--profile", required=True)

    subparsers.add_parser("restore", help="Report persistent keyd state")
    subparsers.add_parser("doctor", help="Print keyd integration diagnostics")
    return parser


def dispatch(args: argparse.Namespace, runner: Runner = default_runner) -> dict[str, Any]:
    if args.command == "snapshot":
        return snapshot(args.query, args.limit)
    if args.command in ("layouts", "catalog"):
        state = snapshot(args.query, args.limit)
        return {"ok": True, "layouts": state["layouts"]}
    if args.command == "select-profile":
        return select_profile(args.profile)
    if args.command == "apply":
        return apply_layout(args.profile, args.layout_id, runner)
    if args.command in ("layout-save", "custom-save"):
        return save_layout(
            args.name,
            args.brief,
            args.top,
            args.home,
            args.bottom,
            args.id,
        )
    if args.command in ("layout-remove", "favorite-remove"):
        return remove_layout(args.id)
    if args.command == "setup":
        return setup_profile(args.profile, runner)
    if args.command == "restore":
        return restore_layouts()
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
