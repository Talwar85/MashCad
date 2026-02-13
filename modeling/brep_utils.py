import numpy as np
import numpy as np
from build123d import Face, Vector
from build123d import *  # Keep star import for other potential uses, but explicit import fixes pylint for used ones
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.gp import gp_Lin, gp_Pnt, gp_Dir
from OCP.BRep import BRep_Tool
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf

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
            return Face(ocp_face), min_u # Face is imported from build123d
            
    return None, None
    
    
def find_closest_face(solid_obj, target_point, tolerance=2.0):
    """
    Findet die CAD-Fläche, die einem Punkt am nächsten liegt.
    Löst das Problem bei importierten STLs, wo Mesh und BREP leicht abweichen.
    """
    if not solid_obj:
        return None

    # Sicherstellen, dass target_point ein Vektor ist
    if not isinstance(target_point, Vector): # Vector is imported from build123d
        target_point = Vector(target_point)

    best_face = None
    min_dist = float('inf')
    
    # OCP Punkt Konvertierung
    ocp_point = gp_Pnt(target_point.X, target_point.Y, target_point.Z)

    # Durch alle Faces iterieren
    for face in solid_obj.faces():
        try:
            # Hole die zugrundeliegende Geometrie (Surface)
            surf = BRep_Tool.Surface_s(face.wrapped)
            
            # Projiziere Punkt auf Surface
            proj = GeomAPI_ProjectPointOnSurf(ocp_point, surf)
            
            # Prüfen ob Projektion erfolgreich war
            if proj.NbPoints() > 0:
                dist = proj.LowerDistance()
                
                # Wir suchen das Minimum
                if dist < min_dist:
                    min_dist = dist
                    best_face = face
        except Exception:
            continue

    # Wenn der Abstand klein genug ist (Toleranz), Treffer zurückgeben
    if best_face and min_dist <= tolerance:
        return best_face
    
    return None