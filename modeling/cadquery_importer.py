"""
CadQuery Script Importer for MashCad

This module enables importing and executing CadQuery/Build123d scripts
to generate 3D geometry in MashCad.

Phases:
- Phase 1: Core Importer (script execution, security, solid extraction)
- Phase 2: In-App Script Editor (syntax highlighting, execute button)
- Phase 3: Parameter Extraction and UI
- Phase 4: CadQuery Workplane API compatibility

Usage:
    from modeling.cadquery_importer import CadQueryImporter
    from modeling import Document

    doc = Document('MyDoc')
    importer = CadQueryImporter(doc)

    # Execute script from string
    result = importer.execute_code(script, source='my_script.py')

    if result.success:
        for solid in result.solids:
            body = Body.from_solid(solid, name=result.name)
            doc.add_body(body)
"""

import re
import ast
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
from loguru import logger


class ResultStatus(Enum):
    """Status of a script execution result."""
    SUCCESS = auto()
    ERROR = auto()
    WARNING = auto()
    EMPTY = auto()


@dataclass
class ScriptResult:
    """Result of executing a CadQuery/Build123d script."""
    success: bool
    solids: List[Any] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    name: str = "CadQuery Import"
    status: ResultStatus = ResultStatus.SUCCESS

    @property
    def has_solids(self) -> bool:
        return len(self.solids) > 0

    @property
    def is_error(self) -> bool:
        return self.status == ResultStatus.ERROR


@dataclass
class ParameterInfo:
    """Information about an extracted parameter."""
    name: str
    value: float
    line: int
    description: str = ""


class CadQueryImporter:
    """
    Importer for CadQuery/Build123d scripts.

    Features:
    - Sandboxed script execution
    - Build123d API compatibility (auto-detects version)
    - CadQuery Workplane API compatibility (cq.Workplane)
    - Parameter extraction
    - Security scanning

    Example:
        doc = Document('MyDoc')
        importer = CadQueryImporter(doc)

        result = importer.execute_script('bracket.py')
        if result.success:
            for solid in result.solids:
                body = Body.from_solid(solid)
                doc.add_body(body)
    """

    # Dangerous modules that are blocked
    BLOCKED_MODULES = {
        'os', 'sys', 'subprocess', 'pathlib', 'shutil', 'tempfile',
        'eval', 'exec', 'compile', '__import__',
        'open', 'file', 'input', 'raw_input',
        'socket', 'urllib', 'requests', 'http',
        'pickle', 'shelve', 'marshal',
    }

    # Allowed Build123d API patterns
    ALLOWED_PATTERNS = [
        r'build123d',
        r'Box|Cylinder|Sphere|Cone',
        r'BuildPart|BuildSketch|BuildLine',
        r'extrude|revolve|loft|sweep',
        r'fillet|chamfer',
        r'Plane|Axis|Locations|Vector',
        r'Rectangle|Circle|Polygon|Polyline',
        r'Mode',
        r'cq\.',  # CadQuery compatibility
    ]

    def __init__(self, document):
        """
        Initialize the importer.

        Args:
            document: MashCad Document instance
        """
        self.document = document
        self._build123d_version = None
        self._namespace_cache = None

        # Check Build123d availability
        try:
            import build123d
            self._build123d_version = getattr(build123d, '__version__', 'unknown')
            logger.debug(f"[CadQuery] Build123d {self._build123d_version} detected")
        except ImportError:
            logger.warning("[CadQuery] Build123d not found - script execution will fail")

    def execute_script(self, filepath: str) -> ScriptResult:
        """
        Execute a CadQuery/Build123d script from file.

        Args:
            filepath: Path to the .py file

        Returns:
            ScriptResult with solids and status
        """
        path = Path(filepath)
        if not path.exists():
            return ScriptResult(
                success=False,
                errors=[f"File not found: {filepath}"],
                status=ResultStatus.ERROR
            )

        try:
            code = path.read_text(encoding='utf-8')
            return self.execute_code(code, source=path.name)
        except Exception as e:
            return ScriptResult(
                success=False,
                errors=[f"Failed to read file: {e}"],
                status=ResultStatus.ERROR
            )

    def execute_code(self, code: str, source: str = "<script>") -> ScriptResult:
        """
        Execute CadQuery/Build123d code directly.

        Args:
            code: Python code string
            source: Source identifier for error messages

        Returns:
            ScriptResult with solids and status
        """
        # Security check
        security_result = self._scan_for_dangerous_code(code)
        if security_result:
            return ScriptResult(
                success=False,
                errors=[f"Security check failed: {security_result}"],
                status=ResultStatus.ERROR
            )

        # Create namespace
        namespace = self._create_namespace()

        # Execute code
        try:
            exec(code, namespace)

            # Extract solids
            solids = self._extract_solids(namespace)

            if not solids:
                return ScriptResult(
                    success=True,
                    name=Path(source).stem if source != "<script>" else "CadQuery",
                    solids=[],
                    warnings=["No solids were generated"],
                    status=ResultStatus.EMPTY
                )

            logger.success(f"Script executed successfully, generated {len(solids)} solid(s)")
            return ScriptResult(
                success=True,
                name=Path(source).stem if source != "<script>" else "CadQuery",
                solids=solids,
                status=ResultStatus.SUCCESS
            )

        except Exception as e:
            logger.error(f"Script execution failed:\n{e}")
            return ScriptResult(
                success=False,
                errors=[f"Script execution failed: {e}"],
                status=ResultStatus.ERROR
            )

    def _create_namespace(self) -> Dict[str, Any]:
        """
        Create execution namespace with Build123d API.

        Returns:
            Dictionary with available modules and functions
        """
        if self._namespace_cache is not None:
            return self._namespace_cache.copy()

        # Create safe __import__ that only allows specific modules
        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            """Restricted import that only allows build123d and math."""
            allowed_modules = {'build123d', 'math', 'typing'}
            base_name = name.split('.')[0]

            if base_name not in allowed_modules:
                raise ImportError(f"Module '{name}' is not allowed in CadQuery scripts")

            # Use the real __import__
            return __import__(name, globals, locals, fromlist, level)

        namespace = {
            '__builtins__': {
                '__import__': safe_import,
                'abs': abs,
                'all': all,
                'any': any,
                'bin': bin,
                'bool': bool,
                'dict': dict,
                'enumerate': enumerate,
                'filter': filter,
                'float': float,
                'hex': hex,
                'int': int,
                'isinstance': isinstance,
                'list': list,
                'map': map,
                'max': max,
                'min': min,
                'oct': oct,
                'ord': ord,
                'pow': pow,
                'range': range,
                'reversed': reversed,
                'round': round,
                'set': set,
                'sorted': sorted,
                'str': str,
                'sum': sum,
                'tuple': tuple,
                'zip': zip,
                'len': len,
            }
        }

        try:
            import build123d as b123

            # Core Build123d classes
            core_items = [
                'Box', 'Cylinder', 'Sphere', 'Cone', 'Wedge', 'Torus',
                'BuildPart', 'BuildSketch', 'BuildLine',
                'extrude', 'revolve', 'loft', 'sweep',
                'fillet', 'chamfer', 'offset',
                'Plane', 'Axis', 'Locations', 'Vector', 'Location',
                'Rectangle', 'Circle', 'Polygon', 'Polyline', 'Ellipse',
                'Mode', 'Align',
                'Part', 'Sketch',
                'Solid', 'Face', 'Edge', 'Wire', 'Vertex',
                'BoundBox',
                'make_face',
            ]

            for name in core_items:
                if hasattr(b123, name):
                    namespace[name] = getattr(b123, name)

            # Add 'b' as alias for build123d
            namespace['b'] = b123
            namespace['build123d'] = b123

            # Math functions
            import math
            namespace['math'] = math

            logger.debug("[CadQuery] Build123d namespace loaded")

        except ImportError as e:
            logger.error(f"[CadQuery] Failed to import Build123d: {e}")

        # Add CadQuery Workplane compatibility (Phase 4)
        try:
            from modeling.cadquery_compat import WorkplaneAdapter, create_cadquery_namespace

            import build123d as b123
            adapter = WorkplaneAdapter(b123)

            # Create cq pseudo-module
            class CadQueryModule:
                """Pseudo-module for CadQuery compatibility."""

                def __init__(self, adapter):
                    self._adapter = adapter

                @property
                def Workplane(self):
                    return lambda plane='XY': self._adapter.Workplane(plane)

            namespace['cq'] = CadQueryModule(adapter)
            logger.debug("[CadQuery] Workplane compatibility enabled")

        except ImportError as e:
            logger.debug(f"[CadQuery] Workplane compat not available: {e}")

        self._namespace_cache = namespace.copy()
        return namespace

    def _extract_solids(self, namespace: Dict[str, Any]) -> List[Any]:
        """
        Extract solids from the execution namespace.

        Looks for:
        - Variables with Solid objects
        - BuildPart context results
        - Workplane.val() results

        Args:
            namespace: Execution namespace dict

        Returns:
            List of Build123d Solid objects
        """
        solids = []

        def is_valid_solid(obj):
            """Check if object is a valid Build123d solid."""
            if obj is None:
                return False
            try:
                import build123d
                # Check for Solid class or wrapped shape
                if isinstance(obj, build123d.Solid):
                    return True
                if hasattr(obj, 'wrapped'):
                    from OCP.TopoDS import TopoDS_Solid
                    shape = obj.wrapped
                    if shape and not shape.IsNull():
                        return True
            except:
                pass
            return False

        # Look for solids in variables
        for name, value in namespace.items():
            if name.startswith('_'):
                continue

            # Direct solid
            if is_valid_solid(value):
                solids.append(value)
                logger.debug(f"[CadQuery] Found solid in variable: {name}")

            # Workplane object - call .val()
            elif hasattr(value, '_operations') and hasattr(value, 'val'):
                try:
                    obj = value.val()
                    if is_valid_solid(obj):
                        solids.append(obj)
                        logger.debug(f"[CadQuery] Found Workplane solid: {name}")
                except Exception as e:
                    logger.debug(f"[CadQuery] Failed to get .val() from {name}: {e}")

            # Part/BuildPart result
            elif hasattr(value, '_obj') or hasattr(value, 'part'):
                try:
                    obj = getattr(value, '_obj', None) or getattr(value, 'part', None)
                    if is_valid_solid(obj):
                        solids.append(obj)
                        logger.debug(f"[CadQuery] Found Part solid: {name}")
                except:
                    pass

        return solids

    def _scan_for_dangerous_code(self, code: str) -> Optional[str]:
        """
        Scan code for dangerous operations.

        Args:
            code: Python code string

        Returns:
            Error message if dangerous code found, None otherwise
        """
        tree = ast.parse(code)

        for node in ast.walk(tree):
            # Check for dangerous imports
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    module = alias.name.split('.')[0]
                    if module in self.BLOCKED_MODULES:
                        return f"Blocked module: {module}"

            # Check for dangerous function calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.BLOCKED_MODULES:
                        return f"Blocked function: {node.func.id}"

        return None

    def extract_parameters(self, code: str) -> List[ParameterInfo]:
        """
        Extract parameter definitions from script.

        Looks for variable assignments at the top of the script:
            length = 100
            width = 50

        Args:
            code: Python code string

        Returns:
            List of ParameterInfo objects
        """
        parameters = []

        try:
            tree = ast.parse(code)

            for i, node in enumerate(tree.body):
                # Only look at top-level assignments
                if not isinstance(node, ast.Assign):
                    continue

                # Stop at first non-assignment (end of parameter section)
                if i > 0 and not isinstance(tree.body[i-1], ast.Assign):
                    break

                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id

                        # Try to evaluate the value
                        try:
                            value = ast.literal_eval(node.value)
                            if isinstance(value, (int, float)):
                                parameters.append(ParameterInfo(
                                    name=name,
                                    value=float(value),
                                    line=node.lineno,
                                    description=name.replace('_', ' ').title()
                                ))
                        except:
                            pass

        except SyntaxError:
            pass

        return parameters

    def create_bodies_from_solids(self, solids: List[Any], name: str = "CadQuery Import", script_source: str = "") -> List:
        """
        Create Body objects from Build123d solids with ImportFeature.

        Args:
            solids: List of Build123d Solid objects
            name: Base name for the bodies
            script_source: Source script filename for reference

        Returns:
            List of Body objects with ImportFeature attached
        """
        from modeling import Body
        from modeling.features import ImportFeature
        from OCP.BRepTools import BRepTools
        import io

        bodies = []
        for i, solid in enumerate(solids):
            body_name = f"{name}_{i+1}" if len(solids) > 1 else name
            body = Body(body_name, document=self.document)

            # Serialize solid to BREP string for ImportFeature
            brep_string = ""
            try:
                stream = io.BytesIO()
                BRepTools.Write_s(solid.wrapped, stream)
                brep_string = stream.getvalue().decode('utf-8')
            except Exception as e:
                logger.warning(f"Failed to serialize solid for feature: {e}")

            # Create ImportFeature
            feature = ImportFeature(
                name=f"Import {script_source or name}",
                brep_string=brep_string,
                source_file=script_source,
                source_type="cadquery_script"
            )

            # Add feature to body
            body.features.append(feature)

            # Set the solid
            body._build123d_solid = solid
            body.invalidate_mesh()

            bodies.append(body)

        return bodies


def execute_script_file(filepath: str, document) -> ScriptResult:
    """
    Convenience function to execute a script file.

    Args:
        filepath: Path to .py file
        document: Document instance

    Returns:
        ScriptResult
    """
    importer = CadQueryImporter(document)
    return importer.execute_script(filepath)
