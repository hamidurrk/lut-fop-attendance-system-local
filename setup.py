from __future__ import annotations

from pathlib import Path
from setuptools import find_packages, setup

BASE_DIR = Path(__file__).parent
README = (BASE_DIR / "readme.md").read_text(encoding="utf-8") if (BASE_DIR / "readme.md").exists() else ""

setup(
    name="lut-fop-attendance-system",
    version="0.1.0",
    description="Cross-platform attendance management system built with CustomTkinter.",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Hamidur",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "customtkinter>=5.2.0",
        "opencv-python>=4.8.0",
        "pyzbar>=0.1.9",
        "Pillow>=10.0.0",
        "selenium>=4.13.0",
        "python-dotenv>=1.0.0",
        "requests>=2.31.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pyinstaller>=5.13.0",
        ]
    },
    entry_points={
        "gui_scripts": [
            "attendance-app=attendance_app.main:main",
        ]
    },
)
