"""
MashCAD - Print Quality Overlay
================================

Viewport overlay for print-orientation preview.

Shows:
- rotated ghost preview of the recommended orientation
- color-coded print risk based on downward-facing surface normals
- optional support fin preview geometry
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from loguru import logger

from gui.viewport.render_queue import request_render

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False


class PrintQualityOverlay:
    """Manage temporary print-quality preview actors inside the viewport."""

    OVERLAY_ACTOR = "print_quality_overlay_mesh"
    SUPPORT_ACTOR = "print_quality_overlay_support"
    PREVIEW_EDGE_ACTOR = "print_quality_overlay_edges"

    def __init__(self, viewport):
        self.viewport = viewport
        self.plotter = getattr(viewport, "plotter", None)
        self._actor_names: list[str] = []
        self._active_body_id: Optional[str] = None
        self._original_opacity: Optional[float] = None

    def show_preview(
        self,
        body: Any,
        candidate: Any,
        *,
        recommendation: Any = None,
        fin_proposal: Any = None,
    ) -> bool:
        """Show a rotated print preview overlay for a body."""
        if not HAS_PYVISTA or self.plotter is None or body is None or candidate is None:
            return False

        mesh = self._resolve_body_mesh(body)
        if mesh is None or getattr(mesh, "n_cells", 0) == 0:
            logger.warning("Print quality overlay skipped: no mesh available")
            return False

        self.clear(render=False)

        body_id = getattr(body, "id", None)
        rotated_mesh = self._rotate_mesh(mesh, candidate)
        if rotated_mesh is None or rotated_mesh.n_cells == 0:
            return False

        risk_mesh = self._build_risk_mesh(rotated_mesh)
        if risk_mesh is None or risk_mesh.n_cells == 0:
            return False

        if body_id is not None and hasattr(self.viewport, "set_body_opacity"):
            body_state = getattr(self.viewport, "bodies", {}).get(body_id, {})
            self._original_opacity = float(body_state.get("opacity", 1.0))
            self.viewport.set_body_opacity(body_id, 0.18)
            self._active_body_id = body_id

        self.plotter.add_mesh(
            risk_mesh,
            scalars="print_risk",
            cmap="RdYlGn_r",
            clim=[0.0, 90.0],
            opacity=0.78,
            smooth_shading=True,
            show_edges=False,
            pickable=False,
            name=self.OVERLAY_ACTOR,
        )
        self._actor_names.append(self.OVERLAY_ACTOR)

        try:
            edge_mesh = risk_mesh.extract_feature_edges(feature_angle=35.0)
            if edge_mesh is not None and getattr(edge_mesh, "n_lines", 0) > 0:
                self.plotter.add_mesh(
                    edge_mesh,
                    color="#e0e0e0",
                    opacity=0.30,
                    line_width=1,
                    pickable=False,
                    name=self.PREVIEW_EDGE_ACTOR,
                )
                self._actor_names.append(self.PREVIEW_EDGE_ACTOR)
        except Exception as e:
            logger.debug(f"Print quality edge overlay failed: {e}")

        support_mesh = self._extract_support_cells(risk_mesh)
        if support_mesh is not None and getattr(support_mesh, "n_cells", 0) > 0:
            self.plotter.add_mesh(
                support_mesh,
                color="#ff9800",
                opacity=0.26,
                show_edges=False,
                pickable=False,
                name=self.SUPPORT_ACTOR,
            )
            self._actor_names.append(self.SUPPORT_ACTOR)

        self._add_fin_preview(body, candidate, fin_proposal)

        request_render(self.plotter, immediate=True)
        logger.info(
            "Print quality overlay shown for body {} ({})".format(
                getattr(body, "name", body_id or "<unknown>"),
                getattr(candidate, "description", "preview"),
            )
        )
        return True

    def clear(self, *, render: bool = True) -> None:
        """Clear all preview actors and restore body appearance."""
        if self.plotter is None:
            return

        for actor_name in list(self._actor_names):
            try:
                self.plotter.remove_actor(actor_name, render=False)
            except Exception as e:
                logger.debug(f"Print quality overlay cleanup skipped for {actor_name}: {e}")
        self._actor_names.clear()

        if (
            self._active_body_id is not None
            and hasattr(self.viewport, "set_body_opacity")
            and self._original_opacity is not None
        ):
            try:
                self.viewport.set_body_opacity(self._active_body_id, self._original_opacity)
            except Exception as e:
                logger.debug(f"Print quality opacity restore failed: {e}")

        self._active_body_id = None
        self._original_opacity = None

        if render:
            request_render(self.plotter, immediate=True)

    def _resolve_body_mesh(self, body: Any):
        body_id = getattr(body, "id", None)

        if body_id is not None and hasattr(self.viewport, "get_body_mesh"):
            mesh = self.viewport.get_body_mesh(body_id)
            if mesh is not None:
                try:
                    return mesh.copy(deep=True)
                except TypeError:
                    return mesh.copy()

        solid = getattr(body, "_build123d_solid", None)
        if solid is None:
            solid = body

        try:
            from modeling.cad_tessellator import CADTessellator

            mesh, _ = CADTessellator.tessellate(solid)
            if mesh is not None:
                try:
                    return mesh.copy(deep=True)
                except TypeError:
                    return mesh.copy()
        except Exception as e:
            logger.debug(f"Print quality overlay tessellation fallback failed: {e}")

        return None

    def _rotate_mesh(self, mesh, candidate: Any):
        try:
            matrix = np.asarray(candidate.get_rotation_matrix(), dtype=float)
            rotated = mesh.copy(deep=True)
            rotated.points = np.asarray(rotated.points) @ matrix.T
            return rotated
        except Exception as e:
            logger.debug(f"Print quality mesh rotation failed: {e}")
            return None

    def _build_risk_mesh(self, mesh):
        try:
            risk_mesh = mesh.extract_surface(algorithm="dataset_surface").triangulate()
            risk_mesh = risk_mesh.compute_normals(
                cell_normals=True,
                point_normals=False,
                inplace=False,
                split_vertices=False,
                consistent_normals=False,
                auto_orient_normals=False,
            )
            normals = np.asarray(risk_mesh.cell_data.get("Normals"))
            if normals.size == 0:
                risk_mesh.cell_data["print_risk"] = np.zeros(risk_mesh.n_cells)
                return risk_mesh

            downward = np.clip(-normals[:, 2], 0.0, 1.0)
            risk_mesh.cell_data["print_risk"] = downward * 90.0
            return risk_mesh
        except Exception as e:
            logger.debug(f"Print quality risk mesh creation failed: {e}")
            return None

    def _extract_support_cells(self, risk_mesh):
        try:
            risk = np.asarray(risk_mesh.cell_data.get("print_risk"))
            if risk.size == 0:
                return None
            cell_ids = np.where(risk >= 45.0)[0]
            if cell_ids.size == 0:
                return None
            return risk_mesh.extract_cells(cell_ids).extract_surface(algorithm="dataset_surface")
        except Exception as e:
            logger.debug(f"Print quality support extraction failed: {e}")
            return None

    def _add_fin_preview(self, body: Any, candidate: Any, fin_proposal: Any) -> None:
        if fin_proposal is None or not getattr(fin_proposal, "regions", None):
            return

        solid = getattr(body, "_build123d_solid", None)
        if solid is None:
            return

        try:
            from modeling.cad_tessellator import CADTessellator
            from modeling.print_support_fins import generate_fins

            fin_solids = generate_fins(solid, fin_proposal)
            for idx, fin_solid in enumerate(fin_solids[:32]):
                fin_mesh, _ = CADTessellator.tessellate(fin_solid)
                if fin_mesh is None or getattr(fin_mesh, "n_cells", 0) == 0:
                    continue

                rotated_fin = self._rotate_mesh(fin_mesh, candidate)
                if rotated_fin is None:
                    continue

                actor_name = f"print_quality_fin_{idx}"
                self.plotter.add_mesh(
                    rotated_fin,
                    color="#00bcd4",
                    opacity=0.42,
                    smooth_shading=True,
                    show_edges=False,
                    pickable=False,
                    name=actor_name,
                )
                self._actor_names.append(actor_name)
        except Exception as e:
            logger.debug(f"Print fin preview generation failed: {e}")
