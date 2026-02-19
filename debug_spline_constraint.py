from sketcher.geometry import BezierSpline, Point2D
from sketcher.sketch import Sketch
from sketcher.constraints import Constraint, ConstraintType

# Debug Test
sketch = Sketch()
spline = BezierSpline()
spline.add_point(0, 0)
spline.add_point(10, 10)
spline.add_point(20, 0)
sketch.splines.append(spline)

# Prüfe Control Points
cps = sketch.get_spline_control_points()
print(f'Control Points: {len(cps)}')
for i, cp in enumerate(cps):
    print(f'  CP[{i}]: id={id(cp)}, x={cp.x:.1f}, y={cp.y:.1f}, fixed={getattr(cp, "fixed", False)}')

# FIXED Constraint
constraint1 = Constraint(ConstraintType.FIXED, entities=[cps[0]])
sketch.constraints.append(constraint1)

print(f'After FIXED constraint:')
print(f'  CP[0].fixed={cps[0].fixed}')

# DISTANCE Constraint
constraint2 = Constraint(ConstraintType.DISTANCE, entities=[cps[0], cps[1]], value=15.0)
sketch.constraints.append(constraint2)

print(f'Constraints added: {len(sketch.constraints)}')

# Solve
result = sketch.solve()
print(f'Result: success={result.success}, message={result.message}')
print(f'CP[0]: x={cps[0].x:.2f}, y={cps[0].y:.2f}')
print(f'CP[1]: x={cps[1].x:.2f}, y={cps[1].y:.2f}')

import math
dist = math.hypot(cps[1].x - cps[0].x, cps[1].y - cps[0].y)
print(f'Distance: {dist:.2f}')
