
import numpy as np
import pyvista as pv
from loguru import logger
import traceback

# --- OPTIONAL DEPENDENCIES ---
try:
    import pymeshlab as ml
    HAS_MESHLAB = True
except ImportError:
    HAS_MESHLAB = False

# FIX: Robuster Import für meshlib / mrmeshpy
HAS_MESHLIB = False
try:
    # Versuch 1: Standard (PyPI)
    import mrmeshpy as mm
    HAS_MESHLIB = True
except ImportError:
    try:
        # Versuch 2: Submodul (Conda / andere Strukturen)
        from meshlib import mrmeshpy as mm
        HAS_MESHLIB = True
    except ImportError:
        HAS_MESHLIB = False
        logger.warning("meshlib (mrmeshpy) nicht gefunden. SDF-Modus nicht verfügbar.")

from OCP.gp import gp_Pnt
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeSolid
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from build123d import Solid, Shape

class MeshToBREPConverter:
    """
    Smart Converter mit Hybrid-Strategie:
    1. 'Mechanical': Low Poly -> Direct Sewing -> Planar Simplify (Scharfe Kanten)
    2. 'Organic/SDF': Voxelization -> Marching Cubes -> Smooth BREP (Robust/Watertight)
    """
    
    def __init__(self):
        pass

    def _simplify_brep(self, ocp_shape):
        """Verschmilzt coplanare Flächen (Planar Simplification)."""
        try:
            upgrader = ShapeUpgrade_UnifySameDomain(ocp_shape, True, True, True)
            upgrader.SetLinearTolerance(1e-4) 
            upgrader.SetAngularTolerance(1e-4)
            upgrader.Build()
            return upgrader.Shape()
        except Exception as e:
            logger.warning(f"Simplifizierung fehlgeschlagen: {e}")
            return ocp_shape

    def _sew_mesh_to_brep(self, verts, faces, tolerance=0.1) -> Shape:
        """Kern-Logik: Erzeugt OCP Shell aus Vertices/Faces via Sewing."""
        try:
            sewing = BRepBuilderAPI_Sewing(tolerance)
            
            # Batch processing wäre schneller, aber hier elementweise für Stabilität
            for face_idx in faces:
                try:
                    # Punkte holen
                    p0 = gp_Pnt(*[float(c) for c in verts[face_idx[0]]])
                    p1 = gp_Pnt(*[float(c) for c in verts[face_idx[1]]])
                    p2 = gp_Pnt(*[float(c) for c in verts[face_idx[2]]])

                    poly = BRepBuilderAPI_MakePolygon()
                    poly.Add(p0); poly.Add(p1); poly.Add(p2)
                    poly.Close()

                    if poly.IsDone():
                        face_builder = BRepBuilderAPI_MakeFace(poly.Wire())
                        if face_builder.IsDone():
                            sewing.Add(face_builder.Face())
                except: continue

            sewing.Perform()
            sewed_shape = sewing.SewedShape()

            if sewed_shape.IsNull():
                return None
            
            return sewed_shape
        except Exception as e:
            logger.error(f"Sewing Error: {e}")
            return None

    def _convert_via_sdf(self, mesh: pv.PolyData, voxel_size=0.2) -> Shape:
        """
        SDF Workflow (via MeshLib):
        Robust gegen Löcher, Noise und Self-Intersections.
        """
        if not HAS_MESHLIB:
            logger.error("SDF Modus nicht verfügbar (Bibliothek fehlt)")
            return None
            
        logger.info(f"Starte SDF-Konvertierung (Voxel: {voxel_size}mm)...")
        
        try:
            # 1. PyVista -> MeshLib
            v_np = mesh.points.astype(np.float32)
            f_np = mesh.faces.reshape(-1, 4)[:, 1:4].astype(np.uint32)
            mmesh = mm.Mesh(mm.Vector3f(v_np), mm.Vector3ui(f_np)) # Effizienter Transfer
            
            # 2. Mesh -> SDF (Signed Distance Field)
            params = mm.MeshToVolumeParams()
            params.voxelSize = voxel_size
            params.surfaceOffset = 3
            
            # Auto-Detect ob geschlossen (Signed) oder offen (Unsigned)
            # Bei offenen Meshes schließt SDF die Löcher quasi "automatisch"
            if mmesh.topology.isClosed():
                params.type = mm.MeshToVolumeParams.Type.Signed
            else:
                params.type = mm.MeshToVolumeParams.Type.Unsigned
            
            volume = mm.meshToDistanceVdbVolume(mmesh, params)
            
            # 3. SDF -> Mesh (Marching Cubes)
            # isoValue=0.0 ist die exakte Oberfläche
            grid_settings = mm.GridToMeshSettings()
            grid_settings.voxelSize = voxel_size
            grid_settings.isoValue = 0.0 
            
            remeshed = mm.gridToMesh(volume.data, grid_settings)
            
            # 4. MeshLib -> Numpy -> Sewing
            # Wir nutzen keine Simplifizierung im SDF Modus, da die Topologie organisch ist
            out_verts = remeshed.points.toNumpyArray().astype(np.float64)
            out_faces = remeshed.topology.getAllFaces().toNumpyArray().reshape(-1, 3)
            
            logger.info(f"SDF Remeshing fertig: {len(out_faces)} Faces. Erzeuge BREP...")
            
            # Sewing mit etwas höherer Toleranz für die Marching Cubes
            sewed_shape = self._sew_mesh_to_brep(out_verts, out_faces, tolerance=1e-3)
            
            if sewed_shape:
                return Shape(sewed_shape)
            return None
            
        except Exception as e:
            logger.error(f"SDF Pipeline fehlgeschlagen: {e}")
            traceback.print_exc()
            return None

    def convert(self, mesh: pv.PolyData, target_faces=5000, method="auto", voxel_size=0.1) -> Solid:
        """
        Hauptmethode.
        :param method: 'auto', 'mechanical' (direct), 'organic' (sdf)
        :param voxel_size: Nur für SDF Modus relevant.
        """
        logger.info(f"Konvertiere Mesh ({mesh.n_cells} Faces) mit Modus: {method}")

        if not mesh.is_all_triangles:
            mesh = mesh.triangulate()

        # --- AUTO-DETECTION ---
        if method == "auto":
            # Heuristik: 
            # - Wenig Faces + Geschlossen -> Mechanical (scharfe Kanten behalten)
            # - Viele Faces oder Offen -> Organic (SDF zum Reparieren/Glätten)
            is_closed = mesh.n_open_edges == 0
            if mesh.n_cells < 4000 and is_closed:
                method = "mechanical"
            else:
                method = "organic"
                logger.info("Auto-Detect: Wähle Organic/SDF Modus (High-Poly oder Reparatur nötig)")

        # --- PFAD 1: SDF / ORGANIC (Neu) ---
        if method == "organic":
            if HAS_MESHLIB:
                shape = self._convert_via_sdf(mesh, voxel_size=voxel_size)
                if shape and shape.is_valid():
                    # Versuch Solid daraus zu machen
                    if shape.shape_type == "Shell":
                        try:
                            maker = BRepBuilderAPI_MakeSolid(shape.wrapped)
                            if maker.IsDone(): return Solid(maker.Solid())
                        except: pass
                    return shape
            else:
                logger.warning("SDF Modus angefordert, aber meshlib fehlt. Fallback zu Mechanical.")

        # --- PFAD 2: MECHANICAL / DIRECT (Legacy + MeshLab) ---
        # Vorbereitung der Daten (Simplification falls nötig)
        out_verts = []
        out_faces = []
        
        use_meshlab = (mesh.n_cells > target_faces) and HAS_MESHLAB

        if use_meshlab:
            # MeshLab Decimation (Quadric Edge Collapse behält scharfe Kanten besser als SDF)
            try:
                ms = ml.MeshSet()
                v = mesh.points.astype(np.float64)
                f = mesh.faces.reshape(-1, 4)[:, 1:4].astype(np.int32)
                ms.add_mesh(ml.Mesh(v, f))
                ms.meshing_decimation_quadric_edge_collapse(targetfacenum=target_faces)
                m = ms.current_mesh()
                out_verts = m.vertex_matrix()
                out_faces = m.face_matrix()
            except Exception as e:
                logger.warning(f"MeshLab fehlgeschlagen ({e}), nutze Originaldaten.")
                out_verts = mesh.points
                out_faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        else:
            out_verts = mesh.points
            out_faces = mesh.faces.reshape(-1, 4)[:, 1:4]

        # Sewing
        sewed_shape = self._sew_mesh_to_brep(out_verts, out_faces)
        if not sewed_shape: return None

        # Post-Processing: Planar Simplification (Wichtig für Mechanical!)
        logger.info("Optimiere planare Flächen...")
        simplified_shape = self._simplify_brep(sewed_shape)
        
        b3d_shape = Shape(simplified_shape)

        # Solid Check
        if b3d_shape.shape_type == "Shell":
            try:
                maker = BRepBuilderAPI_MakeSolid(simplified_shape)
                if maker.IsDone():
                    return Solid(maker.Solid())
                return b3d_shape.fix()
            except: pass

        return b3d_shape
