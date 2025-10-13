from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

DEFAULT_APP_NAME = os.getenv("APP_NAME", "Queue - LUT FoP Attendance System")
DOCUMENTS_PATH = Path(os.path.expanduser("~")) / "Documents"
DEFAULT_POINTER_DIR = DOCUMENTS_PATH / DEFAULT_APP_NAME
DEFAULT_SETTINGS_FILENAME = "user_settings.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
	"default_attendance_points": 5,
	"default_bonus_points": 2,
	"chrome_binary_path": None,
	"app_data_dir": str(DEFAULT_POINTER_DIR),
}


@dataclass
class UserSettingsStore:
	"""Load and persist user-configurable settings in a JSON file."""

	pointer_dir: Path = field(default_factory=lambda: DEFAULT_POINTER_DIR)
	settings_filename: str = DEFAULT_SETTINGS_FILENAME
	_data: Dict[str, Any] = field(init=False, default_factory=dict)
	app_data_dir: Path = field(init=False)
	settings_file: Path = field(init=False)

	def __post_init__(self) -> None:
		self.pointer_dir.mkdir(parents=True, exist_ok=True)
		self.reload()

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------
	@property
	def data(self) -> Dict[str, Any]:
		return dict(self._data)

	def get(self, key: str, default: Any = None) -> Any:
		return self._data.get(key, default)

	def reload(self) -> None:
		pointer_path = self.pointer_dir / self.settings_filename
		pointer_data = self._load_json(pointer_path)

		app_data_raw = pointer_data.get("app_data_dir") or DEFAULT_SETTINGS["app_data_dir"]
		self.app_data_dir = Path(app_data_raw).expanduser()
		self.app_data_dir.mkdir(parents=True, exist_ok=True)

		self.settings_file = self.app_data_dir / self.settings_filename
		file_data = self._load_json(self.settings_file)

		combined = dict(DEFAULT_SETTINGS)
		combined.update(pointer_data)
		combined.update(file_data)

		chrome_path = combined.get("chrome_binary_path")
		if chrome_path:
			combined["chrome_binary_path"] = str(Path(chrome_path).expanduser())

		combined["app_data_dir"] = str(self.app_data_dir)
		self._data = combined

	def update(self, **kwargs: Any) -> Dict[str, Any]:
		new_data = dict(self._data)
		app_data_dir_changed = False

		if "app_data_dir" in kwargs and kwargs["app_data_dir"]:
			new_dir = Path(kwargs.pop("app_data_dir")).expanduser()
			if new_dir != self.app_data_dir:
				app_data_dir_changed = True
				new_data["app_data_dir"] = str(new_dir)
			else:
				new_data["app_data_dir"] = str(self.app_data_dir)

		for key, value in kwargs.items():
			if key in DEFAULT_SETTINGS:
				new_data[key] = value

		self._data = new_data

		if app_data_dir_changed:
			self.app_data_dir = Path(self._data["app_data_dir"]).expanduser()
			self.app_data_dir.mkdir(parents=True, exist_ok=True)
			self.settings_file = self.app_data_dir / self.settings_filename

		self._persist()
		return dict(self._data)

	# ------------------------------------------------------------------
	# Internal helpers
	# ------------------------------------------------------------------
	def _persist(self) -> None:
		pointer_path = self.pointer_dir / self.settings_filename
		pointer_payload = dict(self._data)

		with pointer_path.open("w", encoding="utf-8") as handle:
			json.dump(pointer_payload, handle, indent=2)

		with self.settings_file.open("w", encoding="utf-8") as handle:
			json.dump(self._data, handle, indent=2)

	@staticmethod
	def _load_json(path: Path) -> Dict[str, Any]:
		try:
			if path.exists():
				with path.open("r", encoding="utf-8") as handle:
					return json.load(handle)
		except Exception:
			pass
		return {}
