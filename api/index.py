"""Vercel serverless entry point for the AICTE Flow API.

All /api/* paths are routed here by vercel.json. Persistent state is stored in
PostgreSQL through DATABASE_URL / POSTGRES_URL, never in the function's disk.
"""
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys
import threading
import os

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402

_init_lock = threading.Lock()
_initialized = False


class handler(server.Handler):
    def _prepare(self):
        global _initialized
        if not (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")):
            self.reply(
                503,
                {
                    "error": "Persistent database not configured. Add DATABASE_URL in Vercel Project Settings, then redeploy. See README.md."
                },
            )
            return False
        if not _initialized:
            with _init_lock:
                if not _initialized:
                    try:
                        server.initialise()
                    except Exception:
                        self.reply(
                            503,
                            {
                                "error": "Database initialization failed. Verify DATABASE_URL and confirm the database is reachable."
                            },
                        )
                        return False
                    _initialized = True
        return True

    def do_GET(self):
        if self._prepare():
            super().do_GET()

    def do_POST(self):
        if self._prepare():
            super().do_POST()
