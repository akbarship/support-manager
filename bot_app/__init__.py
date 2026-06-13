"""Aiogram implementation of Support Manager."""

from __future__ import annotations

import site
from pathlib import Path

site.addsitedir(str(Path(__file__).resolve().parent.parent / ".python_deps"))
