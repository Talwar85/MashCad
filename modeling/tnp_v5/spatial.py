"""
TNP v5.0 - Spatial Index

R-tree based spatial index for fast geometric queries.
Enables O(log n) lookup of shapes by proximity.

Performance optimizations:
- LRU cache for nearest neighbor queries
- Batch query support
- Performance statistics tracking
"""

import numpy as np
from typing import List, Tuple, Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from loguru import logger
from functools import lru_cache
from collections import deque
import time

try:
    from rtree import index
    HAS_RTREE = True
except ImportError:
    HAS_RTREE = False
    logger.warning("rtree package not available. Spatial index will be disabled.")


@dataclass
class SpatialIndexStats:
    """Performance statistics for spatial index operations."""
    query_count: int = 0
    nearest_count: int = 0
    batch_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_query_time_ms: float = 0.0
    total_nearest_time_ms: float = 0.0

    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total

    def avg_query_time_ms(self) -> float:
        """Calculate average query time in milliseconds."""
        if self.query_count == 0:
            return 0.0
        return self.total_query_time_ms / self.query_count

    def avg_nearest_time_ms(self) -> float:
        """Calculate average nearest query time in milliseconds."""
        if self.nearest_count == 0:
            return 0.0
        return self.total_nearest_time_ms / self.nearest_count


class QueryCache:
    """
    LRU cache for spatial queries.

    Caches results from nearest() queries to avoid repeated calculations
    for the same query point and parameters.
    """

    def __init__(self, max_size: int = 256):
        """
        Initialize the query cache.

        Args:
            max_size: Maximum number of cached queries
        """
        self._max_size = max_size
        self._cache: Dict[str, Tuple[List[str], float]] = {}
        self._access_order: deque = deque()
        self._hits = 0
        self._misses = 0

    def _make_key(
        self,
        point: Tuple[float, float, float],
        max_results: int,
        shape_type: Optional[str]
    ) -> str:
        """Create a cache key from query parameters."""
        type_part = shape_type or "None"
        return f"{point}:{max_results}:{type_part}"

    def get(
        self,
        point: Tuple[float, float, float],
        max_results: int,
        shape_type: Optional[str]
    ) -> Optional[List[str]]:
        """
        Get cached query result.

        Args:
            point: Query point
            max_results: Maximum results
            shape_type: Optional shape type filter

        Returns:
            Cached result or None if not found
        """
        key = self._make_key(point, max_results, shape_type)

        if key in self._cache:
            self._hits += 1
            # Move to end of access order (most recently used)
            try:
                self._access_order.remove(key)
            except ValueError:
                pass
            self._access_order.append(key)
            return self._cache[key][0]

        self._misses += 1
        return None

    def put(
        self,
        point: Tuple[float, float, float],
        max_results: int,
        shape_type: Optional[str],
        result: List[str]
    ) -> None:
        """
        Store query result in cache.

        Args:
            point: Query point
            max_results: Maximum results
            shape_type: Optional shape type filter
            result: Query result to cache
        """
        key = self._make_key(point, max_results, shape_type)

        # Evict oldest if at capacity
        if len(self._cache) >= self._max_size and key not in self._cache:
            oldest = self._access_order.popleft()
            del self._cache[oldest]

        self._cache[key] = (result, time.perf_counter())
        self._access_order.append(key)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._access_order.clear()
        self._hits = 0
        self._misses = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total


@dataclass
class Bounds:
    """
    3D bounding box for spatial indexing.

    Attributes:
        min_x, min_y, min_z: Minimum coordinates
        max_x, max_y, max_z: Maximum coordinates
    """
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def __iter__(self):
        """Iterate bounds as tuple for rtree."""
        return iter((self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z))

    def to_tuple(self) -> Tuple[float, float, float, float, float, float]:
        """Convert to tuple format."""
        return (self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z)

    @classmethod
    def from_center(cls, center: Tuple[float, float, float], size: float) -> 'Bounds':
        """
        Create bounds from center point and size.

        Args:
            center: (x, y, z) center coordinates
            size: Half-size of the bounding box

        Returns:
            Bounds centered at the point
        """
        x, y, z = center
        return cls(
            min_x=x - size,
            min_y=y - size,
            min_z=z - size,
            max_x=x + size,
            max_y=y + size,
            max_z=z + size
        )

    @classmethod
    def from_points(cls, points: List[Tuple[float, float, float]]) -> 'Bounds':
        """
        Create bounds from a list of points.

        Args:
            points: List of (x, y, z) coordinates

        Returns:
            Bounds enclosing all points
        """
        if not points:
            return cls(0, 0, 0, 0, 0, 0)

        arr = np.array(points)
        min_vals = arr.min(axis=0)
        max_vals = arr.max(axis=0)

        return cls(
            min_x=float(min_vals[0]),
            min_y=float(min_vals[1]),
            min_z=float(min_vals[2]),
            max_x=float(max_vals[0]),
            max_y=float(max_vals[1]),
            max_z=float(max_vals[2])
        )

    def contains(self, point: Tuple[float, float, float]) -> bool:
        """Check if a point is inside the bounds."""
        x, y, z = point
        return (self.min_x <= x <= self.max_x and
                self.min_y <= y <= self.max_y and
                self.min_z <= z <= self.max_z)

    def center(self) -> Tuple[float, float, float]:
        """Get the center of the bounds."""
        return (
            (self.min_x + self.max_x) / 2,
            (self.min_y + self.max_y) / 2,
            (self.min_z + self.max_z) / 2
        )

    def distance_to(self, point: Tuple[float, float, float]) -> float:
        """
        Calculate minimum distance from point to bounds.

        Returns 0 if point is inside bounds.
        """
        x, y, z = point

        # Check if point is inside
        if self.contains(point):
            return 0.0

        # Distance to closest point on bounds
        dx = max(self.min_x - x, 0, x - self.max_x)
        dy = max(self.min_y - y, 0, y - self.max_y)
        dz = max(self.min_z - z, 0, z - self.max_z)

        return np.sqrt(dx*dx + dy*dy + dz*dz)


class SpatialIndex:
    """
    R-tree based spatial index for fast geometric queries.

    Enables O(log n) lookup of shapes by proximity.
    Falls back to linear search if rtree is not available.

    Performance Features:
    - LRU cache for nearest neighbor queries
    - Batch query support for multiple points
    - Performance statistics tracking
    """

    def __init__(self, enable_cache: bool = True, cache_size: int = 256):
        """
        Initialize the spatial index.

        Args:
            enable_cache: Enable LRU cache for nearest queries
            cache_size: Maximum cache size
        """
        self._bounds: Dict[str, Bounds] = {}
        self._shapes: Dict[str, Dict[str, Any]] = {}
        self._count = 0
        self._stats = SpatialIndexStats()
        self._enable_cache = enable_cache
        self._cache = QueryCache(max_size=cache_size) if enable_cache else None
        self._rtree_ids: Dict[str, int] = {}
        self._rtree_shape_ids: Dict[int, str] = {}
        self._next_rtree_id = 1

        if HAS_RTREE:
            try:
                # 3D R-tree index
                self._index = index.Index(properties=index.Property(dimension=3))
                self._use_rtree = True
                logger.debug("[SpatialIndex] R-tree index initialized")
            except Exception as e:
                logger.warning(f"[SpatialIndex] R-tree initialization failed: {e}")
                self._index = None
                self._use_rtree = False
        else:
            self._index = None
            self._use_rtree = False

        if not self._use_rtree:
            logger.info("[SpatialIndex] Using linear search fallback (install rtree for O(log n) queries)")

        if self._cache:
            logger.debug(f"[SpatialIndex] Query cache enabled (size={cache_size})")

    def insert(
        self,
        shape_id: str,
        bounds: Tuple[float, ...] | Bounds,
        shape_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Insert a shape into the index.

        Args:
            shape_id: Unique identifier for the shape
            bounds: Bounding box as (min_x, min_y, min_z, max_x, max_y, max_z) or Bounds object
            shape_data: Optional metadata about the shape
        """
        # Normalize bounds to Bounds object
        if isinstance(bounds, Bounds):
            bounds_obj = bounds
        else:
            bounds_obj = Bounds(*bounds)

        # Store bounds and data
        self._bounds[shape_id] = bounds_obj
        if shape_data is not None:
            self._shapes[shape_id] = shape_data
        else:
            self._shapes[shape_id] = {}

        # Insert into R-tree if available
        if self._use_rtree and self._index is not None:
            try:
                rtree_id = self._rtree_ids.get(shape_id)
                if rtree_id is None:
                    rtree_id = self._next_rtree_id
                    self._next_rtree_id += 1
                    self._rtree_ids[shape_id] = rtree_id
                    self._rtree_shape_ids[rtree_id] = shape_id
                self._index.insert(rtree_id, bounds_obj.to_tuple())
            except Exception as e:
                logger.debug(f"[SpatialIndex] Failed to insert {shape_id}: {e}")

        self._count += 1

    def query_nearby(
        self,
        point: Tuple[float, float, float],
        radius: float,
        shape_type: Optional[str] = None
    ) -> List[str]:
        """
        Query all shapes within radius of a point.

        Args:
            point: Query point (x, y, z)
            radius: Search radius
            shape_type: Optional filter by shape type

        Returns:
            List of shape IDs within radius
        """
        start = time.perf_counter()

        if self._use_rtree and self._index is not None:
            result = self._query_nearby_rtree(point, radius, shape_type)
        else:
            result = self._query_nearby_linear(point, radius, shape_type)

        # Update statistics
        elapsed_ms = (time.perf_counter() - start) * 1000
        self._stats.query_count += 1
        self._stats.total_query_time_ms += elapsed_ms

        return result

    def _query_nearby_rtree(
        self,
        point: Tuple[float, float, float],
        radius: float,
        shape_type: Optional[str] = None
    ) -> List[str]:
        """Query using R-tree (O(log n))."""
        x, y, z = point
        min_pt = (x - radius, y - radius, z - radius)
        max_pt = (x + radius, y + radius, z + radius)

        try:
            candidate_ids = self._index.intersection(min_pt + max_pt)
        except Exception as e:
            logger.debug(f"[SpatialIndex] R-tree query failed: {e}")
            return []

        result = []
        for candidate_id in candidate_ids:
            shape_id = self._rtree_shape_ids.get(candidate_id)
            if shape_id is None:
                continue

            # Filter by shape type if requested
            if shape_type is not None:
                if self._shapes.get(shape_id, {}).get('shape_type') != shape_type:
                    continue

            result.append(shape_id)

        return result

    def _query_nearby_linear(
        self,
        point: Tuple[float, float, float],
        radius: float,
        shape_type: Optional[str] = None
    ) -> List[str]:
        """Query using linear search (O(n) fallback)."""
        result = []
        radius_sq = radius * radius

        for shape_id, bounds in self._bounds.items():
            # Check type filter first
            if shape_type is not None:
                if self._shapes.get(shape_id, {}).get('shape_type') != shape_type:
                    continue

            # Distance check
            dist = bounds.distance_to(point)
            if dist <= radius:
                result.append(shape_id)

        return result

    def nearest(
        self,
        point: Tuple[float, float, float],
        max_results: int = 10,
        shape_type: Optional[str] = None,
        use_cache: bool = True
    ) -> List[str]:
        """
        Find nearest shapes to a point.

        Args:
            point: Query point (x, y, z)
            max_results: Maximum number of results
            shape_type: Optional filter by shape type
            use_cache: Whether to use query cache (default: True)

        Returns:
            List of shape IDs, sorted by distance (nearest first)
        """
        start = time.perf_counter()

        # Check cache if enabled
        if use_cache and self._cache:
            cached = self._cache.get(point, max_results, shape_type)
            if cached is not None:
                self._stats.cache_hits += 1
                self._stats.nearest_count += 1
                return cached
            else:
                self._stats.cache_misses += 1

        # Perform actual query
        if self._use_rtree and self._index is not None:
            result = self._nearest_rtree(point, max_results, shape_type)
        else:
            result = self._nearest_linear(point, max_results, shape_type)

        # Store in cache if enabled
        if use_cache and self._cache:
            self._cache.put(point, max_results, shape_type, result)

        # Update statistics
        elapsed_ms = (time.perf_counter() - start) * 1000
        self._stats.nearest_count += 1
        self._stats.total_nearest_time_ms += elapsed_ms

        return result

    def _nearest_rtree(
        self,
        point: Tuple[float, float, float],
        max_results: int,
        shape_type: Optional[str]
    ) -> List[str]:
        """Find nearest using R-tree."""
        try:
            candidate_ids = self._index.nearest(point, max_results * 2)
        except Exception as e:
            logger.debug(f"[SpatialIndex] R-tree nearest failed: {e}")
            return []

        # Sort by actual distance and filter
        results = []
        for candidate_id in candidate_ids:
            shape_id = self._rtree_shape_ids.get(candidate_id)
            if shape_id is None:
                continue

            # Filter by shape type
            if shape_type is not None:
                if self._shapes.get(shape_id, {}).get('shape_type') != shape_type:
                    continue

            # Get distance for sorting
            bounds = self._bounds.get(shape_id)
            if bounds is not None:
                dist = bounds.distance_to(point)
                results.append((dist, shape_id))

        # Sort by distance and return IDs
        results.sort(key=lambda x: x[0])
        return [shape_id for _, shape_id in results[:max_results]]

    def _nearest_linear(
        self,
        point: Tuple[float, float, float],
        max_results: int,
        shape_type: Optional[str]
    ) -> List[str]:
        """Find nearest using linear search."""
        results = []

        for shape_id, bounds in self._bounds.items():
            # Filter by shape type
            if shape_type is not None:
                if self._shapes.get(shape_id, {}).get('shape_type') != shape_type:
                    continue

            dist = bounds.distance_to(point)
            results.append((dist, shape_id))

        # Sort by distance
        results.sort(key=lambda x: x[0])
        return [shape_id for _, shape_id in results[:max_results]]

    def batch_nearest(
        self,
        points: List[Tuple[float, float, float]],
        max_results: int = 10,
        shape_type: Optional[str] = None,
        use_cache: bool = True
    ) -> List[List[str]]:
        """
        Find nearest shapes for multiple query points.

        More efficient than calling nearest() multiple times as it
        can process queries in batches and share data between queries.

        Args:
            points: List of query points (x, y, z)
            max_results: Maximum number of results per point
            shape_type: Optional filter by shape type
            use_cache: Whether to use query cache

        Returns:
            List of result lists, one per query point
        """
        start = time.perf_counter()
        self._stats.batch_count += 1

        results = []
        for point in points:
            result = self.nearest(point, max_results, shape_type, use_cache)
            results.append(result)

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._stats.total_query_time_ms += elapsed_ms

        return results

    def batch_query_nearby(
        self,
        points: List[Tuple[float, float, float]],
        radius: float,
        shape_type: Optional[str] = None
    ) -> List[List[str]]:
        """
        Query shapes within radius for multiple query points.

        Args:
            points: List of query points (x, y, z)
            radius: Search radius
            shape_type: Optional filter by shape type

        Returns:
            List of result lists, one per query point
        """
        start = time.perf_counter()
        self._stats.batch_count += 1

        results = []
        for point in points:
            result = self.query_nearby(point, radius, shape_type)
            results.append(result)

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._stats.total_query_time_ms += elapsed_ms

        return results

    def remove(self, shape_id: str) -> bool:
        """
        Remove a shape from the index.

        Args:
            shape_id: Shape ID to remove

        Returns:
            True if shape was found and removed
        """
        if shape_id not in self._bounds:
            return False

        # Remove from R-tree
        if self._use_rtree and self._index is not None:
            try:
                bounds = self._bounds[shape_id]
                rtree_id = self._rtree_ids.pop(shape_id, None)
                if rtree_id is not None:
                    self._index.delete(rtree_id, bounds.to_tuple())
                    self._rtree_shape_ids.pop(rtree_id, None)
            except Exception as e:
                logger.debug(f"[SpatialIndex] Failed to remove {shape_id}: {e}")

        # Remove from dictionaries
        del self._bounds[shape_id]
        self._shapes.pop(shape_id, None)
        self._count -= 1

        return True

    def clear(self) -> None:
        """Clear all entries from the index and cache."""
        self._bounds.clear()
        self._shapes.clear()
        self._count = 0
        self._rtree_ids.clear()
        self._rtree_shape_ids.clear()
        self._next_rtree_id = 1

        # Clear cache if enabled
        if self._cache:
            self._cache.clear()

        if self._use_rtree and self._index is not None:
            try:
                # Create new index
                from rtree import index as rtree_index
                self._index = rtree_index.Index(properties=rtree_index.Property(dimension=3))
            except Exception as e:
                logger.debug(f"[SpatialIndex] Failed to recreate index: {e}")
                self._index = None

    def clear_cache(self) -> None:
        """Clear only the query cache, keeping index data."""
        if self._cache:
            self._cache.clear()

    def get_stats(self) -> SpatialIndexStats:
        """
        Get performance statistics.

        Returns:
            Copy of current statistics
        """
        return SpatialIndexStats(
            query_count=self._stats.query_count,
            nearest_count=self._stats.nearest_count,
            batch_count=self._stats.batch_count,
            cache_hits=self._stats.cache_hits,
            cache_misses=self._stats.cache_misses,
            total_query_time_ms=self._stats.total_query_time_ms,
            total_nearest_time_ms=self._stats.total_nearest_time_ms,
        )

    def reset_stats(self) -> None:
        """Reset performance statistics."""
        self._stats = SpatialIndexStats()

    def get_bounds(self, shape_id: str) -> Optional[Bounds]:
        """
        Get the bounds for a specific shape.

        Args:
            shape_id: Shape ID to query

        Returns:
            Bounds object or None if not found
        """
        return self._bounds.get(shape_id)

    def get_shape_data(self, shape_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the metadata for a specific shape.

        Args:
            shape_id: Shape ID to query

        Returns:
            Shape data dict or None if not found
        """
        return self._shapes.get(shape_id)

    def update_bounds(self, shape_id: str, new_bounds: Tuple[float, ...] | Bounds) -> None:
        """
        Update the bounds for an existing shape.

        Args:
            shape_id: Shape ID to update
            new_bounds: New bounding box
        """
        if shape_id not in self._bounds:
            self.insert(shape_id, new_bounds)
            return

        # Remove old entry
        self.remove(shape_id)

        # Insert with new bounds
        old_data = self._shapes.get(shape_id, {})
        self.insert(shape_id, new_bounds, old_data)

    @property
    def size(self) -> int:
        """Number of shapes in the index."""
        return self._count

    @property
    def is_accelerated(self) -> bool:
        """Whether R-tree acceleration is enabled."""
        return self._use_rtree

    def __len__(self) -> int:
        """Return the number of shapes in the index."""
        return self._count

    def __contains__(self, shape_id: str) -> bool:
        """Check if a shape ID is in the index."""
        return shape_id in self._bounds


def compute_bounds_from_signature(signature: Dict[str, Any]) -> Optional[Bounds]:
    """
    Compute bounding box from geometric signature.

    Args:
        signature: Geometric signature from ShapeRecord

    Returns:
        Bounds object or None if signature invalid
    """
    if not signature:
        return None

    center = signature.get('center')
    if center is None:
        return None

    # Try to get size from signature
    size = signature.get('bounds_size', 1.0)  # Default 1mm radius

    # For edges, use length as size hint
    if 'length' in signature:
        size = max(size, signature['length'] / 2)

    # For faces, use area as size hint
    if 'area' in signature:
        import math
        area = signature['area']
        size = max(size, math.sqrt(area) / 2)

    return Bounds.from_center(center, size)
