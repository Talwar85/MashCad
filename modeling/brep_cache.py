"""
MashCAD - BREP Cache

Caching-Schicht für häufig verwendete BREP-Operationen mit TNP-Awareness.

Author: Claude (OCP-First Migration Phase 7)
Date: 2026-02-10
"""

import hashlib
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from loguru import logger


@dataclass
class CacheEntry:
    """Cache Entry mit Metadaten."""
    result: Any  # BREP Result (Solid, Face, etc.)
    shape_id: str  # TNP ShapeID
    feature_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    hit_count: int = 0


class BREPCache:
    """
    Caching-Schicht für BREP-Operationen.

    Strategie:
    - Key basierend auf Operation und Input ShapeIDs
    - TNP ShapeIDs für Consistency
    - LRU Eviction Policy
    - TTL (Time To Live) optional
    """

    def __init__(self, max_size: int = 100, ttl_seconds: Optional[int] = None):
        """
        BREP Cache initialisieren.

        Args:
            max_size: Maximale Anzahl Cache Entries
            ttl_seconds: Optional TTL in Sekunden
        """
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds) if ttl_seconds else None
        self._cache: Dict[str, CacheEntry] = {}
        self._access_order: List[str] = []  # Für LRU

    def _generate_cache_key(self, operation: str, input_shape_ids: List[str], **kwargs) -> str:
        """
        Generiert eindeutigen Cache Key.

        Args:
            operation: Operationsname (z.B. "extrude", "fillet")
            input_shape_ids: Liste der Input ShapeIDs
            **kwargs: Additional Parameter (distance, radius, etc.)

        Returns:
            SHA256 Hash als Cache Key
        """
        # Key-Komponenten
        components = [operation] + input_shape_ids

        # Sortierte kwargs
        sorted_kwargs = sorted(kwargs.items())
        for key, value in sorted_kwargs:
            components.append(f"{key}={value}")

        # SHA256 Hash
        key_string = "|".join(str(c) for c in components)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get(self, operation: str, input_shape_ids: List[str], **kwargs) -> Optional[Any]:
        """
        Cached Result abrufen.

        Args:
            operation: Operationsname
            input_shape_ids: Liste der Input ShapeIDs
            **kwargs: Additional Parameter

        Returns:
            Cached result oder None wenn nicht gefunden oder expired
        """
        key = self._generate_cache_key(operation, input_shape_ids, **kwargs)

        if key not in self._cache:
            return None

        entry = self._cache[key]

        # TTL Check
        if self.ttl and (datetime.now() - entry.timestamp) > self.ttl:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
            return None

        # Hit Count erhöhen
        entry.hit_count += 1

        # LRU Update
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        if is_enabled("tnp_debug_logging"):
            logger.debug(f"Cache HIT: {operation} (hits: {entry.hit_count})")
        return entry.result

    def put(self, operation: str, input_shape_ids: List[str], result: Any,
            feature_id: str, **kwargs) -> None:
        """
        Result in Cache speichern.

        Args:
            operation: Operationsname
            input_shape_ids: Liste der Input ShapeIDs
            result: BREP Result (Solid, Face, etc.)
            feature_id: Feature ID für TNP
            **kwargs: Additional Parameter
        """
        key = self._generate_cache_key(operation, input_shape_ids, **kwargs)

        # ShapeID von Result extrahieren (TNP)
        shape_id = self._extract_shape_id(result)

        # Cache Entry erstellen
        entry = CacheEntry(
            result=result,
            shape_id=shape_id,
            feature_id=feature_id,
            timestamp=datetime.now()
        )

        # Eviction wenn voll
        if len(self._cache) >= self.max_size:
            self._evict_lru()

        # Speichern
        self._cache[key] = entry
        self._access_order.append(key)

        if is_enabled("tnp_debug_logging"):
            logger.debug(f"Cache PUT: {operation} (cache size: {len(self._cache)})")

    def _evict_lru(self) -> None:
        """Least Recently Used Entry entfernen."""
        if self._access_order:
            lru_key = self._access_order.pop(0)
            del self._cache[lru_key]
            logger.debug(f"Cache EVICT: {lru_key}")

    def _extract_shape_id(self, result: Any) -> str:
        """
        Extrahiert ShapeID aus Result (TNP v4.1).

        Args:
            result: BREP Result

        Returns:
            ShapeID als String
        """
        # TNP Integration: ShapeID aus Result holen
        if hasattr(result, 'shape_id'):
            return result.shape_id
        elif hasattr(result, 'wrapped'):
            # OCP Shape Hash
            return hashlib.sha256(str(result.wrapped).encode()).hexdigest()
        else:
            return f"unknown_{id(result)}"

    def clear(self) -> None:
        """Cache leeren."""
        self._cache.clear()
        self._access_order.clear()
        logger.info("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """
        Cache Statistiken.

        Returns:
            Dict mit size, max_size, total_hits, avg_hits, top_entries
        """
        total_hits = sum(entry.hit_count for entry in self._cache.values())
        avg_hits = total_hits / len(self._cache) if self._cache else 0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "total_hits": total_hits,
            "avg_hits": avg_hits,
            "entries": [
                {
                    "feature_id": entry.feature_id,
                    "shape_id": entry.shape_id,
                    "hits": entry.hit_count,
                    "age_seconds": (datetime.now() - entry.timestamp).total_seconds()
                }
                for entry in sorted(self._cache.values(), key=lambda e: e.hit_count, reverse=True)[:10]
            ]
        }

    def invalidate_by_feature(self, feature_id: str) -> int:
        """
        Invalidiert alle Cache Entries für ein Feature.

        Args:
            feature_id: Feature ID

        Returns:
            Anzahl der gelöschten Entries
        """
        keys_to_delete = [
            key for key, entry in self._cache.items()
            if entry.feature_id == feature_id
        ]

        for key in keys_to_delete:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)

        if keys_to_delete:
            logger.info(f"Invalidated {len(keys_to_delete)} cache entries for feature {feature_id}")

        return len(keys_to_delete)

    def invalidate_by_shape_id(self, shape_id: str) -> int:
        """
        Invalidiert alle Cache Entries die eine ShapeID referenzieren.

        Args:
            shape_id: Shape ID

        Returns:
            Anzahl der gelöschten Entries
        """
        keys_to_delete = [
            key for key, entry in self._cache.items()
            if entry.shape_id == shape_id or
               any(inp_id == shape_id for inp_id in
                   self._extract_input_shape_ids_from_key(key))
        ]

        for key in keys_to_delete:
            del self._cache[key]
            if key in self._access_order:
                self._access_order.remove(key)

        return len(keys_to_delete)

    def _extract_input_shape_ids_from_key(self, key: str) -> List[str]:
        """Extrahiert Input ShapeIDs aus einem Cache Key (für Invalidation)."""
        # Der Key ist ein Hash, aber wir können die Operation nicht rekonstruieren
        # Diese Methode ist ein Platzhalter für zukünftige Implementation
        return []


# Global Cache Instance
_global_cache: Optional[BREPCache] = None


def get_global_cache() -> BREPCache:
    """
    Gibt globale Cache Instance zurück.

    Returns:
        Singleton BREPCache Instance
    """
    global _global_cache
    if _global_cache is None:
        # Default: 100 Entries, 1 Stunde TTL
        _global_cache = BREPCache(max_size=100, ttl_seconds=3600)
    return _global_cache


def clear_global_cache() -> None:
    """Leert den globalen Cache."""
    global _global_cache
    if _global_cache is not None:
        _global_cache.clear()


# Import für is_enabled
from config.feature_flags import is_enabled
