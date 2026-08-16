"""
Vercel entrypoint. @vercel/python detects the module-level `app` WSGI
callable here and routes all matched requests to it - see vercel.json.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402,F401
