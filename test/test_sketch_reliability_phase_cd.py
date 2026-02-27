from sketcher import (
    Sketch,
    make_fixed,
    make_horizontal,
    make_length,
    make_radius,
    make_vertical,
    ConstraintSolver,
)


class TestSketchSerialization:
    def test_simple_sketch_serialization_roundtrip(self):
        sketch = Sketch(name="TestSketch")
        line_bottom = sketch.add_line(0, 0, 10, 0)
        line_right = sketch.add_line(10, 0, 10, 10)
        sketch.add_line(10, 10, 0, 10)
        sketch.add_line(0, 10, 0, 0)

        anchor = sketch.points[0]
        sketch.constraints.append(make_fixed(anchor))
        sketch.constraints.append(make_horizontal(line_bottom))
        sketch.constraints.append(make_vertical(line_right))
        sketch.plane_origin = (1, 2, 3)
        sketch.plane_normal = (0, 0, 1)
        sketch.plane_x_dir = (1, 0, 0)
        sketch.plane_y_dir = (0, 1, 0)

        data = sketch.to_dict()

        assert data["plane_origin"] == (1, 2, 3)
        assert data["plane_normal"] == (0, 0, 1)
        assert data["plane_x_dir"] == (1, 0, 0)
        assert data["plane_y_dir"] == (0, 1, 0)

        restored = Sketch.from_dict(data)

        assert restored.name == "TestSketch"
        assert len(restored.points) == 4
        assert len(restored.lines) == 4
        assert len(restored.constraints) == 3
        assert restored.points[0].fixed is True
        assert restored.plane_origin == (1, 2, 3)
        assert restored.plane_normal == (0, 0, 1)
        assert restored.plane_x_dir == (1, 0, 0)
        assert restored.plane_y_dir == (0, 1, 0)
        assert restored.points[0].x == 0
        assert restored.points[0].y == 0
        assert restored.points[3].x == 0
        assert restored.points[3].y == 10

    def test_sketch_with_circle_serialization(self):
        sketch = Sketch(name="CircleSketch")
        sketch.add_circle(5, 5, 3.0)

        center_point = sketch.points[0]
        circle = sketch.circles[0]
        sketch.constraints.append(make_fixed(center_point))
        sketch.constraints.append(make_radius(circle, 3.0))

        data = sketch.to_dict()
        restored = Sketch.from_dict(data)

        assert len(restored.circles) == 1
        assert restored.circles[0].radius == 3.0
        assert restored.circles[0].center.x == 5
        assert restored.circles[0].center.y == 5
        assert restored.points[0].fixed is True

    def test_sketch_with_arc_serialization(self):
        sketch = Sketch(name="ArcSketch")
        sketch.add_arc(0, 0, 5.0, 0, 90)

        data = sketch.to_dict()
        restored = Sketch.from_dict(data)

        assert len(restored.arcs) == 1
        assert restored.arcs[0].radius == 5.0
        assert restored.arcs[0].sweep_angle == 90

    def test_constraint_values_roundtrip(self):
        sketch = Sketch(name="ConstraintValues")
        line = sketch.add_line(0, 0, 10, 0)
        sketch.constraints.append(make_length(line, 15.5))
        sketch.constraints.append(make_fixed(sketch.points[0]))

        data = sketch.to_dict()
        restored = Sketch.from_dict(data)

        length_constraints = [constraint for constraint in restored.constraints if constraint.type.name == "LENGTH"]
        assert len(length_constraints) == 1
        assert length_constraints[0].value == 15.5
        assert restored.points[0].fixed is True

    def test_native_ocp_data_roundtrip(self):
        sketch = Sketch(name="OCPData")
        sketch.add_circle(5, 5, 3.0)

        expected_native_data = {
            "center": {"x": 5.0, "y": 5.0, "z": 0.0},
            "radius": 3.0,
            "plane": "XY",
        }
        circle = sketch.circles[0]
        circle.native_ocp_data = expected_native_data

        data = sketch.to_dict()
        restored = Sketch.from_dict(data)

        assert restored.circles[0].native_ocp_data is not None
        assert restored.circles[0].native_ocp_data == expected_native_data


class TestSketchWithComplexGeometry:
    def test_ellipse_sketch_serialization(self):
        sketch = Sketch(name="EllipseSketch")
        sketch.add_ellipse(5, 5, 10.0, 5.0, 0.0)

        data = sketch.to_dict()
        restored = Sketch.from_dict(data)

        assert len(restored.ellipses) == 1
        assert restored.ellipses[0].radius_x == 10.0
        assert restored.ellipses[0].radius_y == 5.0
        assert restored.ellipses[0].rotation == 0.0

    def test_ellipse_with_native_ocp_data(self):
        sketch = Sketch(name="EllipseOCP")
        sketch.add_ellipse(5, 5, 10.0, 5.0, 30.0)

        expected_native_data = {
            "center": {"x": 5.0, "y": 5.0, "z": 0.0},
            "major_radius": 10.0,
            "minor_radius": 5.0,
            "rotation": 30.0,
            "plane": "XY",
        }
        ellipse = sketch.ellipses[0]
        ellipse.native_ocp_data = expected_native_data

        data = sketch.to_dict()
        restored = Sketch.from_dict(data)

        assert restored.ellipses[0].native_ocp_data is not None
        assert restored.ellipses[0].native_ocp_data == expected_native_data


class TestConstraintSolverApi:
    def test_solver_requires_separate_parameters(self):
        sketch = Sketch(name="SolverApiTest")
        line_bottom = sketch.add_line(0, 0, 10, 0)
        line_right = sketch.add_line(10, 0, 10, 10)
        sketch.add_line(10, 10, 0, 10)
        sketch.add_line(0, 10, 0, 0)

        sketch.constraints.append(make_fixed(sketch.points[0]))
        sketch.constraints.append(make_horizontal(line_bottom))
        sketch.constraints.append(make_vertical(line_right))

        solver = ConstraintSolver()
        result = solver.solve(
            points=sketch.points,
            lines=sketch.lines,
            circles=sketch.circles,
            arcs=sketch.arcs,
            constraints=sketch.constraints,
        )

        assert result.success


class TestConstraintStatus:
    def test_fully_constrained_status(self):
        sketch = Sketch(name="FullyConstrained")
        line_bottom = sketch.add_line(0, 0, 10, 0)
        line_right = sketch.add_line(10, 0, 10, 10)
        line_top = sketch.add_line(10, 10, 0, 10)
        line_left = sketch.add_line(0, 10, 0, 0)

        sketch.constraints.append(make_fixed(sketch.points[0]))
        sketch.constraints.append(make_horizontal(line_bottom))
        sketch.constraints.append(make_vertical(line_right))
        sketch.constraints.append(make_horizontal(line_top))
        sketch.constraints.append(make_vertical(line_left))
        sketch.constraints.append(make_length(line_bottom, 10))
        sketch.constraints.append(make_length(line_right, 10))

        solver = ConstraintSolver()
        result = solver.solve(
            points=sketch.points,
            lines=sketch.lines,
            circles=sketch.circles,
            arcs=sketch.arcs,
            constraints=sketch.constraints,
        )

        assert result.success
        assert result.dof == 0

    def test_under_constrained_status(self):
        sketch = Sketch(name="UnderConstrained")
        line_bottom = sketch.add_line(0, 0, 10, 0)
        line_right = sketch.add_line(10, 0, 10, 10)
        sketch.add_line(10, 10, 0, 10)

        sketch.constraints.append(make_fixed(sketch.points[0]))
        sketch.constraints.append(make_horizontal(line_bottom))
        sketch.constraints.append(make_vertical(line_right))

        solver = ConstraintSolver()
        result = solver.solve(
            points=sketch.points,
            lines=sketch.lines,
            circles=sketch.circles,
            arcs=sketch.arcs,
            constraints=sketch.constraints,
        )

        assert result.success
        assert result.dof > 0
