"""
CadQuery Feature for MashCad

Phase 3: Parametric CadQuery scripts with parameter tracking.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from loguru import logger
from modeling.features import Feature


@dataclass
class Parameter:
    """A parameter in a CadQuery script."""
    name: str
    value: float
    default_value: float
    description: str = ""

    def __str__(self):
        return f"{self.name} = {self.value}"


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


class CadQueryFeature(Feature):
    """
    Feature representing a CadQuery script with parameters.
    """

    def __init__(self, name: str, script: str, parameters: Optional[List[Parameter]] = None):
        super().__init__(name)
        self.script = script
        self._parameters = parameters or extract_parameters_from_script(script)

    @property
    def parameters(self) -> List[Parameter]:
        """Get the feature parameters."""
        return self._parameters

    def get_parameter_value(self, name: str) -> Optional[float]:
        """Get a parameter value by name."""
        for param in self._parameters:
            if param.name == name:
                return param.value
        return None

    def set_parameter_value(self, name: str, value: float) -> bool:
        """Set a parameter value by name."""
        for param in self._parameters:
            if param.name == name:
                param.value = value
                self.script = update_script_parameters(self.script, {name: value})
                return True
        return False

    def update_script(self) -> str:
        """Get the script with current parameter values."""
        param_dict = {p.name: p.value for p in self._parameters}
        return update_script_parameters(self.script, param_dict)
