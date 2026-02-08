"""
Oracle Trader v2.0 — Local Storage
====================================

Cache local e backup offline quando Supabase falha.
"""

import json
from pathlib import Path
from typing import List


class LocalStorage:
    """Gestão de arquivos locais para cache e backup."""

    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or Path.cwd()
        self.pending_file = self.base_dir / "pending_uploads.json"
        self.cache_dir = self.base_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)

    def save_pending(self, data: List[dict]):
        """Salva dados pendentes de upload."""
        existing = self.load_pending()
        existing.extend(data)
        with open(self.pending_file, "w") as f:
            json.dump(existing, f, indent=2)

    def load_pending(self) -> List[dict]:
        """Carrega dados pendentes de upload."""
        if not self.pending_file.exists():
            return []
        try:
            with open(self.pending_file, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def clear_pending(self):
        """Limpa dados pendentes após upload."""
        if self.pending_file.exists():
            self.pending_file.unlink()

    def cache_bars(self, symbol: str, bars: List[dict]):
        """Cache de barras OHLCV."""
        cache_file = self.cache_dir / f"{symbol}_bars.json"
        with open(cache_file, "w") as f:
            json.dump(bars, f)

    def load_cached_bars(self, symbol: str) -> List[dict]:
        """Carrega barras do cache."""
        cache_file = self.cache_dir / f"{symbol}_bars.json"
        if not cache_file.exists():
            return []
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except Exception:
            return []
