"""
MashCad - Spatial Indexing (Quadtree)
Safe against NumPy types.
"""
from PySide6.QtCore import QRectF

class QuadTree:
    def __init__(self, bounds: QRectF, max_items=8, max_depth=8):
        # Native Ints erzwingen
        self.root = QuadTreeNode(bounds, int(max_items), int(max_depth), 0)

    def insert(self, item, bounds: QRectF):
        self.root.insert(item, bounds)

    def query(self, range_rect: QRectF):
        return self.root.query(range_rect)

class QuadTreeNode:
    def __init__(self, bounds: QRectF, max_items, max_depth, depth):
        self.bounds = bounds
        self.max_items = int(max_items)
        self.max_depth = int(max_depth)
        self.depth = int(depth)
        self.items = []
        self.children = None

    def insert(self, item, item_bounds: QRectF):
        if not bool(self.bounds.intersects(item_bounds)):  # ← Explizit zu bool
            return False

        if len(self.items) >= self.max_items and self.depth < self.max_depth:
            if not self.children:
                self._subdivide()
            self._insert_into_children(item, item_bounds)
            return True

        self.items.append((item, item_bounds))
        
        if len(self.items) > self.max_items and self.depth < self.max_depth and not self.children:
            self._subdivide()
            old_items = self.items
            self.items = []
            for it, bd in old_items:
                self._insert_into_children(it, bd)
        return True

    def _insert_into_children(self, item, item_bounds):
        placed = False
        if self.children:
            for child in self.children:
                if child.bounds.intersects(item_bounds):
                    child.insert(item, item_bounds)
                    placed = True
        if not placed and not self.children:
             self.items.append((item, item_bounds))

    def _subdivide(self):
        # EXPLIZITES CASTING verhindert NumPy-Probleme bei der Rechteck-Erstellung
        x = float(self.bounds.x())
        y = float(self.bounds.y())
        w = float(self.bounds.width())
        h = float(self.bounds.height())
        
        hw = w / 2.0
        hh = h / 2.0
        next_depth = self.depth + 1
        
        self.children = [
            QuadTreeNode(QRectF(x, y, hw, hh), self.max_items, self.max_depth, next_depth),
            QuadTreeNode(QRectF(x + hw, y, hw, hh), self.max_items, self.max_depth, next_depth),
            QuadTreeNode(QRectF(x, y + hh, hw, hh), self.max_items, self.max_depth, next_depth),
            QuadTreeNode(QRectF(x + hw, y + hh, hw, hh), self.max_items, self.max_depth, next_depth)
        ]

    def query(self, range_rect: QRectF):
        results = []
        if not bool(self.bounds.intersects(range_rect)):
            return results
        for item, item_bounds in self.items:
            if bool(range_rect.intersects(item_bounds)):
                results.append(item)
        if self.children:
            for child in self.children:
                results.extend(child.query(range_rect))
        return results