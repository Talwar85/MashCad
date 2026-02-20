# Performance Troubleshooting Guide

This guide covers performance issues in MashCAD, including slow rendering, high memory usage, application freezes, and startup problems.

## Table of Contents

1. [Slow Viewport Rendering](#slow-viewport-rendering)
2. [High Memory Usage](#high-memory-usage)
3. [Application Freezes](#application-freezes)
4. [Startup Problems](#startup-problems)
5. [Performance Optimization Tips](#performance-optimization-tips)
6. [Error Messages Reference](#error-messages-reference)

---

## Slow Viewport Rendering

### Symptoms
- Low frame rate in 3D viewport
- Laggy rotation/pan/zoom
- Delayed visual updates
- Choppy animations

### Root Causes

#### 1. Complex Model Geometry

**Diagnosis:**
```python
# Check model complexity
from modeling.geometry_utils import analyze_complexity
stats = analyze_complexity(document)
print(f"Total faces: {stats.face_count}")
print(f"Total edges: {stats.edge_count}")
print(f"Total vertices: {stats.vertex_count}")
print(f"Mesh triangles: {stats.triangle_count}")
```

**Performance Thresholds:**

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| Faces | < 10,000 | 10,000 - 50,000 | > 50,000 |
| Triangles | < 100,000 | 100,000 - 500,000 | > 500,000 |
| Components | < 100 | 100 - 500 | > 500 |

**Solutions:**
1. Reduce mesh quality for display:
   ```python
   from config.feature_flags import set_flag
   set_flag("reduced_display_quality", True)
   ```

2. Enable early rejection for invisible objects:
   ```python
   set_flag("bbox_early_rejection", True)
   ```

3. Use simplified representation for complex parts:
   ```python
   body.set_display_quality("low")  # low, medium, high
   ```

#### 2. Inefficient Tessellation

**Problem:** Mesh generation is slow or produces too many triangles

**Solution:**
```python
# Adjust tessellation parameters
from modeling.cad_tessellator import set_global_tessellation_params
set_global_tessellation_params(
    linear_deflection=0.1,  # Increase for fewer triangles
    angular_deflection=0.5,  # Increase for fewer triangles
    relative_deflection=True
)
```

**Enable Async Tessellation:**
```python
from config.feature_flags import set_flag
set_flag("async_tessellation", True)
```

#### 3. GPU/Driver Issues

**Diagnosis:**
```python
# Check GPU capabilities
from gui.viewport import get_gpu_info
gpu = get_gpu_info()
print(f"Renderer: {gpu.renderer}")
print(f"VRAM: {gpu.vram_mb} MB")
print(f"OpenGL Version: {gpu.opengl_version}")
```

**Solutions:**
- Update GPU drivers to latest version
- Reduce anti-aliasing level
- Disable unnecessary visual effects:
  ```python
  from config.feature_flags import set_flag
  set_flag("disable_shadows", True)
  set_flag("disable_reflections", True)
  set_flag("simple_lighting", True)
  ```

#### 4. Too Many Actors in Viewport

**Problem:** Each body/face creates separate rendering actors

**Solution:**
```python
# Enable actor pooling
from config.feature_flags import set_flag
set_flag("optimized_actor_pooling", True)

# Enable picker pooling for selection
set_flag("picker_pooling", True)

# Reuse hover markers
set_flag("reuse_hover_markers", True)
```

---

## High Memory Usage

### Symptoms
- Application uses excessive RAM
- "Out of memory" errors
- System becomes sluggish
- Memory usage grows over time

### Root Causes

#### 1. Memory Leaks

**Diagnosis:**
```python
# Enable memory tracking
import tracemalloc
tracemalloc.start()

# ... perform operations ...

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
```

**Common Leak Sources:**
- Unclosed file handles
- Circular references in Python objects
- Cached geometry not being released
- VTK actor references

**Solution:**
```python
# Force garbage collection
import gc
gc.collect()

# Clear caches
from modeling.brep_cache import BrepCache
BrepCache.clear_all()
```

#### 2. Large BREP Cache

**Problem:** Cached geometry consuming too much memory

**Diagnosis:**
```python
from modeling.brep_cache import BrepCache
cache = BrepCache.get_instance()
print(f"Cache entries: {cache.entry_count}")
print(f"Cache size: {cache.size_mb} MB")
print(f"Hit rate: {cache.hit_rate}%")
```

**Solution:**
```python
# Adjust cache limits
from modeling.brep_cache import set_cache_limits
set_cache_limits(
    max_entries=1000,  # Maximum cached items
    max_size_mb=500    # Maximum cache size in MB
)

# Clear cache if needed
BrepCache.clear_all()
```

#### 3. Document History Growth

**Problem:** Undo/redo history consuming memory

**Solution:**
```python
# Limit history depth
from core.document import set_history_limit
set_history_limit(50)  # Keep last 50 states

# Clear history
document.clear_history()
```

#### 4. Mesh Data Accumulation

**Problem:** Generated meshes not being released

**Solution:**
```python
# Clear mesh cache
from meshconverter.mesh_converter import clear_mesh_cache
clear_mesh_cache()

# Enable automatic cleanup
from config.feature_flags import set_flag
set_flag("auto_mesh_cleanup", True)
```

---

## Application Freezes

### Symptoms
- UI becomes unresponsive
- Operations never complete
- "Not responding" in title bar
- Must force-quit application

### Root Causes

#### 1. Long-Running Operations on Main Thread

**Problem:** Heavy computation blocking UI thread

**Diagnosis:**
```python
# Enable operation timing
from config.feature_flags import set_flag
set_flag("operation_timing", True)

# Check operation durations
from core.performance_monitor import get_slow_operations
slow = get_slow_operations(threshold_ms=1000)
for op in slow:
    print(f"{op.name}: {op.duration_ms}ms")
```

**Solution:**
- Operations > 100ms should run asynchronously
- Report freeze issues with operation details

#### 2. Infinite Loops in Solvers

**Problem:** Sketch solver or constraint solver stuck in loop

**Diagnosis:**
```python
# Set solver timeout
from sketcher.solver import set_solver_timeout
set_solver_timeout(5.0)  # 5 second timeout
```

**Solution:**
```python
# Enable solver iteration limit
from sketcher.solver import set_solver_limits
set_solver_limits(
    max_iterations=1000,
    timeout_seconds=5.0
)
```

#### 3. Deadlocks

**Problem:** Multiple threads waiting on each other

**Diagnosis:**
```python
# Enable thread debugging
import threading
print(f"Active threads: {threading.active_count()}")
for thread in threading.enumerate():
    print(f"  {thread.name}: {thread.is_alive()}")
```

**Solution:**
- Report deadlock issues with thread dump
- Restart application

#### 4. GPU Hang

**Problem:** Graphics driver frozen

**Diagnosis:**
- Screen goes black or static
- Other applications also affected
- System requires restart

**Solution:**
- Update GPU drivers
- Reduce GPU load:
  ```python
  from config.feature_flags import set_flag
  set_flag("disable_gpu_acceleration", True)
  ```

---

## Startup Problems

### Symptoms
- Application takes long to start
- Startup fails with error
- Window doesn't appear
- Crashes during initialization

### Root Causes

#### 1. Slow Plugin/Extension Loading

**Diagnosis:**
```python
# Enable startup timing
from config.feature_flags import set_flag
set_flag("startup_debug", True)

# Check startup log
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Solution:**
- Disable unnecessary plugins
- Check for conflicting extensions

#### 2. Corrupt Configuration

**Problem:** Invalid settings prevent startup

**Solution:**
```python
# Reset to default configuration
from config.settings import reset_to_defaults
reset_to_defaults()

# Or delete config file manually
# Windows: %APPDATA%/MashCAD/settings.json
# Linux: ~/.config/MashCAD/settings.json
# macOS: ~/Library/Application Support/MashCAD/settings.json
```

#### 3. Missing Dependencies

**Problem:** Required libraries not found

**Diagnosis:**
```bash
# Check dependencies
python -c "import OCP; print('OCP OK')"
python -c "import vtk; print('VTK OK')"
python -c "import PySide6; print('PySide6 OK')"
```

**Solution:**
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

#### 4. GPU Initialization Failure

**Problem:** Cannot initialize graphics context

**Solution:**
```python
# Try software rendering
import os
os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"

# Or specify GPU
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
```

---

## Performance Optimization Tips

### General Optimization

1. **Enable All Performance Flags:**
   ```python
   from config.feature_flags import set_flag
   performance_flags = [
       "optimized_actor_pooling",
       "reuse_hover_markers",
       "picker_pooling",
       "bbox_early_rejection",
       "export_cache",
       "feature_dependency_tracking",
       "async_tessellation"
   ]
   for flag in performance_flags:
       set_flag(flag, True)
   ```

2. **Regular Maintenance:**
   ```python
   # Periodic cleanup (call every 100 operations or so)
   def periodic_cleanup():
       import gc
       gc.collect()
       
       from modeling.brep_cache import BrepCache
       BrepCache.prune()
       
       from meshconverter.mesh_converter import clear_mesh_cache
       clear_mesh_cache(older_than_seconds=300)
   ```

3. **Work Efficiently:**
   - Close unused documents
   - Simplify complex sketches
   - Use patterns instead of copies
   - Work at appropriate zoom level

### Model Optimization

1. **Reduce Complexity:**
   - Use fewer features when possible
   - Avoid redundant operations
   - Delete unused construction geometry

2. **Efficient Modeling:**
   - Use patterns for repeated features
   - Build from simple to complex
   - Avoid deep feature trees

3. **Assembly Optimization:**
   - Use lightweight representations for distant parts
   - Load sub-assemblies on demand
   - Disable automatic rebuild during complex edits

### Display Optimization

1. **Adjust Visual Quality:**
   ```python
   # For complex models, reduce quality
   from gui.viewport import set_display_quality
   set_display_quality("draft")  # draft, normal, quality
   ```

2. **Disable Expensive Effects:**
   ```python
   from config.feature_flags import set_flag
   set_flag("disable_ambient_occlusion", True)
   set_flag("disable_antialiasing", False)  # Keep AA, it's cheap
   set_flag("simple_edge_highlight", True)
   ```

---

## Error Messages Reference

### Performance Warnings

| Code | Message | Cause | Action |
|------|---------|-------|--------|
| PF-001 | "High memory usage detected" | RAM > 80% used | Clear caches, close documents |
| PF-002 | "Slow operation detected" | Operation > 1s | Consider simplification |
| PF-003 | "GPU memory low" | VRAM nearly full | Reduce display quality |
| PF-004 | "Cache miss rate high" | < 50% cache hits | Increase cache size |
| PF-005 | "Frame rate degraded" | FPS < 30 | Reduce model complexity |

### Memory Errors

| Code | Message | Cause | Action |
|------|---------|-------|--------|
| ME-001 | "Out of memory" | Allocation failed | Free memory, restart |
| ME-002 | "Cache overflow" | Cache size exceeded | Clear cache |
| ME-003 | "Memory leak detected" | Growing memory usage | Report bug |
| ME-004 | "Large allocation" | Single alloc > 100MB | Check operation |

### Startup Errors

| Code | Message | Cause | Action |
|------|---------|-------|--------|
| SU-001 | "Failed to initialize OCP" | OCP not installed | Install OCP |
| SU-002 | "GPU not supported" | Old GPU/drivers | Update drivers |
| SU-003 | "Config load failed" | Corrupt settings | Reset config |
| SU-004 | "Plugin load failed" | Bad plugin | Disable plugin |
| SU-005 | "License check failed" | Invalid license | Check license |

---

## Debug Checklist

When experiencing performance issues:

- [ ] Check model complexity (faces, triangles)
- [ ] Monitor memory usage
- [ ] Enable performance flags
- [ ] Check GPU drivers are current
- [ ] Clear caches
- [ ] Reduce display quality
- [ ] Check for memory leaks with tracemalloc
- [ ] Review operation timing logs
- [ ] Disable unnecessary visual effects

## Performance Monitoring

```python
# Enable comprehensive performance monitoring
from config.feature_flags import set_flag
set_flag("performance_monitoring", True)

# Get performance report
from core.performance_monitor import get_report
report = get_report()
print(report.summary())

# Export detailed metrics
report.export("performance_report.json")
```

## Related Files

- [`config/feature_flags.py`](../../config/feature_flags.py) - Performance flags
- [`modeling/brep_cache.py`](../../modeling/brep_cache.py) - Geometry caching
- [`modeling/cad_tessellator.py`](../../modeling/cad_tessellator.py) - Mesh generation
- [`gui/viewport/`](../../gui/viewport/) - Viewport rendering
- [`core/document.py`](../../core/document.py) - Document management

## Feature Flags for Performance

```python
# All performance flags (recommended: all True)
"optimized_actor_pooling": True
"reuse_hover_markers": True
"picker_pooling": True
"bbox_early_rejection": True
"export_cache": True
"feature_dependency_tracking": True
"async_tessellation": True

# Debug flags (recommended: False unless debugging)
"performance_monitoring": False
"operation_timing": False
"startup_debug": False
```
