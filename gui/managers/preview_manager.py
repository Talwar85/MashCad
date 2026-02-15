
from loguru import logger
from gui.viewport.render_queue import request_render

class PreviewManager:
    def __init__(self, parent):
        self.parent = parent
        self._preview_actor_groups = {}

    def track_actor(self, group: str, actor_name: str):
        """Registriert einen Preview-Aktor in einer Gruppe für konsistentes Cleanup."""
        if not group or not actor_name:
            return
        group_actors = self._preview_actor_groups.setdefault(group, set())
        group_actors.add(actor_name)

    def clear_group(self, group: str, *, render: bool = True):
        """Entfernt alle Preview-Aktoren einer Gruppe."""
        if not group:
            return
        names = list(self._preview_actor_groups.get(group, set()))
        if not names:
            return

        plotter = getattr(getattr(self.parent, "viewport_3d", None), "plotter", None)
        removed_any = False
        if plotter:
            for actor_name in names:
                try:
                    plotter.remove_actor(actor_name)
                    removed_any = True
                except Exception:
                    pass

        self._preview_actor_groups[group] = set()
        if removed_any and render and plotter:
            try:
                request_render(plotter)
            except Exception:
                pass

    def clear_all(self, *, render: bool = True):
        """Entfernt alle registrierten Preview-Aktoren."""
        if not self._preview_actor_groups:
            return

        for group in list(self._preview_actor_groups.keys()):
            self.clear_group(group, render=False)

        if render:
            plotter = getattr(getattr(self.parent, "viewport_3d", None), "plotter", None)
            if plotter:
                try:
                    request_render(plotter)
                except Exception:
                    pass

    def clear_transient_previews(self, reason: str = "", *, clear_interaction_modes: bool = False):
        """
        Zentrales Cleanup für flüchtige Previews/Highlights beim Tool- oder Mode-Wechsel.

        Entfernt sowohl MainWindow-seitig registrierte Preview-Aktoren als auch
        viewport-interne Vorschauen (Extrude/Revolve/Hole/Thread/Draft/Split/Offset).
        """
        if reason:
            logger.debug(f"[preview] clear transient previews: {reason}")

        self.clear_all(render=False)

        viewport = getattr(self.parent, "viewport_3d", None)
        if viewport is None:
            return

        clear_methods = (
            "clear_draft_preview",
            "clear_split_preview_meshes",
            "clear_revolve_preview",
            "clear_hole_preview",
            "clear_thread_preview",
            "clear_offset_plane_preview",
            "_clear_preview",
        )
        for method_name in clear_methods:
            method = getattr(viewport, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception as e:
                    # logger.warning(f"Failed to call {method_name}: {e}")
                    pass

        if clear_interaction_modes:
            self._clear_interaction_modes(viewport)

        plotter = getattr(viewport, "plotter", None)
        if plotter:
            try:
                request_render(plotter)
            except Exception:
                pass

    def _clear_interaction_modes(self, viewport):
        """Helper to clear interaction modes on the viewport."""
        mode_calls = (
            ("set_pending_transform_mode", False),
            ("set_plane_select_mode", False),
            ("set_offset_plane_mode", False),
            ("set_split_mode", False),
            ("set_draft_mode", False),
            ("set_revolve_mode", False),
            ("set_hole_mode", False),
            ("set_thread_mode", False),
        )
        for method_name, value in mode_calls:
            method = getattr(viewport, method_name, None)
            if callable(method):
                try:
                    method(value)
                except Exception:
                    pass

        set_extrude_mode = getattr(viewport, "set_extrude_mode", None)
        if callable(set_extrude_mode):
            try:
                set_extrude_mode(False)
            except Exception:
                pass

        for method_name in ("stop_sketch_path_mode", "stop_edge_selection_mode", "stop_texture_face_mode"):
            method = getattr(viewport, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass

        try:
            viewport.measure_mode = False
        except Exception:
            pass
