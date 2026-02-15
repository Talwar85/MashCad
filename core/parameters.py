"""
LiteCAD - Parameter System
Parametrisierbare Werte für Sketches (wie Fusion360)

Verwendung:
    from core.parameters import Parameters
    
    params = Parameters()
    params.set('width', 100)
    params.set('height', 'width * 0.5')  # Formel!
    
    value = params.get('height')  # -> 50.0
"""

import re
import math
from typing import Dict, Any, Optional, List, Tuple
from loguru import logger


class Parameters:
    """
    Parametersystem für LiteCAD.
    Unterstützt Variablen und Formeln.
    """
    
    def __init__(self):
        self._params: Dict[str, Any] = {}  # Name -> Wert oder Formel
        self._formulas: Dict[str, str] = {}  # Name -> Original-Formel
        self._dependencies: Dict[str, List[str]] = {}  # Name -> Liste von abhängigen Params
        
        # Standard mathematische Funktionen für Formeln
        self._math_funcs = {
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'asin': math.asin,
            'acos': math.acos,
            'atan': math.atan,
            'atan2': math.atan2,
            'sqrt': math.sqrt,
            'log': math.log,
            'log10': math.log10,
            'exp': math.exp,
            'pow': pow,
            'floor': math.floor,
            'ceil': math.ceil,
            'abs': abs,
            'min': min,
            'max': max,
            'pi': math.pi,
            'e': math.e,
            'tau': math.tau,
            'radians': math.radians,
            'degrees': math.degrees,
        }
    
    def set(self, name: str, value: Any) -> bool:
        """
        Setzt einen Parameter.
        
        Args:
            name: Parametername (z.B. 'width', 'hole_diameter')
            value: Wert (Zahl) oder Formel (String wie 'width * 2')
            
        Returns:
            True wenn erfolgreich
        """
        name = name.strip()
        
        # Validiere Name
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            raise ValueError(f"Ungültiger Parametername: {name}")
        
        if isinstance(value, str):
            # Es ist eine Formel
            self._formulas[name] = value
            # Finde Abhängigkeiten
            deps = self._find_dependencies(value)
            self._dependencies[name] = deps
            # Berechne initialen Wert
            self._params[name] = self._evaluate(value)
        else:
            # Es ist ein direkter Wert
            self._params[name] = float(value)
            if name in self._formulas:
                del self._formulas[name]
            self._dependencies[name] = []
        
        # Aktualisiere abhängige Parameter
        self._update_dependents(name)
        
        return True
    
    def get(self, name: str, default: float = 0.0) -> float:
        """Gibt den Wert eines Parameters zurück"""
        return self._params.get(name, default)
    
    def get_formula(self, name: str) -> Optional[str]:
        """Gibt die Formel eines Parameters zurück (oder None wenn direkter Wert)"""
        return self._formulas.get(name)
    
    def delete(self, name: str) -> bool:
        """Löscht einen Parameter"""
        if name in self._params:
            del self._params[name]
            if name in self._formulas:
                del self._formulas[name]
            if name in self._dependencies:
                del self._dependencies[name]
            return True
        return False
    
    def list_all(self) -> List[Tuple[str, float, Optional[str]]]:
        """
        Gibt alle Parameter als Liste zurück.
        
        Returns:
            Liste von (name, value, formula_or_none)
        """
        result = []
        for name, value in self._params.items():
            formula = self._formulas.get(name)
            result.append((name, value, formula))
        return sorted(result, key=lambda x: x[0])
    
    def _find_dependencies(self, formula: str) -> List[str]:
        """Findet alle Parameter-Referenzen in einer Formel"""
        # Alle Wörter finden die Parameter sein könnten
        words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', formula)
        # Filter: nur existierende Parameter und keine Math-Funktionen
        deps = [w for w in words if w in self._params and w not in self._math_funcs]
        return list(set(deps))
    
    def _evaluate(self, formula: str) -> float:
        """Evaluiert eine Formel"""
        try:
            # Erstelle Namespace mit Parametern und Math-Funktionen
            namespace = {**self._params, **self._math_funcs}
            result = eval(formula, {"__builtins__": {}}, namespace)
            return float(result)
        except Exception as e:
            logger.warning(f"Fehler beim Evaluieren von '{formula}': {e}")
            return 0.0
    
    def _update_dependents(self, changed_param: str):
        """Aktualisiert alle Parameter die von changed_param abhängen"""
        for name, deps in self._dependencies.items():
            if changed_param in deps:
                if name in self._formulas:
                    self._params[name] = self._evaluate(self._formulas[name])
                    # Rekursiv weiter aktualisieren
                    self._update_dependents(name)
    
    def to_dict(self) -> Dict:
        """Exportiert Parameter für Speicherung"""
        return {
            'values': dict(self._params),
            'formulas': dict(self._formulas)
        }
    
    def from_dict(self, data: Dict):
        """Importiert Parameter aus gespeicherten Daten"""
        self._params.clear()
        self._formulas.clear()
        self._dependencies.clear()
        
        # Erst direkte Werte laden
        for name, value in data.get('values', {}).items():
            if name not in data.get('formulas', {}):
                self._params[name] = value
        
        # Dann Formeln laden (damit Referenzen funktionieren)
        for name, formula in data.get('formulas', {}).items():
            self.set(name, formula)


# Globale Parameter-Instanz
_global_params = Parameters()


def get_parameters() -> Parameters:
    """Gibt die globale Parameter-Instanz zurück"""
    return _global_params
