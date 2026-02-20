# MashCAD Export Regression Corpus

This directory contains a regression corpus for STL/3MF export validation.
Each model is designed to test specific aspects of the export pipeline.

## Directory Structure

```
test/corpus/
├── README.md                    # This file
├── primitives/                  # Basic shapes
│   ├── cube.py                 # Unit cube
│   ├── sphere.py               # Unit sphere
│   ├── cylinder.py             # Unit cylinder
│   ├── cone.py                 # Unit cone
│   └── torus.py                # Unit torus
├── operations/                  # Boolean operations
│   ├── union.py                # Union of two cubes
│   ├── difference.py           # Cube minus sphere
│   ├── intersection.py         # Two overlapping spheres
│   └── complex_boolean.py      # Multi-body boolean
├── features/                    # CAD features
│   ├── extrude_with_hole.py    # Extruded profile with hole
│   ├── fillet_cube.py          # Cube with edge fillets
│   ├── chamfer_cube.py         # Cube with edge chamfers
│   ├── shell_box.py            # Hollowed box (shell)
│   └── revolve_profile.py      # Revolved profile
└── regression/                  # Known issue cases
    ├── thin_wall.py            # Thin wall geometry
    ├── complex_fillet.py       # Complex fillet case
    └── manifold_edge_case.py   # Manifold edge case
```

## Corpus Model Interface

Each corpus model file must implement:

```python
from typing import Dict, Any, Optional
from OCP.TopoDS import TopoDS_Shape

def create_model() -> TopoDS_Shape:
    """Create and return the OCP shape for this corpus model."""
    pass

def get_metadata() -> Dict[str, Any]:
    """Return metadata about this corpus model."""
    return {
        "name": "Model Name",
        "category": "primitives|operations|features|regression",
        "description": "Brief description",
        "expected_issues": [],  # List of expected validation issues
        "tags": [],             # Tags for filtering
    }
```

## Running the Corpus

### Via pytest:
```bash
pytest test/test_export_corpus.py -v
```

### Via PowerShell script:
```powershell
./scripts/run_export_corpus.ps1
```

## Validation Criteria

Each model is validated against:

1. **Manifold Check**: Must be a closed solid (unless `expected_issues` includes "non_manifold")
2. **Free Bounds Check**: No open edges (unless expected)
3. **Degenerate Faces**: No zero-area triangles
4. **Export Success**: STL/STEP export completes without error
5. **File Integrity**: Output file is valid and non-empty

## Adding New Models

1. Create a new Python file in the appropriate category directory
2. Implement `create_model()` and `get_metadata()`
3. Add any expected issues to metadata if the model intentionally has problems
4. Run the corpus tests to verify

## Golden Files

Golden reference files can be stored in `test/corpus/golden/`:
- `{model_name}.stl` - Reference STL file
- `{model_name}.json` - Expected validation results

---

**Author**: MashCAD Team
**Date**: 2026-02-20
**Branch**: feature/v1-roadmap-execution
