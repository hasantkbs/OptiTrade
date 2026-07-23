"""
OptiTrade — Basit TTL Tabanlı Bellek-İçi Cache Yöneticisi
============================================================
``core/news_analyzer.py`` ve ``core/sector_intelligence.py``'de zaten
kullanılan "modül-seviyesi dict + zaman damgası" örüntüsünü genel amaçlı,
yeniden kullanılabilir, thread-safe tek bir sınıfa taşır. Kalıcı bir
depolama katmanı yoktur (Redis/SQLite değil) — süreç yeniden başladığında
cache sıfırlanır; bu, tek-process çalışan bu projenin ihtiyacı için yeterli.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Generic, Optional, Tuple, TypeVar

V = TypeVar("V")


class TTLCache(Generic[V]):
    """Belirli bir süre (TTL) boyunca geçerli, bellek-içi, thread-safe anahtar-değer cache.

    Süresi dolmuş bir girdiye ``get()`` çağrısı ``None`` döner ve girdiyi
    cache'ten siler; çağıran taraf değeri yeniden hesaplayıp ``set()`` ile
    tekrar yazmalıdır.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: Dict[str, Tuple[float, V]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[V]:
        """Anahtar geçerliyse (TTL dolmamışsa) değeri döner; aksi halde None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            cached_at, value = entry
            if time.time() - cached_at >= self._ttl_seconds:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: V) -> None:
        """Değeri şu anki zaman damgasıyla cache'e yazar."""
        with self._lock:
            self._store[key] = (time.time(), value)

    def invalidate(self, key: str) -> None:
        """Belirli bir anahtarı cache'ten zorla siler."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Tüm cache içeriğini temizler."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
