from sketcher import Sketch
from sketcher.profile_detector_b3d import Build123dProfileDetector, is_available as has_profile_detector
from build123d import Plane, Face, extrude

assert has_profile_detector(), "Build123d profile detector must be available in cad_env"


class TestProfileDetection:
    def test_simple_rectangle_profile(self):
        sketch = Sketch(name="Rectangle")
        sketch.add_line(0, 0, 10, 0)
        sketch.add_line(10, 0, 10, 10)
        sketch.add_line(10, 10, 0, 10)
        sketch.add_line(0, 10, 0, 0)

        detector = Build123dProfileDetector()
        faces = detector.detect_profiles(sketch, Plane.XY)

        assert len(faces) >= 1
        assert isinstance(faces[0], Face)

    def test_circle_profile(self):
        sketch = Sketch(name="Circle")
        sketch.add_circle(5, 5, 3.0)

        detector = Build123dProfileDetector()
        faces = detector.detect_profiles(sketch, Plane.XY)

        assert len(faces) >= 1

    def test_multiple_profiles(self):
        sketch = Sketch(name="MultipleCircles")
        sketch.add_circle(0, 0, 2.0)
        sketch.add_circle(10, 0, 2.0)
        sketch.add_circle(20, 0, 2.0)

        detector = Build123dProfileDetector()
        faces = detector.detect_profiles(sketch, Plane.XY)

        assert len(faces) >= 3

    def test_open_profile_rejected(self):
        sketch = Sketch(name="OpenLine")
        sketch.add_line(0, 0, 10, 0)
        sketch.add_line(10, 0, 10, 10)

        detector = Build123dProfileDetector()
        faces, error = detector.get_profiles_for_extrude(sketch, Plane.XY)

        assert faces == []
        assert error is not None

    def test_all_construction_geometry_ignored(self):
        sketch = Sketch(name="AllConstruction")
        l1 = sketch.add_line(0, 0, 10, 0)
        l1.construction = True
        l2 = sketch.add_line(10, 0, 10, 10)
        l2.construction = True
        l3 = sketch.add_line(10, 10, 0, 10)
        l3.construction = True
        l4 = sketch.add_line(0, 10, 0, 0)
        l4.construction = True

        detector = Build123dProfileDetector()
        faces = detector.detect_profiles(sketch, Plane.XY)

        assert faces == []


class TestExtrudeOperations:
    def test_extrude_rectangle_profile(self):
        sketch = Sketch(name="ExtrudeRect")
        sketch.add_line(0, 0, 10, 0)
        sketch.add_line(10, 0, 10, 10)
        sketch.add_line(10, 10, 0, 10)
        sketch.add_line(0, 10, 0, 0)

        detector = Build123dProfileDetector()
        faces, error = detector.get_profiles_for_extrude(sketch, Plane.XY)

        assert error is None
        assert len(faces) >= 1

        solid = extrude(faces[0], amount=5.0)

        assert solid is not None
        assert solid.volume > 0

    def test_extrude_circle_profile(self):
        sketch = Sketch(name="ExtrudeCircle")
        sketch.add_circle(0, 0, 5.0)

        detector = Build123dProfileDetector()
        faces, error = detector.get_profiles_for_extrude(sketch, Plane.XY)

        assert error is None
        assert len(faces) >= 1

        solid = extrude(faces[0], amount=10.0)

        assert solid is not None
        assert 700 < solid.volume < 900

    def test_extrude_with_hole(self):
        sketch = Sketch(name="RectWithHole")
        sketch.add_line(0, 0, 20, 0)
        sketch.add_line(20, 0, 20, 20)
        sketch.add_line(20, 20, 0, 20)
        sketch.add_line(0, 20, 0, 0)

        sketch.add_line(5, 5, 15, 5)
        sketch.add_line(15, 5, 15, 15)
        sketch.add_line(15, 15, 5, 15)
        sketch.add_line(5, 15, 5, 5)

        detector = Build123dProfileDetector()
        faces, error = detector.get_profiles_for_extrude(sketch, Plane.XY)

        assert error is None
        assert faces

        solid = extrude(faces[0], amount=5.0)

        assert solid is not None
        assert solid.volume < 2000


class TestSketchValidation:
    def test_empty_sketch_detection(self):
        sketch = Sketch(name="Empty")

        detector = Build123dProfileDetector()
        faces = detector.detect_profiles(sketch, Plane.XY)

        assert faces == []

    def test_only_construction_geometry_detection(self):
        sketch = Sketch(name="OnlyConstruction")
        line = sketch.add_line(0, 0, 10, 0)
        line.construction = True
        circle = sketch.add_circle(5, 5, 3.0)
        circle.construction = True

        detector = Build123dProfileDetector()
        faces = detector.detect_profiles(sketch, Plane.XY)

        assert faces == []


class TestComplexSketches:
    def test_concentric_circles(self):
        sketch = Sketch(name="Concentric")
        sketch.add_circle(0, 0, 5.0)
        sketch.add_circle(0, 0, 3.0)
        sketch.add_circle(0, 0, 1.0)

        detector = Build123dProfileDetector()
        faces = detector.detect_profiles(sketch, Plane.XY)

        assert len(faces) >= 3

    def test_mixed_geometry_profile(self):
        sketch = Sketch(name="Mixed")
        sketch.add_line(2, 0, 8, 0)
        sketch.add_arc(8, 2, 2, 270, 360)
        sketch.add_line(10, 2, 10, 8)
        sketch.add_arc(8, 8, 2, 0, 90)
        sketch.add_line(8, 10, 2, 10)
        sketch.add_arc(2, 8, 2, 90, 180)
        sketch.add_line(0, 8, 0, 2)
        sketch.add_arc(2, 2, 2, 180, 270)

        detector = Build123dProfileDetector()
        faces, error = detector.get_profiles_for_extrude(sketch, Plane.XY)

        assert error is None
        assert len(faces) >= 1
