"""
MashCad - BRepFeat Operations
=============================

Lokale CAD-Operationen mit BRepFeat (OpenCASCADE).

Diese Operationen modifizieren Solids DIREKT ohne Boolean-Operationen,
was zu sauberer Topologie führt (keine zusätzlichen Kanten/Faces).

Verfügbare Operationen:
- MakePrism: Extrusion (Join/Cut)
- MakeDPrism: Extrusion mit Draft-Winkel
- MakeCylindricalHole: Zylindrische Bohrung
- MakeRevol: Rotation um Achse

Usage:
    from modeling.brepfeat_operations import (
        brepfeat_prism, brepfeat_dprism, brepfeat_hole, brepfeat_revol
    )

    result = brepfeat_prism(base_solid, face, height, fuse=True)
"""

import math
from typing import Optional, Tuple
from loguru import logger

try:
    from OCP.BRepFeat import (
        BRepFeat_MakePrism,
        BRepFeat_MakeDPrism,
        BRepFeat_MakeCylindricalHole,
        BRepFeat_MakeRevol
    )
    from OCP.gp import gp_Dir, gp_Ax1, gp_Pnt, gp_Vec
    from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Face, TopoDS_Solid
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from build123d import Solid
    HAS_OCP = True
except ImportError as e:
    logger.warning(f"BRepFeat imports failed: {e}")
    HAS_OCP = False


def _unify_same_domain(shape: 'TopoDS_Shape', context: str = "") -> 'TopoDS_Shape':
    """
    Wendet UnifySameDomain an um koplanare/kozylindrische Faces zu vereinen.

    Args:
        shape: OCP Shape
        context: Kontext für Logging

    Returns:
        Vereinigtes Shape (oder Original bei Fehler)
    """
    try:
        upgrader = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
        upgrader.SetLinearTolerance(0.01)   # 0.01mm
        upgrader.SetAngularTolerance(0.01)  # ~0.5°
        upgrader.Build()
        unified = upgrader.Shape()
        if unified and not unified.IsNull():
            logger.debug(f"UnifySameDomain ({context}): OK")
            return unified
    except Exception as e:
        logger.debug(f"UnifySameDomain ({context}): {e}")
    return shape


def _count_faces(shape: 'TopoDS_Shape') -> int:
    """Zählt die Faces in einem Shape."""
    count = 0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        count += 1
        exp.Next()
    return count


def _find_sketch_face(base_solid: 'TopoDS_Shape', profile_face: 'TopoDS_Face') -> Optional['TopoDS_Face']:
    """
    Findet die Face des Base-Solids, auf der das Profil liegt.

    Iteriert über alle Faces des Solids und prüft ob das Profil
    auf der gleichen Oberfläche liegt (koplanar für Planes,
    gleiche Achse für Zylinder, etc.).

    Returns:
        Die Sketch-Face des Base-Solids oder None
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder

    profile_adaptor = BRepAdaptor_Surface(profile_face)
    profile_type = profile_adaptor.GetType()

    exp = TopExp_Explorer(base_solid, TopAbs_FACE)
    while exp.More():
        candidate = TopoDS.Face_s(exp.Current())
        try:
            cand_adaptor = BRepAdaptor_Surface(candidate)
            if cand_adaptor.GetType() != profile_type:
                exp.Next()
                continue

            if profile_type == GeomAbs_Plane:
                p_plane = profile_adaptor.Plane()
                c_plane = cand_adaptor.Plane()
                p_ax = p_plane.Axis()
                c_ax = c_plane.Axis()
                # Gleiche Ebene: parallele Normalen + gleicher Abstand
                if p_ax.Direction().IsParallel(c_ax.Direction(), 1e-4):
                    dist = p_ax.Location().Distance(c_ax.Location())
                    # Projizierte Distanz entlang der Normalen
                    dx = c_ax.Location().X() - p_ax.Location().X()
                    dy = c_ax.Location().Y() - p_ax.Location().Y()
                    dz = c_ax.Location().Z() - p_ax.Location().Z()
                    d = p_ax.Direction()
                    proj_dist = abs(dx * d.X() + dy * d.Y() + dz * d.Z())
                    if proj_dist < 1e-3:
                        return candidate

            elif profile_type == GeomAbs_Cylinder:
                p_cyl = profile_adaptor.Cylinder()
                c_cyl = cand_adaptor.Cylinder()
                # Gleicher Zylinder: gleiche Achse + gleicher Radius
                if (abs(p_cyl.Radius() - c_cyl.Radius()) < 1e-3 and
                        p_cyl.Axis().Direction().IsParallel(c_cyl.Axis().Direction(), 1e-4)):
                    ax_dist = p_cyl.Axis().Location().Distance(c_cyl.Axis().Location())
                    if ax_dist < 1e-3:
                        return candidate
        except Exception:
            pass
        exp.Next()

    return None


def brepfeat_prism(
    base_solid: 'Solid',
    face: 'TopoDS_Face',
    height: float,
    fuse: bool = True,
    unify: bool = True,
    sketch_face: 'TopoDS_Face' = None
) -> Optional['Solid']:
    """
    Extrudiert eine Face mit BRepFeat_MakePrism (lokale Operation).

    Vorteile gegenüber Boolean:
    - Keine zusätzlichen Kanten an Übergängen
    - Zylindrische Faces bleiben intakt
    - Schneller bei komplexen Shapes

    Args:
        base_solid: Build123d Solid als Basis
        face: OCP Face die extrudiert werden soll
        height: Extrusionshöhe (positiv = in Normal-Richtung)
        fuse: True = Join/Fuse, False = Cut
        unify: UnifySameDomain anwenden
        sketch_face: Face des Base-Solids auf der das Profil liegt.
                     Wenn None, wird automatisch gesucht.

    Returns:
        Neues Solid oder None bei Fehler
    """
    if not HAS_OCP:
        return None

    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.gp import gp_Pnt

        # Face-Normal korrekt berechnen via Kreuzprodukt der Tangenten
        adaptor = BRepAdaptor_Surface(face)
        u_mid = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
        v_mid = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2

        pnt_out = gp_Pnt()
        d1u = gp_Vec()
        d1v = gp_Vec()
        adaptor.D1(u_mid, v_mid, pnt_out, d1u, d1v)
        normal_vec = d1u.Crossed(d1v)

        # Fallback: Plane-Normal wenn Kreuzprodukt degeneriert
        if normal_vec.Magnitude() < 1e-6:
            from OCP.GeomAbs import GeomAbs_Plane
            if adaptor.GetType() == GeomAbs_Plane:
                plane = adaptor.Plane()
                normal = plane.Axis().Direction()
            else:
                logger.warning("BRepFeat_MakePrism: Kann Normal nicht berechnen")
                return None
        else:
            normal_vec.Normalize()
            normal = gp_Dir(normal_vec)

        direction = gp_Dir(normal.X(), normal.Y(), normal.Z())
        fuse_mode = 1 if fuse else 0
        abs_height = abs(height)

        # Richtung umkehren wenn height negativ
        if height < 0:
            direction = gp_Dir(-normal.X(), -normal.Y(), -normal.Z())

        # Sketch-Face auf dem Base-Solid finden
        if sketch_face is None:
            sketch_face = _find_sketch_face(base_solid.wrapped, face)
            if sketch_face is None:
                sketch_face = face
                logger.debug("BRepFeat_MakePrism: Sketch-Face nicht auf Solid gefunden, nutze Profil-Face")

        logger.debug(f"BRepFeat_MakePrism: fuse={fuse}, height={abs_height:.2f}")

        prism = BRepFeat_MakePrism()
        prism.Init(
            base_solid.wrapped,  # Base shape
            face,                # Profile face
            sketch_face,         # Face des Base-Solids
            direction,           # Direction
            fuse_mode,           # 1=Fuse, 0=Cut
            False                # Modify (False = copy)
        )
        prism.Perform(abs_height)

        if not prism.IsDone():
            logger.debug("BRepFeat_MakePrism: IsDone() = False")
            return None

        result_shape = prism.Shape()

        if unify:
            result_shape = _unify_same_domain(result_shape, "MakePrism")

        result = Solid(result_shape)

        if not result.is_valid():
            logger.debug("BRepFeat_MakePrism: Ergebnis ungültig")
            return None

        faces_after = _count_faces(result_shape)
        logger.info(f"✅ BRepFeat_MakePrism: {faces_after} Faces, volume={result.volume:.2f}")
        return result

    except Exception as e:
        logger.warning(f"BRepFeat_MakePrism fehlgeschlagen: {e}")
        return None


def brepfeat_dprism(
    base_solid: 'Solid',
    face: 'TopoDS_Face',
    height: float,
    draft_angle: float,
    fuse: bool = True,
    unify: bool = True
) -> Optional['Solid']:
    """
    Extrudiert eine Face mit Draft-Winkel (BRepFeat_MakeDPrism).

    Kombiniert Extrusion + Draft in einer Operation.

    Args:
        base_solid: Build123d Solid als Basis
        face: OCP Face die extrudiert werden soll
        height: Extrusionshöhe
        draft_angle: Draft-Winkel in Grad (positiv = nach außen)
        fuse: True = Join/Fuse, False = Cut
        unify: UnifySameDomain anwenden

    Returns:
        Neues Solid oder None bei Fehler
    """
    if not HAS_OCP:
        return None

    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane

        # Face-Normal berechnen
        adaptor = BRepAdaptor_Surface(face)
        if adaptor.GetType() != GeomAbs_Plane:
            logger.warning("BRepFeat_MakeDPrism: Nur für planare Faces")
            return None

        plane = adaptor.Plane()
        normal = plane.Axis().Direction()
        direction = gp_Dir(normal.X(), normal.Y(), normal.Z())

        if height < 0:
            direction = gp_Dir(-normal.X(), -normal.Y(), -normal.Z())

        fuse_mode = 1 if fuse else 0
        abs_height = abs(height)
        angle_rad = math.radians(draft_angle)

        logger.debug(f"BRepFeat_MakeDPrism: height={abs_height:.2f}, draft={draft_angle}°")

        dprism = BRepFeat_MakeDPrism()
        dprism.Init(
            base_solid.wrapped,  # Base shape
            face,                # Profile face
            face,                # Sketch face
            angle_rad,           # Draft angle (radians)
            fuse_mode,           # 1=Fuse, 0=Cut
            False                # Modify
        )
        dprism.Perform(abs_height)

        if not dprism.IsDone():
            logger.debug("BRepFeat_MakeDPrism: IsDone() = False")
            return None

        result_shape = dprism.Shape()

        if unify:
            result_shape = _unify_same_domain(result_shape, "MakeDPrism")

        result = Solid(result_shape)

        if not result.is_valid():
            logger.debug("BRepFeat_MakeDPrism: Ergebnis ungültig")
            return None

        faces_after = _count_faces(result_shape)
        logger.info(f"✅ BRepFeat_MakeDPrism: {faces_after} Faces, draft={draft_angle}°")
        return result

    except Exception as e:
        logger.warning(f"BRepFeat_MakeDPrism fehlgeschlagen: {e}")
        return None


def brepfeat_cylindrical_hole(
    base_solid: 'Solid',
    position: Tuple[float, float, float],
    direction: Tuple[float, float, float],
    diameter: float,
    depth: float = 0  # 0 = through all
) -> Optional['Solid']:
    """
    Erstellt eine zylindrische Bohrung mit BRepFeat_MakeCylindricalHole.

    Vorteile gegenüber Boolean Cut:
    - Saubere zylindrische Faces
    - Bessere Performance
    - Automatische Through-All Berechnung

    Args:
        base_solid: Build123d Solid als Basis
        position: Startpunkt der Bohrung (x, y, z)
        direction: Bohrrichtung (normalisiert)
        diameter: Bohr-Durchmesser
        depth: Bohrtiefe (0 = through all)

    Returns:
        Neues Solid oder None bei Fehler
    """
    if not HAS_OCP:
        return None

    try:
        radius = diameter / 2.0

        # Richtung normalisieren
        dx, dy, dz = direction
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length < 1e-9:
            logger.warning("BRepFeat_MakeCylindricalHole: Ungültige Richtung")
            return None
        dx, dy, dz = dx/length, dy/length, dz/length

        # Achse erstellen
        origin = gp_Pnt(*position)
        axis_dir = gp_Dir(dx, dy, dz)
        axis = gp_Ax1(origin, axis_dir)

        logger.debug(f"BRepFeat_MakeCylindricalHole: D={diameter}, depth={depth}")

        hole = BRepFeat_MakeCylindricalHole()
        hole.Init(base_solid.wrapped, axis)

        if depth > 0:
            # Sackloch
            hole.PerformBlind(depth, radius)
        else:
            # Durchgangsbohrung
            hole.PerformThruNext(radius)

        # BRepFeat_MakeCylindricalHole hat keine IsDone() - prüfe direkt Shape()
        try:
            result_shape = hole.Shape()
            if result_shape is None or result_shape.IsNull():
                logger.debug("BRepFeat_MakeCylindricalHole: Shape ist Null")
                return None
        except Exception as shape_err:
            logger.debug(f"BRepFeat_MakeCylindricalHole: Shape() fehlgeschlagen: {shape_err}")
            return None

        result = Solid(result_shape)

        if not result.is_valid():
            logger.debug("BRepFeat_MakeCylindricalHole: Ergebnis ungültig")
            return None

        faces_after = _count_faces(result_shape)
        logger.info(f"✅ BRepFeat_MakeCylindricalHole: {faces_after} Faces, D={diameter}")
        return result

    except Exception as e:
        logger.warning(f"BRepFeat_MakeCylindricalHole fehlgeschlagen: {e}")
        return None


def brepfeat_revol(
    base_solid: 'Solid',
    face: 'TopoDS_Face',
    axis_origin: Tuple[float, float, float],
    axis_direction: Tuple[float, float, float],
    angle: float = 360.0,
    fuse: bool = True,
    unify: bool = True
) -> Optional['Solid']:
    """
    Rotiert eine Face um eine Achse mit BRepFeat_MakeRevol.

    Vorteile gegenüber Boolean:
    - Keine zusätzlichen Kanten
    - Bessere Topologie bei vollen 360°

    Args:
        base_solid: Build123d Solid als Basis
        face: OCP Face die rotiert werden soll
        axis_origin: Ursprung der Rotationsachse
        axis_direction: Richtung der Rotationsachse
        angle: Rotationswinkel in Grad (default: 360)
        fuse: True = Join/Fuse, False = Cut
        unify: UnifySameDomain anwenden

    Returns:
        Neues Solid oder None bei Fehler
    """
    if not HAS_OCP:
        return None

    try:
        # Achse erstellen
        origin = gp_Pnt(*axis_origin)

        dx, dy, dz = axis_direction
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length < 1e-9:
            logger.warning("BRepFeat_MakeRevol: Ungültige Achsen-Richtung")
            return None
        axis_dir = gp_Dir(dx/length, dy/length, dz/length)
        axis = gp_Ax1(origin, axis_dir)

        fuse_mode = 1 if fuse else 0
        angle_rad = math.radians(angle)

        logger.debug(f"BRepFeat_MakeRevol: angle={angle}°, fuse={fuse}")

        revol = BRepFeat_MakeRevol()
        revol.Init(
            base_solid.wrapped,  # Base shape
            face,                # Profile face
            face,                # Sketch face
            axis,                # Rotation axis
            fuse_mode,           # 1=Fuse, 0=Cut
            False                # Modify
        )
        revol.Perform(angle_rad)

        if not revol.IsDone():
            logger.debug("BRepFeat_MakeRevol: IsDone() = False")
            return None

        result_shape = revol.Shape()

        if unify:
            result_shape = _unify_same_domain(result_shape, "MakeRevol")

        result = Solid(result_shape)

        if not result.is_valid():
            logger.debug("BRepFeat_MakeRevol: Ergebnis ungültig")
            return None

        faces_after = _count_faces(result_shape)
        logger.info(f"✅ BRepFeat_MakeRevol: {faces_after} Faces, angle={angle}°")
        return result

    except Exception as e:
        logger.warning(f"BRepFeat_MakeRevol fehlgeschlagen: {e}")
        return None


def is_available() -> bool:
    """Prüft ob BRepFeat verfügbar ist."""
    return HAS_OCP
