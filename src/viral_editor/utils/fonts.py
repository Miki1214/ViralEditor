"""Font family registry and resolution for drawtext rendering."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"

# family label -> ordered candidate filenames (bundled assets, then system)
FONT_REGISTRY: dict[str, list[str]] = {
    "Montserrat Black": ["Montserrat-Black.ttf", "arialbd.ttf", "arial.ttf"],
    "Impact": ["impact.ttf"],
    "Arial Black": ["ariblk.ttf", "arialbd.ttf"],
    "Bebas Neue": ["BebasNeue-Regular.ttf", "impact.ttf"],
    "Anton": ["Anton-Regular.ttf", "impact.ttf"],
    "Oswald": ["Oswald-Bold.ttf", "arialbd.ttf"],
    "Barlow Condensed Black": ["BarlowCondensed-Black.ttf", "arialbd.ttf"],
    "Helvetica Neue": ["Helvetica Neue Bold.ttf", "segoeuib.ttf", "arialbd.ttf"],
}

DEFAULT_FONT_FAMILY = "Montserrat Black"


def _system_font_dirs() -> list[Path]:
    dirs: list[Path] = []
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        dirs.append(windir / "Fonts")
    elif sys.platform == "darwin":
        dirs.extend(
            [
                Path("/System/Library/Fonts/Supplemental"),
                Path("/Library/Fonts"),
            ]
        )
    else:
        dirs.extend(
            [
                Path("/usr/share/fonts/truetype/dejavu"),
                Path("/usr/share/fonts/TTF"),
                Path("/usr/share/fonts/truetype/liberation"),
            ]
        )
    return dirs


def resolve_font_path(family: str) -> Path | None:
    """Resolve a font family label to an existing TTF/OTF path."""
    candidates = FONT_REGISTRY.get(family, FONT_REGISTRY[DEFAULT_FONT_FAMILY])
    search_roots = [_ASSETS_DIR, *_system_font_dirs()]

    for filename in candidates:
        for root in search_roots:
            path = root / filename
            if path.is_file():
                return path.resolve()

    # Case-insensitive scan on Windows font dir
    if sys.platform == "win32":
        fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        if fonts_dir.is_dir():
            lower_map = {entry.name.lower(): entry for entry in fonts_dir.iterdir()}
            for filename in candidates:
                hit = lower_map.get(filename.lower())
                if hit is not None and hit.is_file():
                    return hit.resolve()

    return None


def resolve_font_for_ffmpeg(family: str) -> str | None:
    """Return an ffmpeg-safe escaped fontfile path."""
    from viral_editor.utils.ffmpeg import escape_filter_path

    path = resolve_font_path(family)
    if path is None:
        return None
    return escape_filter_path(path)
