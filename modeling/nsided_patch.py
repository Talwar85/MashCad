"""
MashCad - N-Sided Patch (Surface Fill)
xNURBS-Alternative using OCP BRepFill_Filling (Gordon surface).

Creates a smooth surface that fills an N-sided boundary of edges.
Similar to Rhino's Patch command or Plasticity's xNURBS Fill.
"""

from loguru import logger


class NSidedPatch:
    """
    Fills an N-sided hole or boundary with a smooth NURBS surface.

    Uses BRepFill_Filling which creates a plate surface (energy-minimizing)
    constrained to the boundary edges. Supports:
    - Edge boundary constraints (G0 positional)
    - Face tangency constraints (G1 continuity)
    - Point constraints (pass-through points)
    """

    @staticmethod
    def fill_edges(edges, tangent_faces=None, degree=3, max_segments=12,
                   tolerance=1e-3):
        """
        Create a surface filling N boundary edges.

        Args:
            edges: List of Build123d Edge objects forming a closed boundary
            tangent_faces: Optional list of (edge_index, face) for G1 tangency
            degree: Surface degree (3=cubic, default)
            max_segments: Max BSpline segments
            tolerance: Approximation tolerance

        Returns:
            Build123d Face or None on failure
        """
        if not edges or len(edges) < 3:
            raise ValueError(f"N-Sided Patch benötigt mindestens 3 Kanten, erhalten: {len(edges) if edges else 0}")

        try:
            from OCP.BRepFill import BRepFill_Filling
            from OCP.GeomAbs import GeomAbs_C0, GeomAbs_G1
            from OCP.TopoDS import TopoDS
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
            from build123d import Face

            filler = BRepFill_Filling(degree, max_segments, 15)

            # Add boundary edges
            for i, edge in enumerate(edges):
                edge_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge

                # Check if this edge has tangency constraint
                has_tangency = False
                if tangent_faces:
                    for ei, face in tangent_faces:
                        if ei == i:
                            face_shape = face.wrapped if hasattr(face, 'wrapped') else face
                            filler.Add(TopoDS.Edge_s(edge_shape),
                                       TopoDS.Face_s(face_shape),
                                       GeomAbs_G1)
                            has_tangency = True
                            break

                if not has_tangency:
                    filler.Add(TopoDS.Edge_s(edge_shape), GeomAbs_C0)

            logger.info(f"N-Sided Patch: {len(edges)} Kanten, Grad={degree}")

            filler.Build()

            if not filler.IsDone():
                raise RuntimeError("BRepFill_Filling fehlgeschlagen")

            result_face = filler.Face()

            if result_face.IsNull():
                raise RuntimeError("Resultat-Face ist null")

            face = Face(result_face)
            logger.success(f"N-Sided Patch erfolgreich: {len(edges)} Kanten")
            return face

        except Exception as e:
            logger.error(f"N-Sided Patch fehlgeschlagen: {e}")
            raise

    @staticmethod
    def fill_hole(solid, hole_edges, tangent=True):
        """
        Fill a hole in a solid by detecting boundary edges and creating
        a patch surface with optional tangency to adjacent faces.

        Args:
            solid: Build123d Solid with a hole
            hole_edges: List of Edge objects forming the hole boundary
            tangent: If True, try to match tangency with adjacent faces

        Returns:
            Build123d Solid with hole filled, or None
        """
        try:
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE
            from build123d import Solid

            # Get tangent face pairs if requested
            tangent_faces = []
            if tangent:
                tangent_faces = NSidedPatch._find_adjacent_faces(solid, hole_edges)

            # Create patch face
            patch_face = NSidedPatch.fill_edges(hole_edges, tangent_faces)
            if patch_face is None:
                return None

            # Sew patch onto solid
            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid
            patch_shape = patch_face.wrapped if hasattr(patch_face, 'wrapped') else patch_face

            sewing = BRepBuilderAPI_Sewing(1e-3)
            sewing.Add(shape)
            sewing.Add(patch_shape)
            sewing.Perform()

            sewn = sewing.SewedShape()

            # Try to make solid
            try:
                maker = BRepBuilderAPI_MakeSolid()

                explorer = TopExp_Explorer(sewn, TopAbs_FACE)
                from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeShell
                from OCP.TopAbs import TopAbs_SHELL
                shell_exp = TopExp_Explorer(sewn, TopAbs_SHELL)
                if shell_exp.More():
                    from OCP.TopoDS import TopoDS
                    maker.Add(TopoDS.Shell_s(shell_exp.Current()))

                maker.Build()
                if maker.IsDone():
                    result = Solid(maker.Shape())
                    logger.success("Hole fill: Solid erstellt")
                    return result
            except Exception:
                pass

            # Return as-is if solid creation fails
            from build123d import Shape
            logger.warning("Hole fill: Kein Solid, gebe Shape zurück")
            return Shape(sewn)

        except Exception as e:
            logger.error(f"Hole fill fehlgeschlagen: {e}")
            raise

    @staticmethod
    def _find_adjacent_faces(solid, edges):
        """Find faces adjacent to boundary edges for tangency constraints."""
        try:
            from OCP.TopExp import TopExp_Explorer, TopExp
            from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
            from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
            from OCP.TopoDS import TopoDS

            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Build edge→face adjacency map
            edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
            TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

            tangent_faces = []
            for i, edge in enumerate(edges):
                edge_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge
                try:
                    idx = edge_face_map.FindIndex(edge_shape)
                    if idx > 0:
                        face_list = edge_face_map.FindFromIndex(idx)
                        if face_list.Size() > 0:
                            face = face_list.First()
                            tangent_faces.append((i, face))
                except Exception:
                    continue

            logger.debug(f"Found {len(tangent_faces)} tangent face constraints")
            return tangent_faces

        except Exception as e:
            logger.debug(f"Adjacent face detection failed: {e}")
            return []
