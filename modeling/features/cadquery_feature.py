"""
CadQuery Feature for MashCad

Editable parametric script feature that stores the script source
and allows re-execution with parameter changes.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from loguru import logger
from modeling.features import Feature, FeatureType


@dataclass
class Parameter:
    """A parameter in a CadQuery script."""
    name: str
    value: float
    default_value: float
    description: str = ""

    def __str__(self):
        return f"{self.name} = {self.value}"

    def to_dict(self) -> dict:
        """Convert parameter to dict for serialization."""
        return {
            "name": self.name,
            "value": self.value,
            "default_value": self.default_value,
            "description": self.description
        }

    @staticmethod
    def from_dict(data: dict) -> 'Parameter':
        """Create parameter from dict."""
        return Parameter(
            name=data.get("name", ""),
            value=float(data.get("value", 0)),
            default_value=float(data.get("default_value", 0)),
            description=data.get("description", "")
        )


def extract_parameters_from_script(script: str) -> List[Parameter]:
    """
    Extract parameters from a CadQuery script.

    Looks for variable assignments at the top of the script:
        length = 100
        width = 50
        radius = 12.5

    Args:
        script: Python script content

    Returns:
        List of Parameter objects
    """
    import ast
    import re

    parameters = []

    # Method 1: Parse with AST
    try:
        tree = ast.parse(script)

        # Look for assignments at the top level
        # Stop when we hit something other than assignment
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                # Continue if it's an import or docstring
                if isinstance(node, (ast.Import, ast.ImportFrom, ast.Expr)):
                    # Check if it's a docstring
                    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                        if isinstance(node.value.value, str):
                            continue
                    continue
                break

            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id

                    # Try to evaluate as number
                    try:
                        value = ast.literal_eval(node.value)
                        if isinstance(value, (int, float)):
                            parameters.append(Parameter(
                                name=name,
                                value=float(value),
                                default_value=float(value),
                                description=name.replace('_', ' ').title()
                            ))
                    except:
                        pass

    except SyntaxError:
        pass

    return parameters


def update_script_parameters(script: str, parameters: Dict[str, float]) -> str:
    """
    Update parameter values in a script.

    Args:
        script: Original script content
        parameters: Dict of parameter name -> new value

    Returns:
        Updated script
    """
    import re

    lines = script.split('\n')
    result = []

    for line in lines:
        updated = False
        for name, value in parameters.items():
            # Pattern: name = value
            pattern = rf'^{name}\s*=\s*[\d.]+'
            if re.match(pattern, line):
                line = f"{name} = {value}"
                updated = True
                break
        result.append(line)

    return '\n'.join(result)


@dataclass
class CadQueryFeature(Feature):
    """
    Editable CadQuery script feature.

    Stores the script source and allows:
    - Re-editing the script
    - Changing parameters
    - Re-executing to regenerate geometry
    """

    script: str = ""
    source_file: str = ""  # Original filename for reference
    parameters: List[Parameter] = field(default_factory=list)

    def __post_init__(self):
        """Initialize feature type and extract parameters."""
        self.type = FeatureType.CADQUERY
        if not self.name or self.name == "Feature":
            self.name = "CadQuery Script"
        # Extract parameters if not provided
        if not self.parameters and self.script:
            self.parameters = extract_parameters_from_script(self.script)

    def get_parameter_value(self, name: str) -> Optional[float]:
        """Get a parameter value by name."""
        for param in self.parameters:
            if param.name == name:
                return param.value
        return None

    def set_parameter_value(self, name: str, value: float) -> bool:
        """Set a parameter value by name and update script."""
        for param in self.parameters:
            if param.name == name:
                param.value = value
                self.script = update_script_parameters(self.script, {name: value})
                return True
        return False

    def update_script_from_params(self) -> str:
        """Get the script with current parameter values applied."""
        param_dict = {p.name: p.value for p in self.parameters}
        return update_script_parameters(self.script, param_dict)

    def execute(self, document) -> List[Any]:
        """
        Execute the script and return solids.

        Args:
            document: Document instance for execution context

        Returns:
            List of Build123d Solid objects
        """
        from modeling.cadquery_importer import CadQueryImporter

        # Use the current script (with updated parameters)
        script = self.update_script_from_params()

        importer = CadQueryImporter(document)
        result = importer.execute_code(script, source=self.source_file or self.name)

        if result.success:
            return result.solids
        return []

    def to_dict(self) -> dict:
        """Convert feature to dict for serialization."""
        return {
            "feature_class": "CadQueryFeature",
            "name": self.name,
            "type": self.type.name if hasattr(self.type, 'name') else str(self.type),
            "id": self.id,
            "script": self.script,
            "source_file": self.source_file,
            "parameters": [p.to_dict() for p in self.parameters]
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'CadQueryFeature':
        """Create feature from dict."""
        params_data = data.get("parameters", [])
        parameters = [Parameter.from_dict(p) for p in params_data]

        return cls(
            name=data.get("name", "CadQuery Script"),
            script=data.get("script", ""),
            source_file=data.get("source_file", ""),
            parameters=parameters
        )


# Register the feature type
try:
    FeatureType.CADQUERY = "CADQUERY"
except:
    pass
