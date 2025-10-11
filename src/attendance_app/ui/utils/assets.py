from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import customtkinter as ctk
from PIL import Image


@lru_cache(maxsize=1)
def _assets_root() -> Path | None:
    base_path = Path(__file__).resolve()
    for parent in base_path.parents:
        candidate = parent / "assets"
        if candidate.exists():
            return candidate
    return None


def load_icon_image(filename: str, size: tuple[int, int]) -> tuple[Image.Image | None, ctk.CTkImage | None]:
    assets_dir = _assets_root()
    if assets_dir is None:
        return None, None

    image_path = assets_dir / filename
    if not image_path.exists():
        return None, None

    try:
        with Image.open(image_path) as img:
            pil_image = img.convert("RGBA")
    except Exception:
        return None, None

    tk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=size)
    return pil_image, tk_image


def get_asset_path(filename: str) -> Path | None:
    assets_dir = _assets_root()
    if assets_dir is None:
        return None

    image_path = assets_dir / filename
    if not image_path.exists():
        return None
    return image_path
