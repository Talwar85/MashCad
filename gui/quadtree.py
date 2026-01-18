"""
MashCad - Spatial Indexing (Quadtree)
Provides O(log n) spatial queries for hit-testing and snapping.
"""

from PySide6.QtCore import QRectF

class QuadTree:
    """
    Root wrapper for the Quadtree. 
    Handles dynamic resizing and interface.
    """
    def __init__(self, bounds: QRectF, max_items=8, max_depth=8):
        self.root = QuadTreeNode(bounds, max_items, max_depth, depth=0)
        self.max_items = max_items
        self.max_depth = max_depth

    def insert(self, item, bounds: QRectF):
        """
        Insert an item into the tree.
        :param item: The geometry object (Line2D, Circle2D, etc.)
        :param bounds: The QRectF bounding box of the item
        """
        self.root.insert(item, bounds)

    def query(self, range_rect: QRectF):
        """
        Returns a list of items whose bounds intersect with range_rect.
        """
        return self.root.query(range_rect)
    
    def clear(self, bounds: QRectF):
        """Resets the tree with new bounds."""
        self.root = QuadTreeNode(bounds, self.max_items, self.max_depth, depth=0)


class QuadTreeNode:
    def __init__(self, bounds: QRectF, max_items, max_depth, depth):
        self.bounds = bounds
        self.max_items = max_items
        self.max_depth = max_depth
        self.depth = depth
        # Stores tuples of (item, item_bounds)
        self.items = [] 
        self.children = None

    def insert(self, item, item_bounds: QRectF):
        # Optimization: If item doesn't touch this node, ignore (should be handled by parent, but safety first)
        if not self.bounds.intersects(item_bounds):
            return False

        # If we are at capacity and not at max depth, split and push down
        if len(self.items) >= self.max_items and self.depth < self.max_depth:
            if not self.children:
                self._subdivide()
            
            # Try to push existing items to children
            # (In a dynamic quadtree, usually we only push down on split)
            self._insert_into_children(item, item_bounds)
            return True

        # Otherwise add here
        self.items.append((item, item_bounds))
        
        # If we just exceeded capacity, try to split now
        if len(self.items) > self.max_items and self.depth < self.max_depth and not self.children:
            self._subdivide()
            # Re-distribute existing items to children
            # Note: Items that overlap multiple children stay in parent in some implementations,
            # or go into all overlapping children in others. 
            # Here: We push to all overlapping children to ensure query finds them.
            old_items = self.items
            self.items = []
            for it, bd in old_items:
                self._insert_into_children(it, bd)

        return True

    def _insert_into_children(self, item, item_bounds):
        # Determine which children the item overlaps
        placed = False
        if self.children:
            for child in self.children:
                if child.bounds.intersects(item_bounds):
                    child.insert(item, item_bounds)
                    placed = True
        
        # If it didn't fit perfectly into children (shouldn't happen with intersects check), keep it here
        if not placed and not self.children:
             self.items.append((item, item_bounds))

    def _subdivide(self):
        x, y, w, h = self.bounds.x(), self.bounds.y(), self.bounds.width(), self.bounds.height()
        hw, hh = w / 2, h / 2
        
        self.children = [
            QuadTreeNode(QRectF(x, y, hw, hh), self.max_items, self.max_depth, self.depth + 1),       # TL
            QuadTreeNode(QRectF(x + hw, y, hw, hh), self.max_items, self.max_depth, self.depth + 1),  # TR
            QuadTreeNode(QRectF(x, y + hh, hw, hh), self.max_items, self.max_depth, self.depth + 1),  # BL
            QuadTreeNode(QRectF(x + hw, y + hh, hw, hh), self.max_items, self.max_depth, self.depth + 1) # BR
        ]

    def query(self, range_rect: QRectF):
        results = []
        
        # Fast rejection
        if not self.bounds.intersects(range_rect):
            return results

        # Check items in this node
        for item, item_bounds in self.items:
            if range_rect.intersects(item_bounds):
                results.append(item)

        # Check children
        if self.children:
            for child in self.children:
                results.extend(child.query(range_rect))
        
        return results