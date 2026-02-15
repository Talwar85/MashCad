import sys
import unittest
from unittest.mock import MagicMock

# Add C:\LiteCad to sys.path
sys.path.append(r"C:\LiteCad")

from sketcher.geometry import BezierSpline

class TestSplineHash(unittest.TestCase):
    def test_spline_hashable(self):
        s1 = BezierSpline()
        s2 = BezierSpline()
        
        # Test hash
        try:
            h1 = hash(s1)
            h2 = hash(s2)
        except TypeError:
            self.fail("BezierSpline is not hashable")
            
        self.assertNotEqual(h1, h2)
        
        # Test set operation
        try:
            s = set()
            s.add(s1)
            s.add(s2)
            self.assertEqual(len(s), 2)
            s.add(s1) # Add again
            self.assertEqual(len(s), 2) 
        except TypeError:
            self.fail("BezierSpline cannot be added to a set")

if __name__ == '__main__':
    unittest.main()
