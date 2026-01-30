"""
MashCad - Lattice Generator
Beam-based lattice structures for 3D printing (lightweight, material-saving).

Unit cell types: BCC, FCC, Octet, Diamond
Strategy: Define unit cell edges → repeat over bounding box → sweep with circle → fuse → intersect with body.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from loguru import logger


# Unit cell definitions: list of (start, end) pairs as fractional coordinates [0,1]^3
UNIT_CELLS = {
    "BCC": [
        # Body center to all 8 corners
        ((0.5, 0.5, 0.5), (0, 0, 0)),
        ((0.5, 0.5, 0.5), (1, 0, 0)),
        ((0.5, 0.5, 0.5), (0, 1, 0)),
        ((0.5, 0.5, 0.5), (1, 1, 0)),
        ((0.5, 0.5, 0.5), (0, 0, 1)),
        ((0.5, 0.5, 0.5), (1, 0, 1)),
        ((0.5, 0.5, 0.5), (0, 1, 1)),
        ((0.5, 0.5, 0.5), (1, 1, 1)),
    ],
    "FCC": [
        # Face centers to corners (12 edges per cell)
        ((0.5, 0.5, 0), (0, 0, 0)), ((0.5, 0.5, 0), (1, 0, 0)),
        ((0.5, 0.5, 0), (0, 1, 0)), ((0.5, 0.5, 0), (1, 1, 0)),
        ((0.5, 0, 0.5), (0, 0, 0)), ((0.5, 0, 0.5), (1, 0, 0)),
        ((0.5, 0, 0.5), (0, 0, 1)), ((0.5, 0, 0.5), (1, 0, 1)),
        ((0, 0.5, 0.5), (0, 0, 0)), ((0, 0.5, 0.5), (0, 1, 0)),
        ((0, 0.5, 0.5), (0, 0, 1)), ((0, 0.5, 0.5), (0, 1, 1)),
    ],
    "Octet": [
        # Octet truss: FCC + cross braces (very stiff)
        # FCC edges
        ((0.5, 0.5, 0), (0, 0, 0)), ((0.5, 0.5, 0), (1, 0, 0)),
        ((0.5, 0.5, 0), (0, 1, 0)), ((0.5, 0.5, 0), (1, 1, 0)),
        ((0.5, 0, 0.5), (0, 0, 0)), ((0.5, 0, 0.5), (1, 0, 0)),
        ((0.5, 0, 0.5), (0, 0, 1)), ((0.5, 0, 0.5), (1, 0, 1)),
        ((0, 0.5, 0.5), (0, 0, 0)), ((0, 0.5, 0.5), (0, 1, 0)),
        ((0, 0.5, 0.5), (0, 0, 1)), ((0, 0.5, 0.5), (0, 1, 1)),
        # Cross connections between face centers
        ((0.5, 0.5, 0), (0.5, 0, 0.5)),
        ((0.5, 0.5, 0), (0, 0.5, 0.5)),
        ((0.5, 0, 0.5), (0, 0.5, 0.5)),
    ],
    "Diamond": [
        # Diamond cubic: tetrahedral connections (flexible)
        ((0.25, 0.25, 0.25), (0, 0, 0)),
        ((0.25, 0.25, 0.25), (0.5, 0.5, 0)),
        ((0.25, 0.25, 0.25), (0.5, 0, 0.5)),
        ((0.25, 0.25, 0.25), (0, 0.5, 0.5)),
        ((0.75, 0.75, 0.75), (1, 1, 1)),
        ((0.75, 0.75, 0.75), (0.5, 0.5, 1)),
        ((0.75, 0.75, 0.75), (0.5, 1, 0.5)),
        ((0.75, 0.75, 0.75), (1, 0.5, 0.5)),
    ],
}


class LatticeGenerator:
    """
    Generates beam-based lattice structures within a bounding shape.

    Performance optimized with:
    - BOPAlgo_Builder for O(n) multi-shape fuse (primary)
    - Hierarchical fusing O(n log n) as fallback
    - Multi-threading enabled for parallel processing
    """

    @staticmethod
    def generate(solid, cell_type: str = "BCC", cell_size: float = 5.0,
                 beam_radius: float = 0.5, max_cells: int = 500,
                 progress_callback=None, shell_thickness: float = 0.0):
        """
        Generate a lattice structure within the bounding box of the solid,
        then intersect with the original solid.

        Args:
            solid: Build123d Solid to fill with lattice
            cell_type: One of "BCC", "FCC", "Octet", "Diamond"
            cell_size: Size of each unit cell in mm
            beam_radius: Radius of each beam strut in mm
            max_cells: Maximum number of cells (safety limit)
            progress_callback: Optional callable(percent: int, message: str)
            shell_thickness: If > 0, preserve outer shell with this wall thickness (mm)

        Returns:
            Build123d Solid of the lattice, or None on failure
        """
        if cell_type not in UNIT_CELLS:
            raise ValueError(f"Unknown cell type: {cell_type}. Use: {list(UNIT_CELLS.keys())}")

        try:
            from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Vec
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Common
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
            from OCP.gp import gp_Trsf
            import math

            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Get bounding box
            bb = solid.bounding_box()
            x_min, y_min, z_min = bb.min.X, bb.min.Y, bb.min.Z
            x_max, y_max, z_max = bb.max.X, bb.max.Y, bb.max.Z

            # Calculate cell counts
            nx = max(1, int(math.ceil((x_max - x_min) / cell_size)))
            ny = max(1, int(math.ceil((y_max - y_min) / cell_size)))
            nz = max(1, int(math.ceil((z_max - z_min) / cell_size)))

            total_cells = nx * ny * nz
            if total_cells > max_cells:
                logger.warning(
                    f"Lattice would need {total_cells} cells, limiting to {max_cells}. "
                    f"Increase cell_size or reduce body size."
                )
                # Scale down
                scale = (max_cells / total_cells) ** (1/3)
                nx = max(1, int(nx * scale))
                ny = max(1, int(ny * scale))
                nz = max(1, int(nz * scale))

            cell_edges = UNIT_CELLS[cell_type]

            # Validierung: beam_radius sollte deutlich kleiner als cell_size sein
            # Bei BCC ist die kürzeste Beam-Länge ca. 0.866 * cell_size (Diagonale zur Ecke)
            min_beam_length = 0.5 * math.sqrt(3) * cell_size  # ~0.866 * cell_size
            max_sensible_radius = min_beam_length / 4  # Beam sollte max 1/4 der Länge als Radius haben

            if beam_radius > max_sensible_radius:
                logger.warning(
                    f"Beam-Radius ({beam_radius}mm) ist sehr groß relativ zur Cell-Size ({cell_size}mm)! "
                    f"Empfohlen: max {max_sensible_radius:.1f}mm für sichtbare Gitterstruktur."
                )

            if beam_radius * 2 >= cell_size:
                logger.warning(
                    f"ACHTUNG: Beam-Durchmesser ({beam_radius * 2}mm) >= Cell-Size ({cell_size}mm). "
                    f"Beams werden komplett überlappen - keine Gitterstruktur sichtbar!"
                )

            # Beam-Anzahl vorab berechnen und limitieren
            estimated_beams = nx * ny * nz * len(cell_edges)
            MAX_BEAMS = 2000  # Sinnvolles Limit für Performance

            if estimated_beams > MAX_BEAMS:
                logger.warning(
                    f"Zu viele Beams ({estimated_beams}), reduziere auf max {MAX_BEAMS}. "
                    f"Erhöhe Cell-Size für bessere Performance."
                )
                # Skaliere Zellanzahl runter
                scale = (MAX_BEAMS / estimated_beams) ** (1/3)
                nx = max(1, int(nx * scale))
                ny = max(1, int(ny * scale))
                nz = max(1, int(nz * scale))
                estimated_beams = nx * ny * nz * len(cell_edges)

            logger.info(f"Lattice: {cell_type} {nx}x{ny}x{nz} cells, "
                        f"~{estimated_beams} beams, beam_r={beam_radius}mm")

            # Generate all beams
            beam_shapes = []
            for ix in range(nx):
                for iy in range(ny):
                    for iz in range(nz):
                        # Cell origin in world space
                        ox = x_min + ix * cell_size
                        oy = y_min + iy * cell_size
                        oz = z_min + iz * cell_size

                        for (sx, sy, sz), (ex, ey, ez) in cell_edges:
                            # World coordinates
                            p1 = (ox + sx * cell_size, oy + sy * cell_size, oz + sz * cell_size)
                            p2 = (ox + ex * cell_size, oy + ey * cell_size, oz + ez * cell_size)

                            beam = LatticeGenerator._make_beam(p1, p2, beam_radius)
                            if beam is not None:
                                beam_shapes.append(beam)

            if not beam_shapes:
                raise RuntimeError("No beams generated")

            total_beams = len(beam_shapes)
            logger.info(f"Fusing {total_beams} beams...")
            if progress_callback:
                progress_callback(5, f"Fusing {total_beams} beams...")

            # Fast fusing: Use BOPAlgo_Builder for general fuse (O(n) statt O(n²))
            result = LatticeGenerator._fast_fuse_shapes(beam_shapes, progress_callback)

            # Debug: Prüfe Beam-Fuse Ergebnis
            if result is not None and not result.IsNull():
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_FACE
                explorer = TopExp_Explorer(result, TopAbs_FACE)
                face_count = 0
                while explorer.More():
                    face_count += 1
                    explorer.Next()
                logger.info(f"Beam-Fuse Ergebnis: {face_count} Faces")
            else:
                logger.error("Beam-Fuse Ergebnis ist NULL!")

            from build123d import Solid

            # Shell: Außenhülle beibehalten und mit Lattice-Innenleben vereinigen
            if shell_thickness > 0:
                logger.info(f"Creating shell (thickness={shell_thickness}mm)...")
                if progress_callback:
                    progress_callback(90, "Creating outer shell...")

                try:
                    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
                    from OCP.BRepOffset import BRepOffset_Skin, BRepOffset_Mode
                    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
                    from OCP.GeomAbs import GeomAbs_Intersection

                    # 1. Inner shape erstellen (für Lattice-Schnitt)
                    # Versuche verschiedene Offset-Modi
                    inner_shape = None

                    for join_type in [GeomAbs_Intersection]:
                        try:
                            offset_builder = BRepOffsetAPI_MakeOffsetShape()
                            offset_builder.PerformByJoin(
                                shape,
                                -shell_thickness,
                                1e-2,  # Höhere Toleranz für Stabilität
                                BRepOffset_Skin,
                                False,  # Intersection
                                False,  # SelfInter
                                join_type
                            )

                            if offset_builder.IsDone():
                                inner_shape = offset_builder.Shape()
                                if inner_shape and not inner_shape.IsNull():
                                    logger.debug("Offset shape created successfully")
                                    break
                        except Exception as e:
                            logger.debug(f"Offset attempt failed: {e}")
                            continue

                    if inner_shape is None or inner_shape.IsNull():
                        logger.warning("Shell offset fehlgeschlagen - verwende Lattice ohne Shell")
                        # Fallback: Lattice nur mit Original schneiden
                        common = BRepAlgoAPI_Common(result, shape)
                        common.SetFuzzyValue(1e-3)
                        common.Build()
                        if common.IsDone():
                            lattice_result = common.Shape()
                            logger.info("Fallback: Lattice ohne Shell erstellt")
                        else:
                            raise RuntimeError("Lattice intersection failed")
                    else:
                        # 2. Lattice mit INNER shape schneiden
                        logger.info("Intersecting lattice with inner volume...")
                        if progress_callback:
                            progress_callback(92, "Intersecting with inner volume...")

                        common = BRepAlgoAPI_Common(result, inner_shape)
                        common.SetFuzzyValue(1e-2)
                        common.Build()

                        if not common.IsDone():
                            logger.warning("Inner intersection failed - using original body")
                            common = BRepAlgoAPI_Common(result, shape)
                            common.SetFuzzyValue(1e-3)
                            common.Build()

                        lattice_inner = common.Shape()

                        # Validiere lattice_inner
                        if lattice_inner is None or lattice_inner.IsNull():
                            logger.warning("Lattice-Inner-Schnitt leer - verwende Lattice mit Original")
                            common2 = BRepAlgoAPI_Common(result, shape)
                            common2.SetFuzzyValue(1e-3)
                            common2.Build()
                            if common2.IsDone():
                                lattice_inner = common2.Shape()

                        # 3. Shell = Original - Inner (Hohlkörper)
                        logger.info("Creating shell...")
                        if progress_callback:
                            progress_callback(95, "Creating shell...")

                        shell_cut = BRepAlgoAPI_Cut(shape, inner_shape)
                        shell_cut.SetFuzzyValue(1e-2)
                        shell_cut.Build()

                        if not shell_cut.IsDone() or shell_cut.Shape().IsNull():
                            logger.warning("Shell cut fehlgeschlagen - verwende Lattice ohne Shell")
                            # Prüfe ob lattice_inner überhaupt Inhalt hat
                            if lattice_inner is None or lattice_inner.IsNull():
                                logger.warning("Lattice-Inner auch leer - verwende direkten Schnitt")
                                common3 = BRepAlgoAPI_Common(result, shape)
                                common3.SetFuzzyValue(1e-3)
                                common3.Build()
                                if common3.IsDone():
                                    lattice_result = common3.Shape()
                                else:
                                    lattice_result = result  # Fallback: ungefilterte Beams
                            else:
                                lattice_result = lattice_inner
                        else:
                            # 4. Shell + Lattice vereinigen
                            logger.info("Fusing shell with lattice...")
                            if progress_callback:
                                progress_callback(97, "Fusing shell with lattice...")

                            final_fuse = BRepAlgoAPI_Fuse(shell_cut.Shape(), lattice_inner)
                            final_fuse.SetFuzzyValue(1e-2)
                            final_fuse.Build()

                            if final_fuse.IsDone() and not final_fuse.Shape().IsNull():
                                lattice_result = final_fuse.Shape()
                                logger.success(f"Shell + Lattice vereinigt (wall={shell_thickness}mm)")
                            else:
                                logger.warning("Shell+Lattice fuse failed - using lattice only")
                                lattice_result = lattice_inner

                except Exception as shell_err:
                    logger.warning(f"Shell-Erzeugung fehlgeschlagen: {shell_err} - verwende Lattice ohne Shell")
                    # Fallback: Lattice ohne Shell
                    common = BRepAlgoAPI_Common(result, shape)
                    common.SetFuzzyValue(1e-3)
                    common.Build()
                    if common.IsDone():
                        lattice_result = common.Shape()
                    else:
                        raise RuntimeError("Lattice generation completely failed")

            else:
                # Ohne Shell: Lattice mit Original schneiden
                logger.info("Intersecting lattice with body...")
                if progress_callback:
                    progress_callback(92, "Intersecting with body...")

                # Debug: Prüfe ob Beams und Body sich überhaupt überschneiden
                from OCP.GProp import GProp_GProps
                from OCP.BRepGProp import brepgprop

                props_body = GProp_GProps()
                brepgprop.VolumeProperties(shape, props_body)
                vol_body = props_body.Mass()

                props_beams = GProp_GProps()
                brepgprop.VolumeProperties(result, props_beams)
                vol_beams = props_beams.Mass()

                logger.info(f"Body Volume: {vol_body:.2f}mm³, Beams Volume: {vol_beams:.2f}mm³")

                common = BRepAlgoAPI_Common(result, shape)
                common.SetFuzzyValue(1e-2)  # Etwas toleranter
                common.SetRunParallel(True)
                common.Build()

                if not common.IsDone():
                    raise RuntimeError("Boolean Common (lattice ∩ body) failed")

                lattice_result = common.Shape()

                # Prüfe Volumen des Ergebnisses
                if lattice_result and not lattice_result.IsNull():
                    props_result = GProp_GProps()
                    brepgprop.VolumeProperties(lattice_result, props_result)
                    vol_result = props_result.Mass()
                    logger.info(f"Intersection Volume: {vol_result:.2f}mm³")

                    # Wenn Ergebnis-Volumen ~= Body-Volumen, hat Common nicht richtig funktioniert
                    if vol_result > 0.9 * vol_body:
                        logger.warning(
                            f"Boolean Common hat möglicherweise Original zurückgegeben! "
                            f"(Result {vol_result:.1f} ≈ Body {vol_body:.1f})"
                        )

                    # Wenn Ergebnis-Volumen ~= 0, ist keine Überschneidung vorhanden
                    if vol_result < 0.01 * vol_body:
                        logger.error(
                            f"Boolean Common ergab quasi leeres Volumen ({vol_result:.4f}mm³). "
                            f"Beams und Body überschneiden sich nicht korrekt."
                        )

            if progress_callback:
                progress_callback(98, "Finalizing...")

            # Validiere Ergebnis
            if lattice_result is None or lattice_result.IsNull():
                logger.error("Lattice result ist NULL - verwende gefusete Beams direkt")
                # Letzter Fallback: Beams direkt mit Body schneiden
                common_final = BRepAlgoAPI_Common(result, shape)
                common_final.SetFuzzyValue(1e-3)
                common_final.Build()
                if common_final.IsDone() and not common_final.Shape().IsNull():
                    lattice_result = common_final.Shape()
                else:
                    lattice_result = result  # Ungefilterte Beams als absoluter Fallback

            lattice_solid = Solid(lattice_result)

            # Prüfe ob Ergebnis Inhalt hat
            try:
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_FACE

                # Original Body Face-Count zum Vergleich
                orig_face_count = 0
                explorer = TopExp_Explorer(shape, TopAbs_FACE)
                while explorer.More():
                    orig_face_count += 1
                    explorer.Next()

                # Lattice Result Face-Count
                face_count = 0
                explorer = TopExp_Explorer(lattice_result, TopAbs_FACE)
                while explorer.More():
                    face_count += 1
                    explorer.Next()
                logger.info(f"Lattice result: {face_count} Faces (Original: {orig_face_count})")

                # Ein echter Lattice hat VIEL mehr Faces als der Original-Body
                # z.B. Box = 6 Faces, Lattice mit 50 Beams = ~600 Faces
                MIN_FACE_MULTIPLIER = 3  # Mindestens 3x so viele Faces

                if face_count <= orig_face_count * MIN_FACE_MULTIPLIER:
                    logger.error(
                        f"Lattice-Generierung fehlgeschlagen: Nur {face_count} Faces "
                        f"(erwartet >> {orig_face_count}). Boolean-Schnitt hat nicht funktioniert."
                    )
                    # Rückgabe None signalisiert Fehler
                    raise RuntimeError(
                        f"Lattice boolean intersection fehlgeschlagen. "
                        f"Ergebnis hat {face_count} Faces statt erwartet >{orig_face_count * MIN_FACE_MULTIPLIER}. "
                        f"Versuchen Sie kleinere Cell-Size oder größeren Beam-Radius."
                    )

                if face_count == 0:
                    logger.error("Lattice hat 0 Faces - Boolean-Schnitt fehlgeschlagen!")
                    raise RuntimeError("Lattice boolean intersection ergab 0 Faces")

            except RuntimeError:
                raise  # Re-raise our own errors
            except Exception as e:
                logger.debug(f"Face count check failed: {e}")

            if hasattr(lattice_solid, 'is_valid') and lattice_solid.is_valid():
                logger.success(f"Lattice generated: {cell_type}, {len(beam_shapes)} beams"
                               + (f", shell={shell_thickness}mm" if shell_thickness > 0 else ""))
                return lattice_solid
            else:
                logger.warning("Lattice result is invalid, returning raw shape")
                from build123d import Shape
                return Shape(lattice_result)

        except Exception as e:
            logger.error(f"Lattice generation failed: {e}")
            raise

    @staticmethod
    def _fast_fuse_shapes(shapes, progress_callback=None):
        """
        Fast multi-shape fuse using batched BOPAlgo_Builder.

        Bei vielen Shapes (>500) werden Batches verarbeitet, um
        Progress-Updates zu ermöglichen und Memory zu sparen.
        """
        from OCP.BOPAlgo import BOPAlgo_Builder
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

        # UI responsive halten
        def process_ui():
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            except:
                pass

        total = len(shapes)
        logger.info(f"Fast fuse: {total} shapes...")

        if total == 0:
            return None
        if total == 1:
            return shapes[0]

        # Bei vielen Shapes: Batch-Verarbeitung für Progress-Updates
        BATCH_SIZE = 200  # Shapes pro Batch

        if total > BATCH_SIZE:
            return LatticeGenerator._batched_fuse(shapes, BATCH_SIZE, progress_callback)

        # Wenige Shapes: Direkt mit BOPAlgo_Builder
        builder = BOPAlgo_Builder()
        builder.SetFuzzyValue(1e-3)
        builder.SetRunParallel(True)
        builder.SetNonDestructive(True)

        if progress_callback:
            progress_callback(10, f"Adding {total} shapes...")
            process_ui()

        for i, shape in enumerate(shapes):
            builder.AddArgument(shape)
            if i % 50 == 0:
                process_ui()

        if progress_callback:
            progress_callback(35, "Fusing shapes...")
            process_ui()

        logger.info("BOPAlgo_Builder.Perform()...")
        builder.Perform()

        if builder.HasErrors():
            logger.warning("BOPAlgo_Builder error, using hierarchical fuse")
            return LatticeGenerator._hierarchical_fuse(shapes, progress_callback)

        result = builder.Shape()
        if result is None or result.IsNull():
            logger.warning("BOPAlgo_Builder null result, using hierarchical fuse")
            return LatticeGenerator._hierarchical_fuse(shapes, progress_callback)

        logger.success(f"Fast fuse completed: {total} shapes")
        return result

    @staticmethod
    def _batched_fuse(shapes, batch_size, progress_callback=None):
        """
        Batch-Verarbeitung für viele Shapes mit Progress-Updates.

        1. Shapes in Batches aufteilen
        2. Jeden Batch mit BOPAlgo_Builder fussen
        3. Batch-Ergebnisse hierarchisch zusammenfügen
        """
        from OCP.BOPAlgo import BOPAlgo_Builder

        def process_ui():
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            except:
                pass

        total = len(shapes)
        n_batches = (total + batch_size - 1) // batch_size

        logger.info(f"Batched fuse: {total} shapes in {n_batches} batches...")

        batch_results = []

        for batch_idx in range(n_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, total)
            batch = shapes[start:end]

            # Progress update
            pct = int(10 + 60 * batch_idx / n_batches)
            if progress_callback:
                progress_callback(pct, f"Batch {batch_idx+1}/{n_batches} ({len(batch)} shapes)...")
                process_ui()

            logger.debug(f"Processing batch {batch_idx+1}/{n_batches}: {len(batch)} shapes")

            # Batch fussen
            if len(batch) == 1:
                batch_results.append(batch[0])
            else:
                builder = BOPAlgo_Builder()
                builder.SetFuzzyValue(1e-3)
                builder.SetRunParallel(True)
                builder.SetNonDestructive(True)

                for shape in batch:
                    builder.AddArgument(shape)

                builder.Perform()

                if builder.HasErrors() or builder.Shape() is None or builder.Shape().IsNull():
                    # Fallback für diesen Batch: hierarchisch
                    logger.debug(f"Batch {batch_idx+1} needs hierarchical fuse")
                    result = LatticeGenerator._hierarchical_fuse(batch, None)
                    if result:
                        batch_results.append(result)
                else:
                    batch_results.append(builder.Shape())

            process_ui()

        # Batch-Ergebnisse zusammenfügen
        if len(batch_results) == 0:
            return None
        if len(batch_results) == 1:
            return batch_results[0]

        if progress_callback:
            progress_callback(75, f"Merging {len(batch_results)} batch results...")
            process_ui()

        logger.info(f"Merging {len(batch_results)} batch results...")

        # Hierarchisch zusammenfügen (wenige Shapes = schnell)
        return LatticeGenerator._hierarchical_fuse(batch_results, progress_callback)

    @staticmethod
    def _hierarchical_fuse(shapes, progress_callback=None):
        """
        Fallback: Hierarchisches Fusing (O(n log n) statt O(n²)).

        Fused Paare von Shapes, dann die Ergebnisse, usw.
        Deutlich schneller als sequentielles Fusing bei vielen Shapes.
        """
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

        # UI responsive halten
        def process_ui():
            try:
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()
            except:
                pass

        total = len(shapes)
        logger.info(f"Hierarchical fuse: {total} shapes...")

        if total == 0:
            return None
        if total == 1:
            return shapes[0]

        current_shapes = list(shapes)
        iteration = 0

        while len(current_shapes) > 1:
            iteration += 1
            next_shapes = []

            # Fuse pairs
            for i in range(0, len(current_shapes), 2):
                if i + 1 < len(current_shapes):
                    # Fuse pair
                    fuse = BRepAlgoAPI_Fuse(current_shapes[i], current_shapes[i+1])
                    fuse.SetFuzzyValue(1e-3)
                    fuse.SetRunParallel(True)
                    fuse.Build()

                    if fuse.IsDone():
                        next_shapes.append(fuse.Shape())
                    else:
                        # Keep originals if fuse fails
                        next_shapes.append(current_shapes[i])
                        next_shapes.append(current_shapes[i+1])
                else:
                    # Odd one out - keep for next iteration
                    next_shapes.append(current_shapes[i])

                # UI nach jedem Paar aktualisieren
                if i % 20 == 0:
                    process_ui()

            current_shapes = next_shapes

            if progress_callback:
                # Log progress
                remaining = len(current_shapes)
                pct = int(35 + 50 * (1 - remaining / total))
                progress_callback(pct, f"Iteration {iteration}: {remaining} shapes remaining...")
                process_ui()

            logger.debug(f"Hierarchical fuse iteration {iteration}: {len(current_shapes)} shapes remaining")

        logger.success(f"Hierarchical fuse completed in {iteration} iterations")
        return current_shapes[0] if current_shapes else None

    @staticmethod
    def _make_beam(p1, p2, radius):
        """Create a cylinder beam between two points."""
        import math
        from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Trsf, gp_Vec
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform

        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        length = math.sqrt(dx*dx + dy*dy + dz*dz)

        if length < 1e-6:
            return None

        # Cylinder along direction
        direction = gp_Dir(dx/length, dy/length, dz/length)
        origin = gp_Pnt(p1[0], p1[1], p1[2])
        ax = gp_Ax2(origin, direction)

        cyl = BRepPrimAPI_MakeCylinder(ax, radius, length)
        cyl.Build()
        if cyl.IsDone():
            return cyl.Shape()
        return None
