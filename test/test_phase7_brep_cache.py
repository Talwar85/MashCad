"""
Phase 7: BREP Cache Integration Tests

Tests für BREP Cache System mit LRU Eviction und TTL.

Author: Claude (OCP-First Migration Phase 7)
Date: 2026-02-10
"""

import pytest
import time
from loguru import logger

from modeling.brep_cache import BREPCache, get_global_cache, clear_global_cache, CacheEntry


# ============================================================================
# BASIC CACHE OPERATIONS TESTS
# ============================================================================

class TestCacheBasicOperations:
    """Tests für grundlegende Cache Operationen."""

    def test_cache_put_get(self):
        """Test grundlegende Cache Operationen."""
        cache = BREPCache(max_size=10)

        # Put
        cache.put("test_op", ["shape1"], "result1", "feature1", param1=10)

        # Get
        result = cache.get("test_op", ["shape1"], param1=10)
        assert result == "result1"

        # Get miss
        result = cache.get("test_op", ["shape2"], param1=10)
        assert result is None

    def test_cache_different_params(self):
        """Test dass verschiedene Parameter verschiedene Keys erzeugen."""
        cache = BREPCache(max_size=10)

        # Gleiche Operation, verschiedene Parameter
        cache.put("extrude", ["shape1"], "result1", "feature1", distance=5.0)
        cache.put("extrude", ["shape1"], "result2", "feature1", distance=10.0)

        # Beide sollten unabhängig voneinander abrufbar sein
        assert cache.get("extrude", ["shape1"], distance=5.0) == "result1"
        assert cache.get("extrude", ["shape1"], distance=10.0) == "result2"

    def test_cache_different_operations(self):
        """Test dass verschiedene Operationen unterschiedliche Results cachen."""
        cache = BREPCache(max_size=10)

        cache.put("extrude", ["shape1"], "extrude_result", "feature1")
        cache.put("fillet", ["shape1"], "fillet_result", "feature1")

        assert cache.get("extrude", ["shape1"]) == "extrude_result"
        assert cache.get("fillet", ["shape1"]) == "fillet_result"

    def test_cache_hit_count(self):
        """Test dass Hit Count erhöht wird."""
        cache = BREPCache(max_size=10)

        cache.put("test_op", ["shape1"], "result1", "feature1")

        # Erster Zugriff
        result = cache.get("test_op", ["shape1"])
        assert result == "result1"

        stats = cache.get_stats()
        assert stats["total_hits"] == 1

        # Zweiter Zugriff
        result = cache.get("test_op", ["shape1"])
        assert result == "result1"

        stats = cache.get_stats()
        assert stats["total_hits"] == 2


# ============================================================================
# LRU EVICTION TESTS
# ============================================================================

class TestCacheLRUEviction:
    """Tests für LRU Eviction Policy."""

    def test_cache_lru_eviction(self):
        """Test LRU Eviction Policy."""
        cache = BREPCache(max_size=3)

        # 3 Entries
        cache.put("op1", ["s1"], "r1", "f1")
        cache.put("op2", ["s2"], "r2", "f2")
        cache.put("op3", ["s3"], "r3", "f3")

        # Alle da
        assert cache.get("op1", ["s1"]) == "r1"
        assert cache.get("op2", ["s2"]) == "r2"
        assert cache.get("op3", ["s3"]) == "r3"

        # op1 accessed -> wird neuer als op2 und op3
        cache.get("op1", ["s1"])

        # 4. Entry sollte op2 evicten (jetzt LRU nach dem op1 access)
        cache.put("op4", ["s4"], "r4", "f4")

        # op2 sollte weg sein (war LRU - wurde nie accessed nach dem Put)
        assert cache.get("op2", ["s2"]) is None

        # op1, op3, op4 sollten noch da sein
        assert cache.get("op1", ["s1"]) == "r1"
        assert cache.get("op3", ["s3"]) == "r3"
        assert cache.get("op4", ["s4"]) == "r4"

    def test_cache_lru_order(self):
        """Test dass LRU Reihenfolge korrekt ist."""
        cache = BREPCache(max_size=3)

        cache.put("op1", ["s1"], "r1", "f1")
        cache.put("op2", ["s2"], "r2", "f2")

        # op1 accessed -> wird neuer als op2
        cache.get("op1", ["s1"])

        cache.put("op3", ["s3"], "r3", "f3")

        # op2 ist jetzt LRU (wurde nie accessed)
        cache.put("op4", ["s4"], "r4", "f4")

        assert cache.get("op2", ["s2"]) is None  # LRU evicted
        assert cache.get("op1", ["s1"]) == "r1"  # Wurde accessed
        assert cache.get("op3", ["s3"]) == "r3"
        assert cache.get("op4", ["s4"]) == "r4"


# ============================================================================
# TTL TESTS
# ============================================================================

class TestCacheTTL:
    """Tests für Time-To-Live (TTL) Funktionalität."""

    def test_cache_ttl_expiration(self):
        """Test dass Entries nach TTL expiren."""
        # Kurz TTL für Test
        cache = BREPCache(max_size=10, ttl_seconds=1)

        cache.put("test_op", ["shape1"], "result1", "feature1")

        # Sofort verfügbar
        assert cache.get("test_op", ["shape1"]) == "result1"

        # Warten bis TTL abläuft
        time.sleep(1.5)

        # Sollte expired sein
        assert cache.get("test_op", ["shape1"]) is None

    def test_cache_ttl_refresh_on_access(self):
        """Test dass Zugriff TTL nicht refresht (standard behavior)."""
        cache = BREPCache(max_size=10, ttl_seconds=2)

        cache.put("test_op", ["shape1"], "result1", "feature1")

        # Nach 1 Sekunde noch da
        time.sleep(1)
        assert cache.get("test_op", ["shape1"]) == "result1"

        # Nach weiterer 1.5 Sekunde insgesamt 2.5 - sollte expired sein
        time.sleep(1.5)
        assert cache.get("test_op", ["shape1"]) is None


# ============================================================================
# CACHE INVALIDATION TESTS
# ============================================================================

class TestCacheInvalidation:
    """Tests für Cache Invalidation."""

    def test_clear_cache(self):
        """Test dass clear() alle Entries entfernt."""
        cache = BREPCache(max_size=10)

        cache.put("op1", ["s1"], "r1", "f1")
        cache.put("op2", ["s2"], "r2", "f2")

        assert cache.get_stats()["size"] == 2

        cache.clear()

        assert cache.get_stats()["size"] == 0
        assert cache.get("op1", ["s1"]) is None
        assert cache.get("op2", ["s2"]) is None

    def test_invalidate_by_feature(self):
        """Test Invalidation by Feature ID."""
        cache = BREPCache(max_size=10)

        cache.put("op1", ["s1"], "r1", "feature_a")
        cache.put("op2", ["s2"], "r2", "feature_a")
        cache.put("op3", ["s3"], "r3", "feature_b")

        assert cache.get_stats()["size"] == 3

        # Alle feature_a Entries invalidieren
        count = cache.invalidate_by_feature("feature_a")

        assert count == 2
        assert cache.get_stats()["size"] == 1
        assert cache.get("op1", ["s1"]) is None
        assert cache.get("op2", ["s2"]) is None
        assert cache.get("op3", ["s3"]) == "r3"


# ============================================================================
# CACHE STATS TESTS
# ============================================================================

class TestCacheStats:
    """Tests für Cache Statistiken."""

    def test_cache_stats(self):
        """Test Cache Statistiken."""
        cache = BREPCache(max_size=10)

        cache.put("op1", ["s1"], "r1", "f1")
        cache.put("op2", ["s2"], "r2", "f2")

        stats = cache.get_stats()

        assert stats["size"] == 2
        assert stats["max_size"] == 10
        assert stats["total_hits"] == 0
        assert stats["avg_hits"] == 0

        # Einige Hits erzeugen
        cache.get("op1", ["s1"])
        cache.get("op1", ["s1"])
        cache.get("op2", ["s2"])

        stats = cache.get_stats()
        assert stats["total_hits"] == 3
        assert stats["avg_hits"] == 1.5

    def test_cache_stats_entries(self):
        """Test dass Stats Entries korrekt sind."""
        cache = BREPCache(max_size=10)

        cache.put("op1", ["s1"], "r1", "feature_1")
        cache.put("op2", ["s2"], "r2", "feature_2")

        # Hits erzeugen
        cache.get("op1", ["s1"])
        cache.get("op1", ["s1"])
        cache.get("op2", ["s2"])

        stats = cache.get_stats()

        assert len(stats["entries"]) <= 10  # Max top 10
        assert any(e["feature_id"] == "feature_1" and e["hits"] == 2 for e in stats["entries"])
        assert any(e["feature_id"] == "feature_2" and e["hits"] == 1 for e in stats["entries"])


# ============================================================================
# GLOBAL CACHE TESTS
# ============================================================================

class TestGlobalCache:
    """Tests für globalen Cache."""

    def test_get_global_cache_singleton(self):
        """Test dass get_global_cache() Singleton zurückgibt."""
        clear_global_cache()

        cache1 = get_global_cache()
        cache2 = get_global_cache()

        assert cache1 is cache2

    def test_clear_global_cache(self):
        """Test dass clear_global_cache() funktioniert."""
        cache = get_global_cache()
        cache.put("test_op", ["s1"], "result1", "feature1")

        assert cache.get_stats()["size"] > 0

        clear_global_cache()

        # Neuer Cache sollte leer sein
        cache = get_global_cache()
        assert cache.get_stats()["size"] == 0


# ============================================================================
# SHAPE ID EXTRACTION TESTS
# ============================================================================

class TestShapeIDExtraction:
    """Tests für ShapeID Extraktion."""

    def test_extract_shape_id_from_dict(self):
        """Test Extraktion aus Objekt mit shape_id Attribut."""
        cache = BREPCache(max_size=10)

        class MockResult:
            def __init__(self, shape_id):
                self.shape_id = shape_id

        result = MockResult("test_shape_123")
        shape_id = cache._extract_shape_id(result)

        assert shape_id == "test_shape_123"

    def test_extract_shape_id_from_ocp(self):
        """Test Extraktion aus OCP Shape mit wrapped Attribut."""
        cache = BREPCache(max_size=10)

        class MockShape:
            def __init__(self):
                self.wrapped = "mock_ocp_shape"

        result = MockShape()
        shape_id = cache._extract_shape_id(result)

        # Sollte ein Hash sein
        assert isinstance(shape_id, str)
        assert len(shape_id) == 64  # SHA256 = 64 hex chars

    def test_extract_shape_id_unknown(self):
        """Test Extraktion aus unbekanntem Objekt."""
        cache = BREPCache(max_size=10)

        shape_id = cache._extract_shape_id("just_a_string")

        assert shape_id.startswith("unknown_")


# ============================================================================
# CACHE KEY GENERATION TESTS
# ============================================================================

class TestCacheKeyGeneration:
    """Tests für Cache Key Generierung."""

    def test_different_operations_different_keys(self):
        """Test dass verschiedene Operationen verschiedene Keys erzeugen."""
        cache = BREPCache(max_size=10)

        key1 = cache._generate_cache_key("op1", ["s1"], param=1)
        key2 = cache._generate_cache_key("op2", ["s1"], param=1)

        assert key1 != key2

    def test_different_shape_ids_different_keys(self):
        """Test dass verschiedene ShapeIDs verschiedene Keys erzeugen."""
        cache = BREPCache(max_size=10)

        key1 = cache._generate_cache_key("op1", ["s1"], param=1)
        key2 = cache._generate_cache_key("op1", ["s2"], param=1)

        assert key1 != key2

    def test_different_params_different_keys(self):
        """Test dass verschiedene Parameter verschiedene Keys erzeugen."""
        cache = BREPCache(max_size=10)

        key1 = cache._generate_cache_key("op1", ["s1"], distance=5.0)
        key2 = cache._generate_cache_key("op1", ["s1"], distance=10.0)

        assert key1 != key2

    def test_same_inputs_same_key(self):
        """Test dass gleiche Inputs gleichen Key erzeugen (unabhängig von kwargs order)."""
        cache = BREPCache(max_size=10)

        key1 = cache._generate_cache_key("op1", ["s1"], distance=5.0, angle=90)
        key2 = cache._generate_cache_key("op1", ["s1"], angle=90, distance=5.0)

        assert key1 == key2


# ============================================================================
# FEATURE FLAG TESTS
# ============================================================================

class TestFeatureFlags:
    """Tests für Feature Flags."""

    def test_ocp_brep_cache_flag_exists(self):
        """Test dass ocp_brep_cache Flag existiert."""
        from config.feature_flags import is_enabled

        # Flag sollte existieren (kann True oder False sein)
        result = is_enabled("ocp_brep_cache")
        assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
