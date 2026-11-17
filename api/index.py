"""Vercel entrypoint. Vercel runs this file as a Python serverless function; all routes
are rewritten here by vercel.json, except /static/* which the CDN serves from public/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fichua.main import app  # noqa: E402,F401
