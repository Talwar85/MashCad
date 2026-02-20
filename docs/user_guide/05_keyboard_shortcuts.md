# Keyboard Shortcuts

Master MashCAD's keyboard shortcuts to dramatically speed up your workflow. This guide covers all shortcuts organized by category.

---

## Table of Contents

1. [Navigation Shortcuts](#navigation-shortcuts)
2. [Tool Shortcuts](#tool-shortcuts)
3. [Action Shortcuts](#action-shortcuts)
4. [Sketch Mode Shortcuts](#sketch-mode-shortcuts)
5. [Customization](#customization)
6. [Quick Reference Card](#quick-reference-card)

---

## Navigation Shortcuts

### View Controls

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Middle Mouse + Drag` | Orbit | Rotate view around model |
| `Middle Mouse + Shift + Drag` | Pan | Move view horizontally |
| `Scroll Wheel` | Zoom | Zoom in/out |
| `F` | Fit All | Fit entire model in view |
| `Home` | Home View | Reset to default view |
| `Escape` | Cancel | Cancel current operation |

### View Presets (Numpad)

| Shortcut | View | Direction |
|----------|------|-----------|
| `Numpad 1` | Front | +Y |
| `Ctrl + Numpad 1` | Back | -Y |
| `Numpad 3` | Right | +X |
| `Ctrl + Numpad 3` | Left | -X |
| `Numpad 7` | Top | +Z |
| `Ctrl + Numpad 7` | Bottom | -Z |
| `Numpad 5` | Isometric | 3D view |
| `Numpad 0` | Perspective Toggle | Switch projection |

### Selection

| Shortcut | Action |
|----------|--------|
| `Left Click` | Select |
| `Ctrl + Left Click` | Add to selection |
| `Shift + Left Click` | Remove from selection |
| `Box Select (Drag)` | Select multiple |
| `Double Click` | Select connected/chain |
| `Ctrl + A` | Select all |
| `Escape` | Deselect all |

---

## Tool Shortcuts

### Transform Tools

| Shortcut | Tool | Description |
|----------|------|-------------|
| `G` | **Grab/Move** | Move selected objects |
| `R` | **Rotate** | Rotate selected objects |
| `S` | **Scale** | Scale selected objects |
| `M` | **Mirror** | Mirror selected objects |

#### Transform Modifiers

While transforming:

| Key | Modifier |
|-----|----------|
| `X` | Constrain to X axis |
| `Y` | Constrain to Y axis |
| `Z` | Constrain to Z axis |
| `Shift` | Snap to grid |
| `Ctrl` | Fine control |
| `Enter` | Apply transform |
| `Escape` | Cancel transform |

### 3D Operations

| Shortcut | Tool |
|----------|------|
| `E` | Extrude |
| `F` | Fillet |
| `Ctrl + F` | Chamfer |
| `J` | Join (Boolean Union) |
| `C` | Cut (Boolean Difference) |
| `I` | Intersect (Boolean Intersection) |

### Visibility

| Shortcut | Action |
|----------|--------|
| `H` | Hide selected |
| `Shift + H` | Hide unselected |
| `Alt + H` | Show all |
| `V` | Toggle visibility |

---

## Action Shortcuts

### File Operations

| Shortcut | Action |
|----------|--------|
| `Ctrl + N` | New project |
| `Ctrl + O` | Open file |
| `Ctrl + S` | Save project |
| `Ctrl + Shift + S` | Save As |
| `Ctrl + I` | Import |
| `Ctrl + Shift + E` | Export |

### Edit Operations

| Shortcut | Action |
|----------|--------|
| `Ctrl + Z` | Undo |
| `Ctrl + Y` | Redo |
| `Ctrl + Shift + Z` | Redo (alternative) |
| `Ctrl + C` | Copy |
| `Ctrl + X` | Cut |
| `Ctrl + V` | Paste |
| `Delete` | Delete selected |
| `Backspace` | Delete selected |

### General

| Shortcut | Action |
|----------|--------|
| `Tab` | Numeric input / Toggle mode |
| `Space` | 3D peek (in sketch mode) |
| `Enter` | Confirm/Accept |
| `Escape` | Cancel/Exit |
| `F1` | Help |
| `F2` | Rename |
| `F5` | Refresh view |
| `F11` | Fullscreen |
| `F12` | Developer tools |

---

## Sketch Mode Shortcuts

These shortcuts are active when editing a sketch.

### Drawing Tools

| Shortcut | Tool |
|----------|------|
| `L` | Line |
| `R` | Rectangle |
| `C` | Circle |
| `A` | Arc |
| `P` | Polygon |
| `S` | Slot |
| `B` | Spline (Bézier) |
| `E` | Ellipse |

### Constraint Tools

| Shortcut | Constraint |
|----------|------------|
| `H` | Horizontal |
| `V` | Vertical |
| `D` | Dimension/Distance |
| `Shift + D` | Diameter |
| `Shift + A` | Angle |
| `T` | Tangent |
| `Shift + P` | Parallel |
| `Shift + T` | Perpendicular |
| `E` | Equal |
| `O` | Concentric |
| `Shift + C` | Coincident |
| `M` | Midpoint |
| `F` | Fixed |
| `Shift + S` | Symmetric |

### Sketch Operations

| Shortcut | Action |
|----------|--------|
| `Tab` | Numeric input panel |
| `Space` | 3D peek (preview in 3D) |
| `Escape` | Finish sketch / Cancel |
| `Enter` | Close profile |
| `Delete` | Delete selected geometry |
| `Ctrl + Z` | Undo |
| `Ctrl + Y` | Redo |

### Numeric Input

Press `Tab` while drawing to access:

| Input | Description |
|-------|-------------|
| `X` | X coordinate |
| `Y` | Y coordinate |
| `L` | Length |
| `A` | Angle |
| `R` | Radius |
| `D` | Diameter |
| `Tab` | Cycle through fields |
| `Enter` | Apply values |
| `Escape` | Cancel input |

---

## Customization

### Accessing Shortcut Settings

1. Go to **Edit → Preferences → Shortcuts**
2. Or press `Ctrl + K` then `S`

### Customizing Shortcuts

```
[Screenshot placeholder: Shortcut customization dialog]
```

**To change a shortcut:**
1. Find the command in the list
2. Click on the current shortcut
3. Press the new key combination
4. Click **Apply**

### Resetting Shortcuts

- **Reset single:** Right-click → Reset to Default
- **Reset all:** Click **Reset All** button

### Exporting/Importing Shortcuts

Share your custom shortcuts:

1. Click **Export** to save shortcuts file
2. Click **Import** to load shortcuts file
3. File format: JSON

### Shortcut Conflicts

MashCAD warns about conflicts:
- Yellow indicator: Potential conflict
- Red indicator: Critical conflict

Resolve by reassigning one of the conflicting shortcuts.

---

## Quick Reference Card

### Most Used Shortcuts

| Category | Shortcut | Action |
|----------|----------|--------|
| **Navigate** | `Middle Drag` | Orbit |
| | `Shift + Middle Drag` | Pan |
| | `Scroll` | Zoom |
| | `F` | Fit All |
| **Transform** | `G` | Move |
| | `R` | Rotate |
| | `S` | Scale |
| **3D** | `E` | Extrude |
| | `F` | Fillet |
| | `J` | Join |
| | `C` | Cut |
| **General** | `Ctrl + S` | Save |
| | `Ctrl + Z` | Undo |
| | `H` | Hide |
| | `Delete` | Delete |

### Sketch Mode Essentials

| Shortcut | Action |
|----------|--------|
| `L` | Line |
| `R` | Rectangle |
| `C` | Circle |
| `A` | Arc |
| `D` | Dimension |
| `H` | Horizontal |
| `V` | Vertical |
| `Tab` | Numeric input |
| `Space` | 3D peek |
| `Escape` | Finish |

### Transform Axis Lock

| During Transform | Constraint |
|------------------|------------|
| `G then X` | Move on X |
| `G then Y` | Move on Y |
| `G then Z` | Move on Z |
| `R then X` | Rotate around X |
| `R then Y` | Rotate around Y |
| `R then Z` | Rotate around Z |
| `S then X` | Scale X only |
| `S then Y` | Scale Y only |
| `S then Z` | Scale Z only |

---

## Tips for Learning Shortcuts

### 1. Start with Essentials

Learn these first:
- `G`, `R`, `S` - Transform
- `E` - Extrude
- `Ctrl + S` - Save
- `Ctrl + Z` - Undo

### 2. Use Shortcut Hints

MashCAD shows shortcuts in:
- Tooltips on toolbar buttons
- Menu items (right side)
- Status bar hints

### 3. Practice Muscle Memory

- Use shortcuts instead of menus
- Force yourself for 1 week
- Speed will increase dramatically

### 4. Print the Reference

Print this page or the quick reference card:
- Keep near your workstation
- Glance when you forget

### 5. Customize for Your Workflow

- Assign frequently used tools to easy keys
- Remove unused shortcuts
- Match other software you use

---

## Platform-Specific Notes

### Windows

- `Ctrl` is the primary modifier
- `Alt` for alternate actions
- Numpad works as described

### macOS

- `⌘ (Command)` replaces `Ctrl`
- `⌥ (Option)` replaces `Alt`
- Numpad may require `Num Lock`

### Linux

- Same as Windows
- Some window managers may intercept shortcuts

---

## Related Topics

- **[Getting Started](01_getting_started.md)** - Basic navigation
- **[Sketch Workflow](02_sketch_workflow.md)** - Sketch tools
- **[3D Operations](03_3d_operations.md)** - 3D tools

---

*Last updated: February 2026 | MashCAD v0.3.0*
