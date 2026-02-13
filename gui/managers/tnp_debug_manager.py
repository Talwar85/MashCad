
from loguru import logger
from config.feature_flags import is_enabled

class TNPDebugManager:
    def __init__(self, parent):
        self.parent = parent

    def setup_callback(self):
        """
        TNP v4.0: Registriert Callback für Edge-Auflösungs-Visualisierung.
        Zeigt gefundene Kanten in GRÜN, nicht gefundene in ROT.
        """
        def tnp_debug_callback(resolved_edges, unresolved_shape_ids, body_id):
            if hasattr(self.parent, 'viewport_3d') and self.parent.viewport_3d:
                try:
                    if is_enabled("tnp_debug_logging"):
                        logger.info(f"TNP Debug: {len(resolved_edges)} resolved, {len(unresolved_shape_ids)} unresolved")
                    # Debug-Visualisierung deaktiviert (grüne/rote Linien)
                    # self.parent.viewport_3d.debug_visualize_edge_resolution(
                    #     resolved_edges, unresolved_shape_ids, body_id
                    # )
                except Exception as e:
                    import traceback
                    traceback.print_exc()
        
        # Callback im Document registrieren (immer setzen)
        if hasattr(self.parent, 'document') and self.parent.document:
            self.parent.document._tnp_debug_callback = tnp_debug_callback
