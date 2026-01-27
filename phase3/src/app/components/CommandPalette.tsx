import { useState, useEffect, useRef } from 'react';
import { Search, Command } from 'lucide-react';
import type { ViewMode } from '@/app/App';

interface CommandPaletteProps {
  onClose: () => void;
  onSelectTool: (tool: string) => void;
  viewMode?: ViewMode;
}

interface CommandItem {
  id: string;
  name: string;
  category: string;
  shortcut?: string;
  keywords?: string[];
  modes: ViewMode[];
}

export function CommandPalette({ onClose, onSelectTool, viewMode = '3D' }: CommandPaletteProps) {
  const [search, setSearch] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const allCommands: CommandItem[] = [
    // 3D Mode - Primitives
    { id: 'cube', name: 'Würfel erstellen', category: 'Primitives', shortcut: 'C', keywords: ['cube', 'box'], modes: ['3D'] },
    { id: 'sphere', name: 'Kugel erstellen', category: 'Primitives', shortcut: 'S', keywords: ['sphere', 'ball'], modes: ['3D'] },
    { id: 'cylinder', name: 'Zylinder erstellen', category: 'Primitives', keywords: ['cylinder'], modes: ['3D'] },
    { id: 'cone', name: 'Kegel erstellen', category: 'Primitives', keywords: ['cone'], modes: ['3D'] },
    { id: 'torus', name: 'Torus erstellen', category: 'Primitives', keywords: ['torus', 'ring'], modes: ['3D'] },
    { id: 'plane', name: 'Ebene erstellen', category: 'Primitives', keywords: ['plane'], modes: ['3D'] },
    
    // 3D Mode - Modeling
    { id: 'createsketch', name: 'Create Sketch', category: 'Modeling', shortcut: 'N', keywords: ['sketch', 'draw'], modes: ['3D'] },
    { id: 'extrude', name: 'Extrude', category: 'Modeling', shortcut: 'E', keywords: ['extrude'], modes: ['3D'] },
    { id: 'revolve', name: 'Revolve', category: 'Modeling', keywords: ['revolve', 'rotate'], modes: ['3D'] },
    { id: 'sweep', name: 'Sweep', category: 'Modeling', keywords: ['sweep'], modes: ['3D'] },
    { id: 'loft', name: 'Loft', category: 'Modeling', keywords: ['loft'], modes: ['3D'] },
    { id: 'fillet', name: 'Fillet/Abrunden', category: 'Modeling', keywords: ['fillet', 'round'], modes: ['3D'] },
    { id: 'chamfer', name: 'Chamfer/Fase', category: 'Modeling', keywords: ['chamfer'], modes: ['3D'] },
    { id: 'shell', name: 'Shell/Aushöhlen', category: 'Modeling', keywords: ['shell', 'hollow'], modes: ['3D'] },
    
    // 3D Mode - Transform
    { id: 'move', name: 'Objekt bewegen', category: 'Transform', shortcut: 'G', keywords: ['move', 'translate'], modes: ['3D'] },
    { id: 'rotate', name: 'Objekt rotieren', category: 'Transform', shortcut: 'R', keywords: ['rotate', 'turn'], modes: ['3D'] },
    { id: 'scale', name: 'Objekt skalieren', category: 'Transform', shortcut: 'S', keywords: ['scale', 'resize'], modes: ['3D'] },
    { id: 'mirror', name: 'Objekt spiegeln', category: 'Transform', keywords: ['mirror', 'flip'], modes: ['3D'] },
    { id: 'pattern_linear', name: 'Linear Pattern', category: 'Transform', keywords: ['pattern', 'array'], modes: ['3D'] },
    { id: 'pattern_circular', name: 'Circular Pattern', category: 'Transform', keywords: ['pattern', 'circular'], modes: ['3D'] },
    { id: 'duplicate', name: 'Objekt duplizieren', category: 'Transform', shortcut: 'D', keywords: ['duplicate', 'copy'], modes: ['3D'] },
    
    // 3D Mode - Boolean
    { id: 'union', name: 'Vereinigung', category: 'Boolean', keywords: ['union', 'join'], modes: ['3D'] },
    { id: 'subtract', name: 'Differenz', category: 'Boolean', keywords: ['subtract', 'difference'], modes: ['3D'] },
    { id: 'intersect', name: 'Schnittmenge', category: 'Boolean', keywords: ['intersect', 'intersection'], modes: ['3D'] },
    
    // 3D Mode - 3D Print
    { id: 'hollow', name: 'Aushöhlen', category: '3D-Druck', keywords: ['hollow'], modes: ['3D'] },
    { id: 'wallthickness', name: 'Wandstärke prüfen', category: '3D-Druck', keywords: ['wall', 'thickness'], modes: ['3D'] },
    { id: 'lattice', name: 'Gitterstruktur', category: '3D-Druck', keywords: ['lattice', 'grid'], modes: ['3D'] },
    { id: 'supports', name: 'Support-Strukturen', category: '3D-Druck', keywords: ['supports'], modes: ['3D'] },
    
    // 3D Mode - Inspect
    { id: 'section', name: 'Section View', category: 'Inspect', keywords: ['section', 'cut'], modes: ['3D'] },
    { id: 'measure', name: 'Messen', category: 'Inspect', keywords: ['measure', 'dimension'], modes: ['3D'] },
    { id: 'checkgeometry', name: 'Geometrie prüfen', category: 'Inspect', keywords: ['check', 'validate'], modes: ['3D'] },
    { id: 'surfaceanalysis', name: 'Oberflächenanalyse', category: 'Inspect', keywords: ['surface', 'analysis'], modes: ['3D'] },
    { id: 'repair', name: 'Geometrie reparieren', category: 'Inspect', keywords: ['repair', 'fix'], modes: ['3D'] },
    
    // 2D/Sketch Mode - Basic Geometry
    { id: 'line', name: 'Linie zeichnen', category: 'Basis Geometrie', shortcut: 'L', keywords: ['line'], modes: ['2D'] },
    { id: 'rectangle', name: 'Rechteck zeichnen', category: 'Basis Geometrie', shortcut: 'R', keywords: ['rectangle', 'rect'], modes: ['2D'] },
    { id: 'circle', name: 'Kreis zeichnen', category: 'Basis Geometrie', shortcut: 'C', keywords: ['circle'], modes: ['2D'] },
    { id: 'arc', name: 'Bogen zeichnen', category: 'Basis Geometrie', shortcut: 'A', keywords: ['arc'], modes: ['2D'] },
    { id: 'ellipse', name: 'Ellipse zeichnen', category: 'Basis Geometrie', keywords: ['ellipse'], modes: ['2D'] },
    { id: 'polygon', name: 'Polygon zeichnen', category: 'Basis Geometrie', shortcut: 'P', keywords: ['polygon'], modes: ['2D'] },
    { id: 'spline', name: 'Spline zeichnen', category: 'Basis Geometrie', shortcut: 'S', keywords: ['spline', 'curve'], modes: ['2D'] },
    { id: 'point', name: 'Punkt setzen', category: 'Basis Geometrie', keywords: ['point'], modes: ['2D'] },
    
    // 2D Mode - Modify
    { id: 'trim', name: 'Trim/Trimmen', category: 'Sketch Modify', keywords: ['trim', 'cut'], modes: ['2D'] },
    { id: 'extend', name: 'Extend/Verlängern', category: 'Sketch Modify', keywords: ['extend'], modes: ['2D'] },
    { id: 'offset', name: 'Offset/Versetzen', category: 'Sketch Modify', keywords: ['offset'], modes: ['2D'] },
    { id: 'mirror_sketch', name: 'Spiegeln', category: 'Sketch Modify', keywords: ['mirror'], modes: ['2D'] },
    { id: 'array', name: 'Array/Muster', category: 'Sketch Modify', keywords: ['array', 'pattern'], modes: ['2D'] },
    { id: 'fillet_sketch', name: 'Fillet/Abrunden', category: 'Sketch Modify', keywords: ['fillet'], modes: ['2D'] },
    { id: 'chamfer_sketch', name: 'Fase', category: 'Sketch Modify', keywords: ['chamfer'], modes: ['2D'] },
    
    // 2D Mode - Constraints
    { id: 'horizontal', name: 'Horizontal Constraint', category: 'Constraints', keywords: ['horizontal'], modes: ['2D'] },
    { id: 'vertical', name: 'Vertikal Constraint', category: 'Constraints', keywords: ['vertical'], modes: ['2D'] },
    { id: 'parallel', name: 'Parallel Constraint', category: 'Constraints', keywords: ['parallel'], modes: ['2D'] },
    { id: 'perpendicular', name: 'Senkrecht Constraint', category: 'Constraints', keywords: ['perpendicular'], modes: ['2D'] },
    { id: 'tangent', name: 'Tangential Constraint', category: 'Constraints', keywords: ['tangent'], modes: ['2D'] },
    { id: 'equal', name: 'Gleich Constraint', category: 'Constraints', keywords: ['equal'], modes: ['2D'] },
    { id: 'fix', name: 'Fixieren', category: 'Constraints', keywords: ['fix', 'lock'], modes: ['2D'] },
    
    // 2D Mode - Dimensions
    { id: 'linear_dimension', name: 'Lineare Bemaßung', category: 'Dimensionen', keywords: ['dimension', 'linear'], modes: ['2D'] },
    { id: 'radial_dimension', name: 'Radius-Bemaßung', category: 'Dimensionen', keywords: ['dimension', 'radius'], modes: ['2D'] },
    { id: 'angular_dimension', name: 'Winkel-Bemaßung', category: 'Dimensionen', keywords: ['dimension', 'angle'], modes: ['2D'] },
    
    // 2D Mode - Tools
    { id: 'finish_sketch', name: 'Sketch beenden', category: 'Tools', shortcut: 'ESC', keywords: ['finish', 'exit'], modes: ['2D'] },
    { id: 'construction_mode', name: 'Konstruktionsmodus', category: 'Tools', keywords: ['construction'], modes: ['2D'] },
    
    // Both modes - File operations
    { id: 'importmesh', name: 'Mesh importieren', category: 'Datei', keywords: ['import', 'load', 'mesh'], modes: ['3D', '2D'] },
    { id: 'importstep', name: 'STEP importieren', category: 'Datei', keywords: ['import', 'step'], modes: ['3D', '2D'] },
    { id: 'exportstl', name: 'STL exportieren', category: 'Datei', keywords: ['export', 'stl', 'save'], modes: ['3D', '2D'] },
    { id: 'exportstep', name: 'STEP exportieren', category: 'Datei', keywords: ['export', 'step', 'save'], modes: ['3D', '2D'] },
    { id: 'export3mf', name: '3MF exportieren', category: 'Datei', keywords: ['export', '3mf'], modes: ['3D', '2D'] },
  ];

  // Filter commands by current view mode
  const commands = allCommands.filter(cmd => cmd.modes.includes(viewMode));

  const filteredCommands = commands.filter(cmd => {
    const searchLower = search.toLowerCase();
    return (
      cmd.name.toLowerCase().includes(searchLower) ||
      cmd.category.toLowerCase().includes(searchLower) ||
      cmd.keywords?.some(kw => kw.includes(searchLower))
    );
  });

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    setSelectedIndex(0);
  }, [search]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(i => Math.min(i + 1, filteredCommands.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && filteredCommands[selectedIndex]) {
      e.preventDefault();
      onSelectTool(filteredCommands[selectedIndex].id);
    }
  };

  const groupedCommands = filteredCommands.reduce((acc, cmd) => {
    if (!acc[cmd.category]) {
      acc[cmd.category] = [];
    }
    acc[cmd.category].push(cmd);
    return acc;
  }, {} as Record<string, CommandItem[]>);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-start justify-center z-50 pt-32">
      <div className="bg-neutral-800 rounded-lg shadow-2xl border border-neutral-700 w-full max-w-2xl">
        {/* Search Input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-neutral-700">
          <Search className="w-5 h-5 text-neutral-400" />
          <input
            ref={inputRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 bg-transparent text-white placeholder-neutral-500 outline-none"
            placeholder="Werkzeug suchen..."
          />
          <kbd className="px-2 py-1 bg-neutral-700 rounded text-xs text-neutral-400">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-96 overflow-y-auto">
          {Object.keys(groupedCommands).length > 0 ? (
            Object.entries(groupedCommands).map(([category, cmds]) => (
              <div key={category}>
                <div className="px-4 py-2 text-xs text-neutral-500 font-semibold uppercase bg-neutral-850">
                  {category}
                </div>
                {cmds.map((cmd, idx) => {
                  const globalIndex = filteredCommands.indexOf(cmd);
                  return (
                    <button
                      key={cmd.id}
                      onClick={() => onSelectTool(cmd.id)}
                      className={`w-full px-4 py-3 flex items-center justify-between transition-colors ${
                        globalIndex === selectedIndex
                          ? 'bg-blue-600 text-white'
                          : 'text-neutral-200 hover:bg-neutral-700'
                      }`}
                      onMouseEnter={() => setSelectedIndex(globalIndex)}
                    >
                      <span>{cmd.name}</span>
                      {cmd.shortcut && (
                        <kbd className={`px-2 py-1 rounded text-xs ${
                          globalIndex === selectedIndex
                            ? 'bg-blue-700'
                            : 'bg-neutral-700'
                        }`}>
                          {cmd.shortcut}
                        </kbd>
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          ) : (
            <div className="px-4 py-8 text-center text-neutral-500">
              Keine Ergebnisse gefunden
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-neutral-700 flex items-center justify-between text-xs text-neutral-500">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-neutral-700 rounded">↑↓</kbd>
              Navigation
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-neutral-700 rounded">↵</kbd>
              Auswählen
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Command className="w-3 h-3" />
            <span>Befehlspalette</span>
          </div>
        </div>
      </div>
    </div>
  );
}