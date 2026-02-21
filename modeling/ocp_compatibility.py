"""
MashCAD - OCP API Compatibility Validation
============================================

CH-006: OCP API Compatibility Validation for Sprint 1

Provides validation and version checking for OpenCASCADE (OCP) API compatibility.
Handles version differences gracefully and provides clear error messages.

Usage:
    from modeling.ocp_compatibility import (
        check_ocp_availability,
        get_ocp_version,
        validate_ocp_api,
        ocp_api_guard,
        OCP_COMPATIBILITY
    )
    
    # Check availability
    if not check_ocp_availability():
        raise RuntimeError("OCP not available")
    
    # Get version info
    version = get_ocp_version()
    print(f"OCP Version: {version.version_string}")
    
    # Validate required APIs
    issues = validate_ocp_api()
    for issue in issues:
        logger.warning(f"API Issue: {issue}")
    
    # Use decorator for graceful failure
    @ocp_api_guard(fallback=None)
    def some_ocp_operation():
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        ...

Author: Claude (CH-006 Implementation)
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Any, Callable, TypeVar, Set
from functools import wraps
import sys
import platform
from loguru import logger

# Type variable for generic decorator
T = TypeVar('T')


class ApiSeverity(Enum):
    """Severity level for API compatibility issues."""
    CRITICAL = "critical"      # Operation cannot proceed
    WARNING = "warning"        # Degraded functionality
    INFO = "info"              # Minor difference, no impact


@dataclass
class ApiCompatibilityIssue:
    """
    Represents a single API compatibility issue.
    
    Attributes:
        api_name: Name of the OCP class/method
        severity: How severe the issue is
        message: Human-readable description
        suggestion: Suggested fix or workaround
        platform_info: Platform-specific notes (Windows, Linux, macOS)
    """
    api_name: str
    severity: ApiSeverity
    message: str
    suggestion: str = ""
    platform_info: str = ""
    
    def __str__(self) -> str:
        parts = [f"[{self.severity.value.upper()}] {self.api_name}: {self.message}"]
        if self.suggestion:
            parts.append(f"  Suggestion: {self.suggestion}")
        if self.platform_info:
            parts.append(f"  Platform: {self.platform_info}")
        return "\n".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "api_name": self.api_name,
            "severity": self.severity.value,
            "message": self.message,
            "suggestion": self.suggestion,
            "platform_info": self.platform_info,
        }


@dataclass
class OCPVersionInfo:
    """
    OCP/OpenCASCADE version information.
    
    Attributes:
        available: Whether OCP is available
        version_string: Full version string (e.g., "7.8.1")
        major: Major version number
        minor: Minor version number
        patch: Patch version number
        ocp_package_version: Python package version (if different from OCCT)
        python_version: Python version string
        platform: Operating system
        build_info: Additional build information
    """
    available: bool = False
    version_string: str = "unknown"
    major: int = 0
    minor: int = 0
    patch: int = 0
    ocp_package_version: str = "unknown"
    python_version: str = ""
    platform: str = ""
    build_info: str = ""
    
    def __str__(self) -> str:
        if not self.available:
            return "OCP not available"
        return f"OCP {self.version_string} (Package: {self.ocp_package_version})"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "available": self.available,
            "version_string": self.version_string,
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
            "ocp_package_version": self.ocp_package_version,
            "python_version": self.python_version,
            "platform": self.platform,
            "build_info": self.build_info,
        }
    
    def is_at_least(self, major: int, minor: int = 0, patch: int = 0) -> bool:
        """Check if version is at least the specified version."""
        if not self.available:
            return False
        return (self.major, self.minor, self.patch) >= (major, minor, patch)


# =============================================================================
# Required OCP APIs Definition
# =============================================================================

REQUIRED_OCP_APIS: Dict[str, Dict[str, Any]] = {
    # Primitive Construction
    "BRepPrimAPI_MakeBox": {
        "module": "OCP.BRepPrimAPI",
        "critical": True,
        "description": "Box primitive construction",
        "alternatives": [],
    },
    "BRepPrimAPI_MakeCylinder": {
        "module": "OCP.BRepPrimAPI",
        "critical": True,
        "description": "Cylinder primitive construction",
        "alternatives": [],
    },
    "BRepPrimAPI_MakeCone": {
        "module": "OCP.BRepPrimAPI",
        "critical": True,
        "description": "Cone primitive construction",
        "alternatives": [],
    },
    "BRepPrimAPI_MakeSphere": {
        "module": "OCP.BRepPrimAPI",
        "critical": True,
        "description": "Sphere primitive construction",
        "alternatives": [],
    },
    "BRepPrimAPI_MakePrism": {
        "module": "OCP.BRepPrimAPI",
        "critical": True,
        "description": "Extrusion operation",
        "alternatives": [],
    },
    "BRepPrimAPI_MakeRevol": {
        "module": "OCP.BRepPrimAPI",
        "critical": True,
        "description": "Revolution operation",
        "alternatives": [],
    },
    
    # Boolean Operations
    "BRepAlgoAPI_Fuse": {
        "module": "OCP.BRepAlgoAPI",
        "critical": True,
        "description": "Boolean union operation",
        "alternatives": [],
    },
    "BRepAlgoAPI_Cut": {
        "module": "OCP.BRepAlgoAPI",
        "critical": True,
        "description": "Boolean difference operation",
        "alternatives": [],
    },
    "BRepAlgoAPI_Common": {
        "module": "OCP.BRepAlgoAPI",
        "critical": True,
        "description": "Boolean intersection operation",
        "alternatives": [],
    },
    
    # Fillet and Chamfer
    "BRepFilletAPI_MakeFillet": {
        "module": "OCP.BRepFilletAPI",
        "critical": True,
        "description": "Fillet operation",
        "alternatives": [],
    },
    "BRepFilletAPI_MakeChamfer": {
        "module": "OCP.BRepFilletAPI",
        "critical": True,
        "description": "Chamfer operation",
        "alternatives": [],
    },
    
    # Topology Exploration
    "TopExp_Explorer": {
        "module": "OCP.TopExp",
        "critical": True,
        "description": "Topology exploration",
        "alternatives": [],
    },
    "TopoDS_Shape": {
        "module": "OCP.TopoDS",
        "critical": True,
        "description": "Base shape type",
        "alternatives": [],
    },
    "TopoDS_Solid": {
        "module": "OCP.TopoDS",
        "critical": True,
        "description": "Solid topology",
        "alternatives": [],
    },
    "TopoDS_Face": {
        "module": "OCP.TopoDS",
        "critical": True,
        "description": "Face topology",
        "alternatives": [],
    },
    "TopoDS_Edge": {
        "module": "OCP.TopoDS",
        "critical": True,
        "description": "Edge topology",
        "alternatives": [],
    },
    "TopoDS_Wire": {
        "module": "OCP.TopoDS",
        "critical": True,
        "description": "Wire topology",
        "alternatives": [],
    },
    
    # Geometry Types
    "gp_Pnt": {
        "module": "OCP.gp",
        "critical": True,
        "description": "3D point",
        "alternatives": [],
    },
    "gp_Vec": {
        "module": "OCP.gp",
        "critical": True,
        "description": "3D vector",
        "alternatives": [],
    },
    "gp_Dir": {
        "module": "OCP.gp",
        "critical": True,
        "description": "3D direction",
        "alternatives": [],
    },
    "gp_Ax2": {
        "module": "OCP.gp",
        "critical": True,
        "description": "Coordinate system",
        "alternatives": [],
    },
    "gp_Pln": {
        "module": "OCP.gp",
        "critical": True,
        "description": "Plane definition",
        "alternatives": [],
    },
    "gp_Trsf": {
        "module": "OCP.gp",
        "critical": True,
        "description": "Transformation",
        "alternatives": [],
    },
    
    # Shape Building
    "BRepBuilderAPI_MakeEdge": {
        "module": "OCP.BRepBuilderAPI",
        "critical": True,
        "description": "Edge construction",
        "alternatives": [],
    },
    "BRepBuilderAPI_MakeWire": {
        "module": "OCP.BRepBuilderAPI",
        "critical": True,
        "description": "Wire construction",
        "alternatives": [],
    },
    "BRepBuilderAPI_MakeFace": {
        "module": "OCP.BRepBuilderAPI",
        "critical": True,
        "description": "Face construction",
        "alternatives": [],
    },
    "BRepBuilderAPI_MakeSolid": {
        "module": "OCP.BRepBuilderAPI",
        "critical": True,
        "description": "Solid construction",
        "alternatives": [],
    },
    "BRepBuilderAPI_Sewing": {
        "module": "OCP.BRepBuilderAPI",
        "critical": False,
        "description": "Shape sewing for mesh import",
        "alternatives": [],
    },
    
    # Shape Validation and Repair
    "BRepCheck_Analyzer": {
        "module": "OCP.BRepCheck",
        "critical": False,
        "description": "Shape validation",
        "alternatives": [],
    },
    "ShapeFix_Shape": {
        "module": "OCP.ShapeFix",
        "critical": False,
        "description": "Shape repair",
        "alternatives": [],
    },
    
    # Topology Abs Types
    "TopAbs_FACE": {
        "module": "OCP.TopAbs",
        "critical": True,
        "description": "Face shape enum",
        "alternatives": [],
    },
    "TopAbs_EDGE": {
        "module": "OCP.TopAbs",
        "critical": True,
        "description": "Edge shape enum",
        "alternatives": [],
    },
    "TopAbs_SOLID": {
        "module": "OCP.TopAbs",
        "critical": True,
        "description": "Solid shape enum",
        "alternatives": [],
    },
    
    # Export
    "StlAPI_Writer": {
        "module": "OCP.StlAPI",
        "critical": False,
        "description": "STL export",
        "alternatives": ["build123d export_stl"],
    },
}

# Optional APIs that enhance functionality but aren't critical
OPTIONAL_OCP_APIS: Dict[str, Dict[str, Any]] = {
    "BRepOffsetAPI_MakeThickSolid": {
        "module": "OCP.BRepOffsetAPI",
        "description": "Shell/hollow operation",
    },
    "BRepOffsetAPI_MakePipe": {
        "module": "OCP.BRepOffsetAPI",
        "description": "Sweep along path",
    },
    "BRepOffsetAPI_ThruSections": {
        "module": "OCP.BRepOffsetAPI",
        "description": "Loft operation",
    },
    "BOPAlgo_CheckerSI": {
        "module": "OCP.BOPAlgo",
        "description": "Self-intersection check",
    },
    "BOPAlgo_ArgumentAnalyzer": {
        "module": "OCP.BOPAlgo",
        "description": "Boolean argument analysis",
    },
    "ShapeAnalysis_ShapeTolerance": {
        "module": "OCP.ShapeAnalysis",
        "description": "Tolerance analysis",
    },
    "ShapeUpgrade_UnifySameDomain": {
        "module": "OCP.ShapeUpgrade",
        "description": "Face merging optimization",
    },
    "BRepExtrema_DistShapeShape": {
        "module": "OCP.BRepExtrema",
        "description": "Distance computation for wall thickness",
    },
}


# =============================================================================
# Core Functions
# =============================================================================

def check_ocp_availability() -> bool:
    """
    Check if OCP (OpenCASCADE) is available.
    
    Returns:
        True if OCP can be imported, False otherwise
    """
    try:
        import OCP
        return True
    except ImportError:
        return False


def get_ocp_version() -> OCPVersionInfo:
    """
    Get detailed OCP version information.
    
    Returns:
        OCPVersionInfo with version details
    """
    info = OCPVersionInfo(
        python_version=sys.version.split()[0],
        platform=f"{platform.system()} {platform.release()} ({platform.machine})",
    )
    
    if not check_ocp_availability():
        return info
    
    try:
        import OCP
        
        # Try to get OCCT version from OCP
        # OCP packages version might differ from OCCT version
        try:
            # Method 1: Check OCP package version via importlib.metadata
            try:
                from importlib.metadata import version as get_version
                info.ocp_package_version = get_version("ocp")
            except Exception:
                # Fallback for older Python
                try:
                    import pkg_resources
                    info.ocp_package_version = pkg_resources.get_distribution("ocp").version
                except Exception:
                    pass
        except Exception:
            pass
        
        # Try to get OCCT version from OCP
        try:
            # OCCT stores version in various places depending on version
            if hasattr(OCP, 'OCCT_VERSION'):
                info.version_string = OCP.OCCT_VERSION
            elif hasattr(OCP, 'VERSION'):
                info.version_string = OCP.VERSION
            else:
                # Try to get from FoundationClasses
                try:
                    from OCP.Standard import Standard_Version
                    info.version_string = f"{Standard_Version.Major()}.{Standard_Version.Minor()}.{Standard_Version.Maintenance()}"
                except Exception:
                    # Last resort: parse from package version
                    if info.ocp_package_version != "unknown":
                        # OCP package version often includes OCCT version
                        # e.g., "7.8.1" or "7.8.1.0"
                        info.version_string = info.ocp_package_version.split('.')[0:3]
                        if len(info.version_string) >= 3:
                            info.version_string = '.'.join(info.version_string[:3])
                        else:
                            info.version_string = info.ocp_package_version
        except Exception:
            pass
        
        # Parse version string into components
        if info.version_string and info.version_string != "unknown":
            try:
                parts = info.version_string.replace('v', '').split('.')
                if len(parts) >= 1:
                    info.major = int(parts[0])
                if len(parts) >= 2:
                    info.minor = int(parts[1])
                if len(parts) >= 3:
                    info.patch = int(parts[2])
            except (ValueError, IndexError):
                pass
        
        info.available = True
        
        # Get build info if available
        try:
            from OCP.Standard import Standard_SystemSynchronization
            info.build_info = "OCP loaded successfully"
        except Exception:
            pass
            
    except Exception as e:
        logger.debug(f"Error getting OCP version: {e}")
    
    return info


def validate_ocp_api(check_optional: bool = False) -> List[ApiCompatibilityIssue]:
    """
    Validate that all required OCP APIs are available.
    
    Args:
        check_optional: Also check optional APIs
        
    Returns:
        List of ApiCompatibilityIssue objects for any problems found
    """
    issues: List[ApiCompatibilityIssue] = []
    
    if not check_ocp_availability():
        issues.append(ApiCompatibilityIssue(
            api_name="OCP",
            severity=ApiSeverity.CRITICAL,
            message="OCP (OpenCASCADE) package is not installed",
            suggestion="Install OCP: pip install ocp",
            platform_info=f"Current platform: {platform.system()} {platform.machine}",
        ))
        return issues
    
    # Check required APIs
    for api_name, api_info in REQUIRED_OCP_APIS.items():
        module = api_info["module"]
        try:
            # Try to import the specific class from the module
            parts = module.split('.')
            ocp_module = __import__(module, fromlist=[api_name])
            getattr(ocp_module, api_name)
        except ImportError as e:
            severity = ApiSeverity.CRITICAL if api_info.get("critical", True) else ApiSeverity.WARNING
            alternatives = api_info.get("alternatives", [])
            suggestion = f"Update OCP package or use alternatives: {alternatives}" if alternatives else "Update OCP package"
            
            issues.append(ApiCompatibilityIssue(
                api_name=api_name,
                severity=severity,
                message=f"Module {module} import failed: {e}",
                suggestion=suggestion,
            ))
        except AttributeError:
            severity = ApiSeverity.CRITICAL if api_info.get("critical", True) else ApiSeverity.WARNING
            alternatives = api_info.get("alternatives", [])
            suggestion = f"API may have changed in this OCP version. Alternatives: {alternatives}" if alternatives else "API may have changed in this OCP version"
            
            issues.append(ApiCompatibilityIssue(
                api_name=api_name,
                severity=severity,
                message=f"Class {api_name} not found in {module}",
                suggestion=suggestion,
            ))
    
    # Check optional APIs if requested
    if check_optional:
        for api_name, api_info in OPTIONAL_OCP_APIS.items():
            module = api_info["module"]
            try:
                ocp_module = __import__(module, fromlist=[api_name])
                getattr(ocp_module, api_name)
            except (ImportError, AttributeError):
                issues.append(ApiCompatibilityIssue(
                    api_name=api_name,
                    severity=ApiSeverity.INFO,
                    message=f"Optional API not available: {api_info['description']}",
                    suggestion="Some advanced features may be unavailable",
                ))
    
    return issues


def ocp_api_guard(
    fallback: Any = None,
    api_names: Optional[List[str]] = None,
    raise_on_failure: bool = False,
):
    """
    Decorator to guard functions that use OCP APIs.
    
    Provides graceful degradation when OCP APIs are unavailable.
    
    Args:
        fallback: Value to return if OCP is unavailable
        api_names: Specific APIs required (if None, just checks OCP availability)
        raise_on_failure: If True, raises RuntimeError instead of returning fallback
        
    Usage:
        @ocp_api_guard(fallback=None)
        def some_function():
            from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
            ...
            
        @ocp_api_guard(fallback=[], api_names=["BRepAlgoAPI_Fuse"])
        def boolean_operation():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Check basic OCP availability
            if not check_ocp_availability():
                if raise_on_failure:
                    raise RuntimeError(
                        f"OCP not available - cannot execute {func.__name__}. "
                        "Install OCP: pip install ocp"
                    )
                logger.warning(
                    f"OCP not available - returning fallback for {func.__name__}"
                )
                return fallback
            
            # Check specific APIs if specified
            if api_names:
                for api_name in api_names:
                    if api_name in REQUIRED_OCP_APIS:
                        module = REQUIRED_OCP_APIS[api_name]["module"]
                        try:
                            ocp_module = __import__(module, fromlist=[api_name])
                            getattr(ocp_module, api_name)
                        except (ImportError, AttributeError):
                            if raise_on_failure:
                                raise RuntimeError(
                                    f"OCP API {api_name} not available - "
                                    f"cannot execute {func.__name__}"
                                )
                            logger.warning(
                                f"OCP API {api_name} not available - "
                                f"returning fallback for {func.__name__}"
                            )
                            return fallback
            
            # All checks passed, execute the function
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Check if this is an OCP-related error
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['ocp', 'opencascade', 'topo', 'brep', 'gp_']):
                    if raise_on_failure:
                        raise RuntimeError(
                            f"OCP operation failed in {func.__name__}: {e}"
                        ) from e
                    logger.error(f"OCP operation failed in {func.__name__}: {e}")
                    return fallback
                raise
        
        return wrapper
    return decorator


def get_feature_availability() -> Dict[str, bool]:
    """
    Get a dictionary of feature availability based on OCP API presence.
    
    Returns:
        Dictionary mapping feature names to availability status
    """
    features: Dict[str, bool] = {}
    
    if not check_ocp_availability():
        return {
            "primitives": False,
            "booleans": False,
            "fillet_chamfer": False,
            "topology_exploration": False,
            "geometry_types": False,
            "shape_building": False,
            "validation_repair": False,
            "export_stl": False,
            "advanced_offset": False,
            "advanced_boolean": False,
        }
    
    # Check each feature category
    features["primitives"] = all(
        _check_api(api) for api in [
            "BRepPrimAPI_MakeBox", "BRepPrimAPI_MakeCylinder",
            "BRepPrimAPI_MakePrism", "BRepPrimAPI_MakeRevol"
        ]
    )
    
    features["booleans"] = all(
        _check_api(api) for api in [
            "BRepAlgoAPI_Fuse", "BRepAlgoAPI_Cut", "BRepAlgoAPI_Common"
        ]
    )
    
    features["fillet_chamfer"] = all(
        _check_api(api) for api in [
            "BRepFilletAPI_MakeFillet", "BRepFilletAPI_MakeChamfer"
        ]
    )
    
    features["topology_exploration"] = all(
        _check_api(api) for api in [
            "TopExp_Explorer", "TopoDS_Shape", "TopoDS_Solid",
            "TopoDS_Face", "TopoDS_Edge"
        ]
    )
    
    features["geometry_types"] = all(
        _check_api(api) for api in [
            "gp_Pnt", "gp_Vec", "gp_Dir", "gp_Ax2", "gp_Pln", "gp_Trsf"
        ]
    )
    
    features["shape_building"] = all(
        _check_api(api) for api in [
            "BRepBuilderAPI_MakeEdge", "BRepBuilderAPI_MakeWire",
            "BRepBuilderAPI_MakeFace", "BRepBuilderAPI_MakeSolid"
        ]
    )
    
    features["validation_repair"] = all(
        _check_api(api) for api in ["BRepCheck_Analyzer", "ShapeFix_Shape"]
    )
    
    features["export_stl"] = _check_api("StlAPI_Writer")
    
    features["advanced_offset"] = all(
        _check_api(api) for api in [
            "BRepOffsetAPI_MakeThickSolid", "BRepOffsetAPI_MakePipe",
            "BRepOffsetAPI_ThruSections"
        ]
    )
    
    features["advanced_boolean"] = all(
        _check_api(api) for api in [
            "BOPAlgo_CheckerSI", "BOPAlgo_ArgumentAnalyzer"
        ]
    )
    
    return features


def _check_api(api_name: str) -> bool:
    """Helper to check if a single API is available."""
    if api_name not in REQUIRED_OCP_APIS and api_name not in OPTIONAL_OCP_APIS:
        return False
    
    api_info = REQUIRED_OCP_APIS.get(api_name) or OPTIONAL_OCP_APIS.get(api_name)
    if not api_info:
        return False
    
    module = api_info["module"]
    try:
        ocp_module = __import__(module, fromlist=[api_name])
        getattr(ocp_module, api_name)
        return True
    except (ImportError, AttributeError):
        return False


# =============================================================================
# Global Compatibility Instance
# =============================================================================

class OCPCompatibility:
    """
    Global OCP compatibility manager.
    
    Provides cached access to compatibility information and
    integrates with feature flags.
    """
    
    def __init__(self):
        self._version_info: Optional[OCPVersionInfo] = None
        self._api_issues: Optional[List[ApiCompatibilityIssue]] = None
        self._feature_availability: Optional[Dict[str, bool]] = None
        self._initialized = False
    
    def initialize(self, force: bool = False) -> None:
        """
        Initialize compatibility checking.
        
        Args:
            force: Force re-initialization
        """
        if self._initialized and not force:
            return
        
        logger.info("Initializing OCP compatibility check...")
        
        # Get version info
        self._version_info = get_ocp_version()
        
        if self._version_info.available:
            logger.success(f"OCP Version: {self._version_info}")
        else:
            logger.warning("OCP not available - CAD operations will be limited")
        
        # Validate APIs
        self._api_issues = validate_ocp_api(check_optional=True)
        
        critical_issues = [i for i in self._api_issues if i.severity == ApiSeverity.CRITICAL]
        warning_issues = [i for i in self._api_issues if i.severity == ApiSeverity.WARNING]
        
        if critical_issues:
            logger.error(f"OCP API Critical Issues: {len(critical_issues)}")
            for issue in critical_issues:
                logger.error(f"  {issue}")
        
        if warning_issues:
            logger.warning(f"OCP API Warnings: {len(warning_issues)}")
            for issue in warning_issues:
                logger.warning(f"  {issue}")
        
        # Get feature availability
        self._feature_availability = get_feature_availability()
        
        # Update feature flags based on availability
        self._update_feature_flags()
        
        self._initialized = True
        logger.info("OCP compatibility check complete")
    
    def _update_feature_flags(self) -> None:
        """Update feature flags based on OCP availability."""
        try:
            if self._feature_availability:
                if not self._feature_availability.get("advanced_offset", False):
                    # Shell/hollow requires BRepOffsetAPI_MakeThickSolid
                    logger.info("Advanced offset operations may be limited")
                    
        except Exception as e:
            logger.debug(f"Could not update feature flags: {e}")
    
    @property
    def is_available(self) -> bool:
        """Check if OCP is available."""
        if self._version_info is None:
            self.initialize()
        return self._version_info.available if self._version_info else False
    
    @property
    def version_info(self) -> OCPVersionInfo:
        """Get version information."""
        if self._version_info is None:
            self.initialize()
        return self._version_info or OCPVersionInfo()
    
    @property
    def api_issues(self) -> List[ApiCompatibilityIssue]:
        """Get API compatibility issues."""
        if self._api_issues is None:
            self.initialize()
        return self._api_issues or []
    
    @property
    def feature_availability(self) -> Dict[str, bool]:
        """Get feature availability map."""
        if self._feature_availability is None:
            self.initialize()
        return self._feature_availability or {}
    
    @property
    def has_critical_issues(self) -> bool:
        """Check if there are any critical API issues."""
        return any(
            i.severity == ApiSeverity.CRITICAL for i in self.api_issues
        )
    
    def get_summary(self) -> str:
        """Get a human-readable summary of compatibility status."""
        lines = ["OCP Compatibility Summary", "=" * 40]
        
        if self.version_info.available:
            lines.append(f"Status: Available")
            lines.append(f"Version: {self.version_info.version_string}")
            lines.append(f"Package: {self.version_info.ocp_package_version}")
            lines.append(f"Platform: {self.version_info.platform}")
        else:
            lines.append("Status: NOT AVAILABLE")
            lines.append("CAD operations will be severely limited!")
        
        if self.api_issues:
            lines.append(f"\nAPI Issues: {len(self.api_issues)}")
            critical = sum(1 for i in self.api_issues if i.severity == ApiSeverity.CRITICAL)
            warning = sum(1 for i in self.api_issues if i.severity == ApiSeverity.WARNING)
            info = sum(1 for i in self.api_issues if i.severity == ApiSeverity.INFO)
            if critical:
                lines.append(f"  Critical: {critical}")
            if warning:
                lines.append(f"  Warnings: {warning}")
            if info:
                lines.append(f"  Info: {info}")
        else:
            lines.append("\nAPI Issues: None")
        
        return "\n".join(lines)


# Global instance
OCP_COMPATIBILITY = OCPCompatibility()


# =============================================================================
# Convenience Functions
# =============================================================================

def ensure_ocp_available() -> None:
    """
    Ensure OCP is available, raise RuntimeError if not.
    
    Raises:
        RuntimeError: If OCP is not available
    """
    if not OCP_COMPATIBILITY.is_available:
        raise RuntimeError(
            "OCP (OpenCASCADE) is not available. "
            "Please install it: pip install ocp"
        )


def get_missing_critical_apis() -> List[str]:
    """
    Get list of missing critical APIs.
    
    Returns:
        List of API names that are critical but unavailable
    """
    return [
        issue.api_name
        for issue in OCP_COMPATIBILITY.api_issues
        if issue.severity == ApiSeverity.CRITICAL
    ]


def is_feature_available(feature: str) -> bool:
    """
    Check if a specific feature is available.
    
    Args:
        feature: Feature name (e.g., "primitives", "booleans")
        
    Returns:
        True if the feature is available
    """
    return OCP_COMPATIBILITY.feature_availability.get(feature, False)
