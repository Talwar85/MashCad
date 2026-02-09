#!/usr/bin/env python3
"""Check OCP methods for cylindrical face modification"""
try:
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
    print('1. BRepOffsetAPI_MakeOffsetShape - Offset/Thicken faces')
except ImportError:
    print('1. BRepOffsetAPI_MakeOffsetShape NOT available')

try:
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThickSolid
    print('2. BRepOffsetAPI_ThickSolid - Hollow/Shell operations')
except ImportError:
    print('2. BRepOffsetAPI_ThickSolid NOT available')

try:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_ModifyShape
    print('3. BRepBuilderAPI_ModifyShape - Direct modification API')
except ImportError:
    print('3. BRepBuilderAPI_ModifyShape NOT available')

try:
    from OCP.GeomAbs import GeomAbs_Cylinder
    print('4. GeomAbs_Cylinder =', GeomAbs_Cylinder)
except ImportError:
    print('4. GeomAbs_Cylinder NOT available')

try:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    print('5. BRepAdaptor_Surface - Analyze surface type')
except ImportError:
    print('5. BRepAdaptor_Surface NOT available')

try:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    print('6. BRepBuilderAPI_MakeFace - Create faces from surfaces')
except ImportError:
    print('6. BRepBuilderAPI_MakeFace NOT available')

try:
    from OCP.Geom import Geom_CylindricalSurface
    print('7. Geom_CylindricalSurface - Create/modify cylindrical surfaces')
except ImportError:
    print('7. Geom_CylindricalSurface NOT available')

try:
    from OCP.gp import gp_Cylinder
    print('8. gp_Cylinder - Cylinder geometry definition')
except ImportError:
    print('8. gp_Cylinder NOT available')

# Check for BRepFeat
try:
    from OCP.BRepFeat import BRepFeat_MakePrism, BRepFeat_MakeDPrism
    print('8. BRepFeat_MakePrism/DPrism - Local prism operations')
except:
    print('8. BRepFeat not available')

# Check for shape modification
try:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    print('9. BRepBuilderAPI_Copy - Copy shapes')
except:
    print('9. BRepBuilderAPI_Copy not available')

# Check for direct face replacement
try:
    from OCP.BRepTools import BRepTools_ReShape
    print('10. BRepTools_ReShape - Replace faces in shapes')
except:
    print('10. BRepTools_ReShape not available')

# Check for BRepLib
try:
    from OCP.BRepLib import BRepLib
    print('11. BRepLib - Various shape operations')
except:
    print('11. BRepLib not available')

print('\n=== Key API for cylindrical face radius modification ===')
print('BRepOffsetAPI_MakeOffsetShape: Can offset faces along their normal')
print('BRepTools_ReShape: Can replace faces in a shape')
print('Geom_CylindricalSurface: Create new cylindrical surface with different radius')
