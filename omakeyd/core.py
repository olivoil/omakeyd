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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


APP_ID = "io.github.olivoil.omakeyd"
SCHEMA_VERSION = 1

TOP_CODES = tuple(f"AD{i:02d}" for i in range(1, 11))
HOME_CODES = tuple(f"AC{i:02d}" for i in range(1, 11))
BOTTOM_CODES = tuple(f"AB{i:02d}" for i in range(1, 11))
ROW_CODES = (TOP_CODES, HOME_CODES, BOTTOM_CODES)
ALL_ROW_CODES = TOP_CODES + HOME_CODES + BOTTOM_CODES

QWERTY_ROWS = (
    ("q", "w", "e", "r", "t", "y", "u", "i", "o", "p"),
    ("a", "s", "d", "f", "g", "h", "j", "k", "l", "semicolon"),
    ("z", "x", "c", "v", "b", "n", "m", "comma", "period", "slash"),
)

CODE_TO_US_KEY = {
    code: key
    for codes, keys in zip(ROW_CODES, QWERTY_ROWS)
    for code, key in zip(codes, keys)
}
US_KEY_TO_CODE = {key: code for code, key in CODE_TO_US_KEY.items()}

# keyd accepts printable aliases in addition to these names. Keep the table
# explicit so a custom mapping cannot smuggle an action into generated XKB.
KEY_ALIASES = {
    ";": "semicolon",
    ",": "comma",
    ".": "period",
    "/": "slash",
    "'": "apostrophe",
    "-": "minus",
    "=": "equal",
    "[": "leftbrace",
    "]": "rightbrace",
    "\\": "backslash",
    "`": "grave",
}

CHAR_TO_KEYSYM = {
    ";": "semicolon",
    ":": "colon",
    ",": "comma",
    "<": "less",
    ".": "period",
    ">": "greater",
    "/": "slash",
    "?": "question",
    "'": "apostrophe",
    '"': "quotedbl",
    "-": "minus",
    "_": "underscore",
    "=": "equal",
    "+": "plus",
    "[": "bracketleft",
    "{": "braceleft",
    "]": "bracketright",
    "}": "braceright",
    "\\": "backslash",
    "|": "bar",
    "`": "grave",
    "~": "asciitilde",
    "!": "exclam",
    "@": "at",
    "#": "numbersign",
    "$": "dollar",
    "%": "percent",
    "^": "asciicircum",
    "&": "ampersand",
    "*": "asterisk",
    "(": "parenleft",
    ")": "parenright",
}

SHIFTED_KEYSYM = {
    "semicolon": "colon",
    "comma": "less",
    "period": "greater",
    "slash": "question",
    "apostrophe": "quotedbl",
    "minus": "underscore",
    "equal": "plus",
    "bracketleft": "braceleft",
    "bracketright": "braceright",
    "backslash": "bar",
    "grave": "asciitilde",
    "1": "exclam",
    "2": "at",
    "3": "numbersign",
    "4": "dollar",
    "5": "percent",
    "6": "asciicircum",
    "7": "ampersand",
    "8": "asterisk",
    "9": "parenleft",
    "0": "parenright",
}

XKB_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
KEYSYM_RE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*|U[0-9A-Fa-f]{4,8}|[0-9]+)$")
COMPILED_KEY_RE = re.compile(
    r"key\s+<([A-Z0-9]+)>\s*\{\s*\[([^\]]*)\]\s*\};",
    re.MULTILINE,
)
UNTYPED_RE = re.compile(
    r"(?:^|[-_])(?:power-button|sleep-button|lid-switch|video-bus|"
    r"consumer-control|system-control|extra-buttons?)(?:$|[-_])"
)
VIRTUAL_RE = re.compile(r"(?:^|[-_])virtual(?:$|[-_])")


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
            timeout=12,
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
            f"Timed out while running {command[0]}",
        ) from error
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def config_path() -> Path:
    override = os.environ.get("OMAKEYD_CONFIG")
    return Path(override) if override else config_home() / "omakeyd" / "config.json"


def xkb_symbols_dir() -> Path:
    return config_home() / "xkb" / "symbols"


def empty_config() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "selectedDevice": "",
        "favorites": [
            {
                "id": "qwerty-us",
                "name": "QWERTY (US)",
                "brief": "US",
                "layout": "us",
                "variant": "",
                "source": "system",
            }
        ],
        "devices": {},
        "customLayouts": {},
    }


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
    if not isinstance(loaded, dict) or loaded.get("version") != SCHEMA_VERSION:
        raise OmakeydError(
            "config-version",
            "Omakeyd configuration has an unsupported version.",
        )
    baseline = empty_config()
    for key in ("selectedDevice", "favorites", "devices", "customLayouts"):
        if key in loaded:
            baseline[key] = loaded[key]
    if not isinstance(baseline["favorites"], list):
        baseline["favorites"] = []
    if not isinstance(baseline["devices"], dict):
        baseline["devices"] = {}
    if not isinstance(baseline["customLayouts"], dict):
        baseline["customLayouts"] = {}
    return baseline


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
    atomic_write_text(target, json.dumps(config, indent=2, sort_keys=True) + "\n")


def _yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def parse_xkbcli_list(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    def finish() -> None:
        nonlocal current
        if current and current.get("layout") and "variant" in current:
            description = current.get("description") or layout_human_name(
                current["layout"], current.get("variant", "")
            )
            entries.append(
                {
                    "layout": current["layout"],
                    "variant": current.get("variant", ""),
                    "brief": current.get("brief", ""),
                    "name": description,
                    "source": "system",
                }
            )
        current = None

    for line in str(text or "").splitlines():
        start = re.match(r"^- layout:\s*(.*)$", line)
        if start:
            finish()
            current = {"layout": _yaml_scalar(start.group(1))}
            continue
        if current is None:
            continue
        field = re.match(r"^  (variant|brief|description):\s*(.*)$", line)
        if field:
            current[field.group(1)] = _yaml_scalar(field.group(2))
    finish()
    return entries


def layout_human_name(layout: str, variant: str = "") -> str:
    words = re.sub(r"[_-]+", " ", variant or layout).strip().title()
    return words.replace("Us", "US").replace("Dh", "DH") or layout


def brief_for(name: str, layout: str = "") -> str:
    lower = f"{name} {layout}".lower()
    if "qwerty" in lower or name == "English (US)":
        return "US"
    if "colemak" in lower:
        return "DH" if "dh" in lower else "CM"
    if "dvorak" in lower:
        return "DV"
    letters = re.findall(r"[A-Za-z0-9]+", name)
    return (letters[0] if letters else layout or "?")[:3].upper()


def parse_custom_symbols(path: Path) -> list[dict[str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    sections = list(re.finditer(r'\bxkb_symbols\s+"([A-Za-z0-9_-]+)"\s*\{', text))
    results: list[dict[str, str]] = []
    for index, match in enumerate(sections):
        variant = match.group(1)
        end = sections[index + 1].start() if index + 1 < len(sections) else len(text)
        body = text[match.end() : end]
        named = re.search(r'name\s*\[\s*Group1\s*\]\s*=\s*"([^"]+)"', body)
        name = named.group(1) if named else layout_human_name(path.name, variant)
        results.append(
            {
                "layout": path.name,
                "variant": "" if variant in ("basic", "default") and index == 0 else variant,
                "brief": brief_for(name, path.name),
                "name": name,
                "source": "custom",
            }
        )
    return results


def custom_catalog(config: dict[str, Any] | None = None) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    directory = xkb_symbols_dir()
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if not path.is_file() or not XKB_ID_RE.fullmatch(path.name):
                continue
            if path.name.startswith("omakeyd_comp_"):
                continue
            entries.extend(parse_custom_symbols(path))
    if config:
        for definition in config.get("customLayouts", {}).values():
            if not isinstance(definition, dict):
                continue
            entry = {
                "layout": str(definition.get("layout", "")),
                "variant": str(definition.get("variant", "")),
                "brief": str(definition.get("brief", "")),
                "name": str(definition.get("name", "")),
                "source": "omakeyd",
            }
            if entry["layout"]:
                entries.append(entry)
    return deduplicate_layouts(entries)


def deduplicate_layouts(entries: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    source_priority = {"omakeyd": 3, "custom": 2, "system": 1}
    for entry in entries:
        key = (entry.get("layout", ""), entry.get("variant", ""))
        if not key[0]:
            continue
        existing = by_key.get(key)
        if existing is None or source_priority.get(entry.get("source", ""), 0) > source_priority.get(
            existing.get("source", ""), 0
        ):
            normalized = dict(entry)
            normalized["id"] = layout_id(*key)
            normalized["brief"] = normalized.get("brief") or brief_for(
                normalized.get("name", ""), key[0]
            )
            by_key[key] = normalized
    return sorted(by_key.values(), key=lambda item: (item["name"].lower(), item["layout"], item["variant"]))


def system_catalog(runner: Runner = default_runner) -> list[dict[str, str]]:
    result = runner(["xkbcli", "list", "--load-exotic"])
    if result.returncode != 0:
        raise OmakeydError(
            "xkb-catalog",
            "The installed XKB layout catalogue could not be read.",
            result.stderr.strip(),
        )
    return parse_xkbcli_list(result.stdout)


def full_catalog(config: dict[str, Any], runner: Runner = default_runner) -> list[dict[str, str]]:
    return deduplicate_layouts([*custom_catalog(config), *system_catalog(runner)])


def search_catalog(
    entries: Sequence[dict[str, str]], query: str = "", limit: int = 60
) -> list[dict[str, str]]:
    tokens = [token for token in query.lower().split() if token]

    def score(entry: dict[str, str]) -> tuple[int, str, str, str] | None:
        name = entry.get("name", "").lower()
        layout = entry.get("layout", "").lower()
        variant = entry.get("variant", "").lower()
        haystack = f"{name} {layout} {variant} {entry.get('brief', '').lower()}"
        if any(token not in haystack for token in tokens):
            return None
        rank = 40
        joined = " ".join(tokens)
        if joined and name.startswith(joined):
            rank = 0
        elif joined and layout.startswith(joined):
            rank = 5
        elif joined and any(word.startswith(joined) for word in name.split()):
            rank = 10
        elif not tokens:
            rank = 20 if entry.get("source") in ("custom", "omakeyd") else 30
        return rank, name, layout, variant

    ranked: list[tuple[tuple[int, str, str, str], dict[str, str]]] = []
    for entry in entries:
        entry_score = score(entry)
        if entry_score is not None:
            ranked.append((entry_score, entry))
    ranked.sort(key=lambda pair: pair[0])
    return [dict(entry) for _, entry in ranked[: max(1, min(limit, 200))]]


def layout_id(layout: str, variant: str = "") -> str:
    return f"{layout}/{variant}" if variant else layout


def validate_xkb_id(value: str, field: str) -> str:
    if not value or not XKB_ID_RE.fullmatch(value):
        raise OmakeydError(
            "layout-identifier",
            f"Invalid XKB {field}: {value!r}",
        )
    return value


def compile_keymap(layout: str, variant: str = "", runner: Runner = default_runner) -> str:
    validate_xkb_id(layout, "layout")
    if variant:
        validate_xkb_id(variant, "variant")
    command = ["xkbcli", "compile-keymap", "--layout", layout]
    if variant:
        command.extend(["--variant", variant])
    result = runner(command)
    if result.returncode != 0:
        raise OmakeydError(
            "layout-invalid",
            f"XKB could not compile {layout_id(layout, variant)}.",
            result.stderr.strip() or result.stdout.strip(),
        )
    return result.stdout


def compiled_symbols(text: str) -> dict[str, list[str]]:
    symbols: dict[str, list[str]] = {}
    for match in COMPILED_KEY_RE.finditer(text):
        values = [value.strip() for value in match.group(2).split(",")]
        symbols[match.group(1)] = [value for value in values if value]
    return symbols


def primary_rows(layout: str, variant: str = "", runner: Runner = default_runner) -> list[list[str]]:
    symbols = compiled_symbols(compile_keymap(layout, variant, runner))
    rows: list[list[str]] = []
    for codes in ROW_CODES:
        rows.append([symbols.get(code, [CODE_TO_US_KEY[code]])[0] for code in codes])
    return rows


def normalize_key_name(name: str) -> str:
    lowered = str(name).strip().lower()
    return KEY_ALIASES.get(lowered, lowered)


def parse_keyd_config(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    section = ""
    mappings: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        header = re.fullmatch(r"\[([^\]]+)\]", line)
        if header:
            section = header.group(1).split(":", 1)[0].strip().lower()
            continue
        if section != "main" or "=" not in line:
            continue
        source_name, target_name = (part.strip() for part in line.split("=", 1))
        if any(character in target_name for character in "(),+"):
            continue
        source_key = normalize_key_name(source_name)
        target_key = normalize_key_name(target_name)
        source_code = US_KEY_TO_CODE.get(source_key)
        target_code = US_KEY_TO_CODE.get(target_key)
        if source_code and target_code:
            mappings[source_code] = target_code
    if not mappings:
        return None
    stem = path.stem
    lower_text = text.lower()
    alias = "Built-in keyboard" if "built-in" in lower_text or "laptop" in stem.lower() else "keyd keyboard"
    name = layout_human_name(re.sub(r"^(?:laptop|keyboard)[-_]", "", stem))
    return {
        "kind": "keyd",
        "name": name,
        "alias": alias,
        "path": str(path),
        "mappings": mappings,
        "automatic": True,
    }


def detect_keyd_sources(directory: Path = Path("/etc/keyd")) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []
    sources = []
    for path in sorted(directory.glob("*.conf")):
        parsed = parse_keyd_config(path)
        if parsed:
            sources.append(parsed)
    return sources


def source_rows(source: dict[str, Any]) -> list[list[str]]:
    mappings = source.get("mappings", {})
    rows: list[list[str]] = []
    for codes in ROW_CODES:
        row = []
        for physical_code in codes:
            emitted_code = mappings.get(physical_code, physical_code)
            row.append(CODE_TO_US_KEY.get(emitted_code, emitted_code))
        rows.append(row)
    return rows


def match_source_to_layout(
    source: dict[str, Any],
    entries: Sequence[dict[str, str]],
    runner: Runner = default_runner,
) -> dict[str, str] | None:
    wanted = source_rows(source)
    # User-owned layouts carry the exact machine-specific intent, so inspect
    # them before generic system variants and cap work to likely candidates.
    candidates = sorted(
        entries,
        key=lambda item: (
            0 if item.get("source") in ("custom", "omakeyd") else 1,
            0 if "colemak" in item.get("name", "").lower() else 1,
            item.get("name", ""),
        ),
    )
    for entry in candidates[:80]:
        name = entry.get("name", "").lower()
        if entry.get("source") == "system" and not any(
            hint in name for hint in ("colemak", "dvorak", "workman", "qwerty")
        ):
            continue
        try:
            if primary_rows(entry["layout"], entry.get("variant", ""), runner) == wanted:
                return dict(entry)
        except OmakeydError:
            continue
    return None


def manual_source_for(device_name: str, config: dict[str, Any]) -> dict[str, Any] | None:
    device = config.get("devices", {}).get(device_name, {})
    source = device.get("source") if isinstance(device, dict) else None
    if not isinstance(source, dict) or not isinstance(source.get("mappings"), dict):
        return None
    normalized = dict(source)
    normalized["mappings"] = {
        str(key): str(value) for key, value in source["mappings"].items()
    }
    normalized["automatic"] = False
    return normalized


def source_for_device(
    device_name: str,
    config: dict[str, Any],
    catalog: Sequence[dict[str, str]],
    runner: Runner = default_runner,
    keyd_dir: Path = Path("/etc/keyd"),
) -> tuple[dict[str, Any] | None, str]:
    manual = manual_source_for(device_name, config)
    if manual:
        return manual, ""
    if device_name != "keyd-virtual-keyboard":
        return None, ""
    sources = detect_keyd_sources(keyd_dir)
    if not sources:
        return None, "keyd is active, but no simple letter mapping could be identified."
    if len(sources) > 1:
        return None, "Several keyd mappings feed this virtual keyboard; choose a physical source map first."
    source = sources[0]
    matched = match_source_to_layout(source, catalog, runner)
    if matched:
        source["name"] = matched["name"]
        source["layout"] = matched["layout"]
        source["variant"] = matched.get("variant", "")
        source["brief"] = matched.get("brief") or brief_for(matched["name"])
    else:
        source["brief"] = brief_for(source["name"])
    return source, ""


def hypr_keyboards(runner: Runner = default_runner) -> list[dict[str, Any]]:
    result = runner(["hyprctl", "devices", "-j"])
    if result.returncode != 0:
        # Some hyprctl versions require flags before the command.
        result = runner(["hyprctl", "-j", "devices"])
    if result.returncode != 0:
        raise OmakeydError(
            "hyprland-unavailable",
            "Hyprland keyboard devices are unavailable.",
            result.stderr.strip(),
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise OmakeydError(
            "hyprland-response",
            "Hyprland returned an invalid device list.",
            str(error),
        ) from error
    keyboards = payload.get("keyboards", []) if isinstance(payload, dict) else []
    return keyboards if isinstance(keyboards, list) else []


def humanize_device(name: str) -> str:
    replacements = {
        "at-translated-set-2-keyboard": "Built-in keyboard",
        "keyd-virtual-keyboard": "keyd virtual keyboard",
        "logitech-pro-x": "Logitech PRO X",
        "zsa-technology-labs-voyager": "ZSA Voyager",
        "zsa-technology-labs-voyager-keyboard": "ZSA Voyager",
    }
    if name in replacements:
        return replacements[name]
    words = re.sub(r"[-_]+", " ", name).split()
    return " ".join(word.upper() if word in ("usb", "rgb") else word.title() for word in words)


def is_auxiliary_keyboard(name: str) -> bool:
    return bool(UNTYPED_RE.search(name))


def favorite_payload(entry: dict[str, Any]) -> dict[str, str]:
    name = str(entry.get("name") or layout_human_name(str(entry.get("layout", "")), str(entry.get("variant", ""))))
    return {
        "id": str(entry.get("id") or layout_id(str(entry.get("layout", "")), str(entry.get("variant", "")))),
        "name": name,
        "brief": str(entry.get("brief") or brief_for(name, str(entry.get("layout", "")))),
        "layout": str(entry.get("layout", "")),
        "variant": str(entry.get("variant", "")),
        "source": str(entry.get("source", "system")),
    }


def ensure_initial_favorites(
    config: dict[str, Any], catalog: Sequence[dict[str, str]]
) -> bool:
    changed = False
    favorites = [favorite_payload(item) for item in config.get("favorites", []) if isinstance(item, dict)]
    existing = {(item["layout"], item["variant"]) for item in favorites}
    if ("us", "") not in existing:
        favorites.insert(0, favorite_payload(empty_config()["favorites"][0]))
        existing.add(("us", ""))
        changed = True
    yoga = next(
        (
            entry
            for entry in catalog
            if entry.get("layout") == "colemak_dh_yoga"
            or "colemak-dh yoga" in entry.get("name", "").lower()
        ),
        None,
    )
    if yoga and (yoga["layout"], yoga.get("variant", "")) not in existing:
        favorites.append(favorite_payload(yoga))
        changed = True
    if config.get("favorites") != favorites:
        config["favorites"] = favorites
        changed = True
    return changed


def device_snapshot(
    raw_keyboards: Sequence[dict[str, Any]],
    config: dict[str, Any],
    catalog: Sequence[dict[str, str]],
    runner: Runner = default_runner,
    keyd_dir: Path = Path("/etc/keyd"),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    connected_names = {str(item.get("name", "")) for item in raw_keyboards}
    keyd_connected = "keyd-virtual-keyboard" in connected_names
    visible: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    seen_labels: set[str] = set()

    for raw in raw_keyboards:
        name = str(raw.get("name", ""))
        if not name:
            continue
        reason = ""
        if is_auxiliary_keyboard(name):
            reason = "auxiliary input"
        elif VIRTUAL_RE.search(name) and name != "keyd-virtual-keyboard":
            reason = "virtual keyboard"
        elif keyd_connected and name == "at-translated-set-2-keyboard":
            reason = "underlying device managed by keyd"
        elif name.endswith("-keyboard") and name.removesuffix("-keyboard") in connected_names:
            reason = "duplicate keyboard endpoint"
        if reason:
            ignored.append({"name": name, "label": humanize_device(name), "reason": reason})
            continue

        source, source_error = source_for_device(name, config, catalog, runner, keyd_dir)
        saved = config.get("devices", {}).get(name, {})
        alias = str(saved.get("alias", "")) if isinstance(saved, dict) else ""
        if not alias and source:
            alias = str(source.get("alias", ""))
        label = alias or humanize_device(name)
        if label in seen_labels:
            label = f"{label} ({name})"
        seen_labels.add(label)

        raw_layout = str(raw.get("layout", ""))
        raw_keymap = str(raw.get("active_keymap", ""))
        active = saved.get("active", {}) if isinstance(saved, dict) else {}
        runtime_layout = str(active.get("runtimeLayout", "")) if isinstance(active, dict) else ""
        runtime_matches = bool(runtime_layout and runtime_layout in raw_layout.split(","))

        if runtime_matches:
            effective_name = str(active.get("name", raw_keymap))
            effective_brief = str(active.get("brief") or brief_for(effective_name))
            effective_layout = str(active.get("layout", ""))
            effective_variant = str(active.get("variant", ""))
        elif source and raw_layout.split(",")[0] == "us":
            effective_name = str(source.get("name", raw_keymap or "Remapped layout"))
            effective_brief = str(source.get("brief") or brief_for(effective_name))
            effective_layout = str(source.get("layout", ""))
            effective_variant = str(source.get("variant", ""))
        else:
            effective_name = raw_keymap or layout_human_name(raw_layout.split(",")[0] or "Unknown")
            effective_brief = brief_for(effective_name, raw_layout)
            effective_layout = raw_layout.split(",")[0]
            effective_variant = ""

        mapping_detail = "Direct XKB device"
        transport = "hardware"
        if source:
            transport = str(source.get("kind", "remapped"))
            mapping_detail = f"{source.get('name', 'Source remap')} → XKB"
        elif source_error:
            transport = "ambiguous"
            mapping_detail = source_error
        elif VIRTUAL_RE.search(name):
            transport = "virtual"
            mapping_detail = "Virtual keyboard, no physical source map configured"

        source_payload = dict(source) if source else {}
        if source_payload:
            source_payload["rows"] = source_rows(source_payload)

        visible.append(
            {
                "name": name,
                "label": label,
                "main": bool(raw.get("main", False)),
                "transport": transport,
                "canApply": not bool(source_error),
                "blockedReason": source_error,
                "rawLayout": raw_layout,
                "rawKeymap": raw_keymap,
                "effectiveLayout": effective_layout,
                "effectiveVariant": effective_variant,
                "effectiveName": effective_name,
                "effectiveBrief": effective_brief,
                "mappingDetail": mapping_detail,
                "source": source_payload,
            }
        )

    visible.sort(key=lambda item: (not item["main"], item["label"].lower(), item["name"]))
    return visible, ignored


def selected_device(config: dict[str, Any], keyboards: Sequence[dict[str, Any]]) -> str:
    configured = str(config.get("selectedDevice", ""))
    names = {keyboard["name"] for keyboard in keyboards}
    if configured in names:
        return configured
    main = next((keyboard["name"] for keyboard in keyboards if keyboard.get("main")), "")
    return main or (keyboards[0]["name"] if keyboards else "")


def snapshot(
    query: str = "",
    limit: int = 60,
    runner: Runner = default_runner,
    path: Path | None = None,
    keyd_dir: Path = Path("/etc/keyd"),
) -> dict[str, Any]:
    config = load_config(path)
    catalog = full_catalog(config, runner)
    changed = ensure_initial_favorites(config, catalog)
    raw = hypr_keyboards(runner)
    keyboards, ignored = device_snapshot(raw, config, catalog, runner, keyd_dir)
    chosen = selected_device(config, keyboards)
    if chosen and config.get("selectedDevice") != chosen:
        config["selectedDevice"] = chosen
        changed = True
    if changed:
        save_config(config, path)
    favorites = [favorite_payload(item) for item in config.get("favorites", []) if isinstance(item, dict)]
    return {
        "ok": True,
        "version": SCHEMA_VERSION,
        "selectedDevice": chosen,
        "keyboards": keyboards,
        "ignoredKeyboards": ignored,
        "favorites": favorites,
        "catalog": search_catalog(catalog, query, limit),
        "configPath": str(path or config_path()),
        "xkbSymbolsPath": str(xkb_symbols_dir()),
    }


def select_device(name: str, path: Path | None = None) -> dict[str, Any]:
    if not name or "]" in name or "\n" in name:
        raise OmakeydError("device-name", "Invalid keyboard identifier.")
    config = load_config(path)
    config["selectedDevice"] = name
    save_config(config, path)
    return {"ok": True, "selectedDevice": name}


def _xkb_include(layout: str, variant: str) -> str:
    validate_xkb_id(layout, "layout")
    if variant:
        validate_xkb_id(variant, "variant")
        return f'{layout}({variant})'
    return layout


def _xkb_name(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def compensation_content(
    source: dict[str, Any],
    target_layout: str,
    target_variant: str,
    target_name: str,
    compiled_target: str,
) -> str:
    mappings = source.get("mappings", {})
    if not isinstance(mappings, dict) or not mappings:
        raise OmakeydError("source-map", "The keyboard source map is empty.")
    target_symbols = compiled_symbols(compiled_target)
    emitted_seen: set[str] = set()
    overrides: list[str] = []
    for physical_code, emitted_code in sorted(mappings.items()):
        if physical_code not in CODE_TO_US_KEY or emitted_code not in CODE_TO_US_KEY:
            raise OmakeydError("source-map", "The source map contains an unsupported physical key.")
        if emitted_code in emitted_seen:
            raise OmakeydError(
                "source-map-collision",
                "The source map sends more than one physical key to the same position.",
                emitted_code,
            )
        emitted_seen.add(emitted_code)
        symbols = target_symbols.get(physical_code)
        if not symbols:
            raise OmakeydError(
                "target-symbols",
                f"The target layout has no symbols for <{physical_code}>.",
            )
        if physical_code == emitted_code:
            continue
        overrides.append(f"    key <{emitted_code}> {{ [ {', '.join(symbols)} ] }};")
    source_name = str(source.get("name", "source remap"))
    return "\n".join(
        [
            "// Generated by Omakeyd. Safe to regenerate.",
            "default partial alphanumeric_keys",
            'xkb_symbols "basic" {',
            f'    include "{_xkb_include(target_layout, target_variant)}"',
            f'    name[Group1]= "{_xkb_name(target_name)} (corrected for {_xkb_name(source_name)})";',
            *overrides,
            "};",
            "",
        ]
    )


def ensure_compensation_layout(
    source: dict[str, Any],
    target_layout: str,
    target_variant: str,
    target_name: str,
    runner: Runner = default_runner,
) -> tuple[str, str]:
    compiled_target = compile_keymap(target_layout, target_variant, runner)
    fingerprint = json.dumps(
        {
            "source": source.get("mappings", {}),
            "layout": target_layout,
            "variant": target_variant,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:12]
    layout = f"omakeyd_comp_{digest}"
    target = xkb_symbols_dir() / layout
    content = compensation_content(
        source, target_layout, target_variant, target_name, compiled_target
    )
    previous = target.read_text(encoding="utf-8") if target.exists() else None
    if previous != content:
        atomic_write_text(target, content, 0o644)
    try:
        compile_keymap(layout, "", runner)
    except OmakeydError:
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            atomic_write_text(target, previous, 0o644)
        raise
    return layout, ""


def apply_runtime_layout(
    device: str, layout: str, variant: str, runner: Runner = default_runner
) -> None:
    if not device or "]" in device or "\n" in device:
        raise OmakeydError("device-name", "Invalid keyboard identifier.")
    validate_xkb_id(layout, "layout")
    if variant:
        validate_xkb_id(variant, "variant")
    variant_key = f"device[{device}]:kb_variant"
    layout_key = f"device[{device}]:kb_layout"
    commands = [
        ["hyprctl", "-r", "--", "keyword", variant_key, ""],
        ["hyprctl", "-r", "--", "keyword", layout_key, layout],
    ]
    if variant:
        commands.append(["hyprctl", "-r", "--", "keyword", variant_key, variant])
    for command in commands:
        result = runner(command)
        if result.returncode != 0 or "error" in result.stdout.lower():
            raise OmakeydError(
                "apply-failed",
                f"Hyprland did not apply the layout to {device}.",
                result.stderr.strip() or result.stdout.strip(),
            )


def apply_layout(
    device: str,
    layout: str,
    variant: str,
    name: str,
    brief: str,
    runner: Runner = default_runner,
    path: Path | None = None,
    keyd_dir: Path = Path("/etc/keyd"),
    persist: bool = True,
) -> dict[str, Any]:
    config = load_config(path)
    catalog = full_catalog(config, runner)
    raw = hypr_keyboards(runner)
    if device not in {str(item.get("name", "")) for item in raw}:
        raise OmakeydError(
            "device-disconnected",
            f"{device} is no longer connected. No layout was changed.",
        )
    source, source_error = source_for_device(device, config, catalog, runner, keyd_dir)
    if source_error:
        raise OmakeydError("source-ambiguous", source_error)
    target_name = name or next(
        (
            item["name"]
            for item in catalog
            if item["layout"] == layout and item.get("variant", "") == variant
        ),
        layout_human_name(layout, variant),
    )
    target_brief = brief or brief_for(target_name, layout)
    compile_keymap(layout, variant, runner)
    runtime_layout, runtime_variant = (
        ensure_compensation_layout(source, layout, variant, target_name, runner)
        if source
        else (layout, variant)
    )
    apply_runtime_layout(device, runtime_layout, runtime_variant, runner)

    if persist:
        devices = config.setdefault("devices", {})
        saved = devices.setdefault(device, {})
        saved["active"] = {
            "layout": layout,
            "variant": variant,
            "name": target_name,
            "brief": target_brief,
            "runtimeLayout": runtime_layout,
            "runtimeVariant": runtime_variant,
        }
        config["selectedDevice"] = device
        save_config(config, path)
    return {
        "ok": True,
        "device": device,
        "layout": layout,
        "variant": variant,
        "name": target_name,
        "brief": target_brief,
        "runtimeLayout": runtime_layout,
        "runtimeVariant": runtime_variant,
        "compensated": bool(source),
        "mapping": str(source.get("name", "")) if source else "",
        "message": f"{target_name} now applies to {humanize_device(device)}.",
    }


def add_favorite(
    layout: str,
    variant: str,
    name: str,
    brief: str,
    source: str = "system",
    runner: Runner = default_runner,
    path: Path | None = None,
) -> dict[str, Any]:
    compile_keymap(layout, variant, runner)
    config = load_config(path)
    entry = favorite_payload(
        {
            "id": layout_id(layout, variant),
            "layout": layout,
            "variant": variant,
            "name": name or layout_human_name(layout, variant),
            "brief": brief,
            "source": source,
        }
    )
    favorites = [
        favorite_payload(item)
        for item in config.get("favorites", [])
        if isinstance(item, dict)
        and (str(item.get("layout", "")), str(item.get("variant", "")))
        != (layout, variant)
    ]
    favorites.append(entry)
    config["favorites"] = favorites
    save_config(config, path)
    return {"ok": True, "favorite": entry, "message": f"Added {entry['name']} to saved layouts."}


def remove_favorite(identifier: str, path: Path | None = None) -> dict[str, Any]:
    config = load_config(path)
    before = config.get("favorites", [])
    after = [item for item in before if str(item.get("id", "")) != identifier]
    if len(after) == len(before):
        raise OmakeydError("favorite-missing", "That saved layout no longer exists.")
    config["favorites"] = after
    save_config(config, path)
    return {"ok": True, "id": identifier, "message": "Removed the saved layout."}


def _split_row(value: str, label: str) -> list[str]:
    try:
        tokens = shlex.split(value)
    except ValueError as error:
        raise OmakeydError("custom-row", f"{label} row could not be parsed.", str(error)) from error
    if len(tokens) != 10:
        raise OmakeydError(
            "custom-row-count",
            f"{label} row needs exactly 10 space-separated keys.",
            f"Received {len(tokens)}.",
        )
    return tokens


def _normalize_keysym(value: str) -> str:
    if len(value) == 1 and value in CHAR_TO_KEYSYM:
        return CHAR_TO_KEYSYM[value]
    if len(value) == 1 and value.isalpha():
        return value.lower()
    if KEYSYM_RE.fullmatch(value):
        return value
    raise OmakeydError("keysym", f"Unsupported XKB symbol: {value!r}")


def keysym_levels(token: str) -> list[str] | None:
    if token == "_":
        return None
    if ":" in token:
        lower, upper = token.split(":", 1)
        return [_normalize_keysym(lower), _normalize_keysym(upper)]
    lower = _normalize_keysym(token)
    if len(lower) == 1 and lower.isalpha():
        upper = lower.upper()
    else:
        upper = SHIFTED_KEYSYM.get(lower, lower)
    return [lower, upper]


def custom_layout_content(
    name: str,
    base_layout: str,
    base_variant: str,
    rows: Sequence[Sequence[str]],
) -> str:
    lines = [
        "// Generated by Omakeyd. Safe to edit through Omakeyd.",
        "default partial alphanumeric_keys",
        'xkb_symbols "basic" {',
        f'    include "{_xkb_include(base_layout, base_variant)}"',
        f'    name[Group1]= "{_xkb_name(name)}";',
        "",
    ]
    for codes, tokens in zip(ROW_CODES, rows):
        for code, token in zip(codes, tokens):
            levels = keysym_levels(token)
            if levels:
                lines.append(f"    key <{code}> {{ [ {', '.join(levels)} ] }};")
        lines.append("")
    lines.extend(["};", ""])
    return "\n".join(lines)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug[:40] or "custom"


def save_custom_layout(
    name: str,
    brief: str,
    base_layout: str,
    base_variant: str,
    top: str,
    home: str,
    bottom: str,
    runner: Runner = default_runner,
    path: Path | None = None,
) -> dict[str, Any]:
    if not name.strip():
        raise OmakeydError("custom-name", "Give the custom layout a name.")
    compile_keymap(base_layout, base_variant, runner)
    rows = (
        _split_row(top, "Top"),
        _split_row(home, "Home"),
        _split_row(bottom, "Bottom"),
    )
    layout = f"omakeyd_{slugify(name)}"
    target = xkb_symbols_dir() / layout
    content = custom_layout_content(name.strip(), base_layout, base_variant, rows)
    previous = target.read_text(encoding="utf-8") if target.exists() else None
    if previous and not previous.startswith("// Generated by Omakeyd"):
        raise OmakeydError(
            "custom-owned",
            f"Omakeyd will not overwrite the existing XKB file {target}.",
        )
    atomic_write_text(target, content, 0o644)
    try:
        compile_keymap(layout, "", runner)
    except OmakeydError:
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            atomic_write_text(target, previous, 0o644)
        raise

    config = load_config(path)
    entry = favorite_payload(
        {
            "id": layout,
            "layout": layout,
            "variant": "",
            "name": name.strip(),
            "brief": brief,
            "source": "omakeyd",
        }
    )
    config.setdefault("customLayouts", {})[layout] = {
        **entry,
        "baseLayout": base_layout,
        "baseVariant": base_variant,
        "rows": [list(row) for row in rows],
        "path": str(target),
    }
    favorites = [
        item for item in config.get("favorites", []) if str(item.get("layout", "")) != layout
    ]
    favorites.append(entry)
    config["favorites"] = favorites
    save_config(config, path)
    return {
        "ok": True,
        "layout": entry,
        "rows": [list(row) for row in rows],
        "path": str(target),
        "message": f"Saved {name.strip()} and added it to layouts.",
    }


def save_source_map(
    device: str,
    name: str,
    top: str,
    home: str,
    bottom: str,
    path: Path | None = None,
) -> dict[str, Any]:
    if not device or "]" in device or "\n" in device:
        raise OmakeydError("device-name", "Invalid keyboard identifier.")
    rows = (
        _split_row(top, "Top"),
        _split_row(home, "Home"),
        _split_row(bottom, "Bottom"),
    )
    mappings: dict[str, str] = {}
    emitted: set[str] = set()
    for codes, tokens in zip(ROW_CODES, rows):
        for physical_code, token in zip(codes, tokens):
            emitted_code = US_KEY_TO_CODE.get(normalize_key_name(token))
            if not emitted_code:
                raise OmakeydError(
                    "source-key",
                    f"Source maps must use QWERTY key names; {token!r} is unsupported.",
                )
            if emitted_code in emitted:
                raise OmakeydError(
                    "source-map-collision",
                    f"The source map emits {token!r} more than once.",
                )
            emitted.add(emitted_code)
            if physical_code != emitted_code:
                mappings[physical_code] = emitted_code
    config = load_config(path)
    device_config = config.setdefault("devices", {}).setdefault(device, {})
    device_config["source"] = {
        "kind": "manual",
        "name": name.strip() or "Custom source map",
        "alias": str(device_config.get("alias", "")),
        "brief": brief_for(name),
        "mappings": mappings,
    }
    save_config(config, path)
    return {
        "ok": True,
        "device": device,
        "name": device_config["source"]["name"],
        "rows": [list(row) for row in rows],
        "message": f"Saved the physical source map for {humanize_device(device)}.",
    }


def clear_source_map(device: str, path: Path | None = None) -> dict[str, Any]:
    config = load_config(path)
    device_config = config.setdefault("devices", {}).setdefault(device, {})
    device_config.pop("source", None)
    save_config(config, path)
    return {"ok": True, "device": device, "message": "Removed the manual source map."}


def restore_layouts(
    runner: Runner = default_runner,
    path: Path | None = None,
    keyd_dir: Path = Path("/etc/keyd"),
) -> dict[str, Any]:
    config = load_config(path)
    connected = {str(item.get("name", "")) for item in hypr_keyboards(runner)}
    restored: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for device, device_config in config.get("devices", {}).items():
        active = device_config.get("active", {}) if isinstance(device_config, dict) else {}
        if device not in connected or not isinstance(active, dict) or not active.get("layout"):
            continue
        try:
            result = apply_layout(
                device=device,
                layout=str(active["layout"]),
                variant=str(active.get("variant", "")),
                name=str(active.get("name", "")),
                brief=str(active.get("brief", "")),
                runner=runner,
                path=path,
                keyd_dir=keyd_dir,
                persist=True,
            )
            restored.append(result)
        except OmakeydError as error:
            errors.append({"device": device, "message": error.message})
    return {"ok": not errors, "restored": restored, "errors": errors}


def doctor(
    runner: Runner = default_runner,
    path: Path | None = None,
    keyd_dir: Path = Path("/etc/keyd"),
) -> dict[str, Any]:
    report = snapshot("", 12, runner, path, keyd_dir)
    report["checks"] = {
        "hyprland": True,
        "xkbCatalog": len(report.get("catalog", [])) > 0,
        "typingKeyboards": len(report.get("keyboards", [])),
        "blockedKeyboards": len(
            [keyboard for keyboard in report.get("keyboards", []) if not keyboard.get("canApply")]
        ),
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omakeyd")
    parser.add_argument("--version", action="version", version="Omakeyd 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Print panel state as JSON")
    snapshot_parser.add_argument("--query", default="")
    snapshot_parser.add_argument("--limit", type=int, default=60)

    catalog_parser = subparsers.add_parser("catalog", help="Search installed XKB layouts")
    catalog_parser.add_argument("--query", default="")
    catalog_parser.add_argument("--limit", type=int, default=60)

    select_parser = subparsers.add_parser("select-device", help="Select the panel target")
    select_parser.add_argument("--device", required=True)

    apply_parser = subparsers.add_parser("apply", help="Apply a layout to one keyboard")
    apply_parser.add_argument("--device", required=True)
    apply_parser.add_argument("--layout", required=True)
    apply_parser.add_argument("--variant", default="")
    apply_parser.add_argument("--name", default="")
    apply_parser.add_argument("--brief", default="")

    add_parser = subparsers.add_parser("favorite-add", help="Save a layout")
    add_parser.add_argument("--layout", required=True)
    add_parser.add_argument("--variant", default="")
    add_parser.add_argument("--name", default="")
    add_parser.add_argument("--brief", default="")
    add_parser.add_argument("--source", default="system")

    remove_parser = subparsers.add_parser("favorite-remove", help="Remove a saved layout")
    remove_parser.add_argument("--id", required=True)

    rows_parser = subparsers.add_parser("layout-rows", help="Print a layout's physical rows")
    rows_parser.add_argument("--layout", required=True)
    rows_parser.add_argument("--variant", default="")

    custom_parser = subparsers.add_parser("custom-save", help="Create or update a custom layout")
    custom_parser.add_argument("--name", required=True)
    custom_parser.add_argument("--brief", default="")
    custom_parser.add_argument("--base-layout", default="us")
    custom_parser.add_argument("--base-variant", default="")
    custom_parser.add_argument("--top", required=True)
    custom_parser.add_argument("--home", required=True)
    custom_parser.add_argument("--bottom", required=True)

    source_parser = subparsers.add_parser("source-save", help="Describe a firmware/source remap")
    source_parser.add_argument("--device", required=True)
    source_parser.add_argument("--name", required=True)
    source_parser.add_argument("--top", required=True)
    source_parser.add_argument("--home", required=True)
    source_parser.add_argument("--bottom", required=True)

    clear_parser = subparsers.add_parser("source-clear", help="Remove a manual source remap")
    clear_parser.add_argument("--device", required=True)

    subparsers.add_parser("restore", help="Reapply saved per-device layouts")
    subparsers.add_parser("doctor", help="Print diagnostics")
    return parser


def dispatch(args: argparse.Namespace, runner: Runner = default_runner) -> dict[str, Any]:
    if args.command == "snapshot":
        return snapshot(args.query, args.limit, runner)
    if args.command == "catalog":
        config = load_config()
        return {
            "ok": True,
            "catalog": search_catalog(full_catalog(config, runner), args.query, args.limit),
        }
    if args.command == "select-device":
        return select_device(args.device)
    if args.command == "apply":
        return apply_layout(args.device, args.layout, args.variant, args.name, args.brief, runner)
    if args.command == "favorite-add":
        return add_favorite(
            args.layout, args.variant, args.name, args.brief, args.source, runner
        )
    if args.command == "favorite-remove":
        return remove_favorite(args.id)
    if args.command == "layout-rows":
        return {"ok": True, "rows": primary_rows(args.layout, args.variant, runner)}
    if args.command == "custom-save":
        return save_custom_layout(
            args.name,
            args.brief,
            args.base_layout,
            args.base_variant,
            args.top,
            args.home,
            args.bottom,
            runner,
        )
    if args.command == "source-save":
        return save_source_map(args.device, args.name, args.top, args.home, args.bottom)
    if args.command == "source-clear":
        return clear_source_map(args.device)
    if args.command == "restore":
        return restore_layouts(runner)
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
