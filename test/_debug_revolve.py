"""Debug Revolve Volume Issue"""
from build123d import Vector, Face, make_face, Wire, Location
from modeling.ocp_helpers import OCPRevolveHelper
from modeling.tnp_system import ShapeNamingService

# Test revolve
pts = [
    Vector(0, 0, 0),
    Vector(2, 0, 0),
    Vector(2, 10, 0),
    Vector(0, 10, 0)
]
wire = Wire.make_polygon(pts)
face = make_face(wire)
face = face.moved(Location(Vector(10, 0, 0)))

naming_service = ShapeNamingService()

result = OCPRevolveHelper.revolve(
    face=face,
    axis_origin=Vector(0, 0, 0),
    axis_direction=Vector(0, 0, 1),
    angle_deg=360.0,
    naming_service=naming_service,
    feature_id='test_revolve'
)

print(f'Result type: {type(result)}')
print(f'Volume: {result.volume}')
print(f'Is valid: {not result.is_null()}')
print(f'Faces: {len(list(result.faces()))}')
