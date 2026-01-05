import numpy as np
from build123d import *
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.gp import gp_Lin, gp_Pnt, gp_Dir

def pick_face_by_ray(solid_obj, ray_origin, ray_direction):
    """
    Schießt einen Strahl durch das echte CAD-Modell (nicht das Mesh!).
    Gibt die getroffene Face und den Schnittpunkt zurück.
    """
    if not solid_obj or not hasattr(solid_obj, "wrapped"):
        return None, None

    # Strahl definieren
    ocp_pnt = gp_Pnt(*ray_origin)
    ocp_dir = gp_Dir(*ray_direction)
    ocp_lin = gp_Lin(ocp_pnt, ocp_dir)

    # Intersector initialisieren
    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(solid_obj.wrapped, 1e-4) # 0.0001mm Toleranz
    intersector.Perform(ocp_lin, 0, float('inf')) # Von Kamera bis Unendlich

    if intersector.NbPnt() > 0:
        # Wir nehmen den ersten Treffer (kleinster Abstand zur Kamera)
        # Sortierung ist oft automatisch, aber wir holen den Index des kleinsten U Parameters
        min_u = float('inf')
        best_face_idx = -1
        
        for i in range(1, intersector.NbPnt() + 1):
            u = intersector.U(i)
            if u < min_u:
                min_u = u
                best_face_idx = i
        
        if best_face_idx != -1:
            # Face wieder in Build123d Objekt wandeln
            ocp_face = intersector.Face(best_face_idx)
            return Face(ocp_face), min_u
            
    return None, None