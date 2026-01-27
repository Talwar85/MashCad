import { useState } from 'react';
import { 
  ChevronLeft, ChevronRight, Shapes, Pencil, 
  Scissors, Printer, Search as SearchIcon, Wrench, Database,
  ChevronDown, ChevronRight as ChevronRightIcon
} from 'lucide-react';
import type { ViewMode, Tool } from '@/app/App';

interface SidePanelProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  activeTool: Tool | null;
  setActiveTool: (tool: Tool | null) => void;
  viewMode: ViewMode;
}

interface ToolCategory {
  id: string;
  name: string;
  icon: any;
  tools: { id: string; name: string; shortcut?: string }[];
}

export function SidePanel({ 
  collapsed, 
  onToggleCollapse, 
  activeTool, 
  setActiveTool,
  viewMode 
}: SidePanelProps) {
  const [expandedCategories, setExpandedCategories] = useState<string[]>([
    'primitives', 'modeling'
  ]);

  // 3D Mode Tools
  const categories3D: ToolCategory[] = [
    {
      id: 'primitives',
      name: 'Primitives',
      icon: Shapes,
      tools: [
        { id: 'cube', name: 'Würfel', shortcut: 'C' },
        { id: 'sphere', name: 'Kugel', shortcut: 'S' },
        { id: 'cylinder', name: 'Zylinder' },
        { id: 'cone', name: 'Kegel' },
        { id: 'torus', name: 'Torus' },
        { id: 'plane', name: 'Ebene' },
      ]
    },
    {
      id: 'modeling',
      name: 'Modeling',
      icon: Pencil,
      tools: [
        { id: 'createsketch', name: 'Create Sketch', shortcut: 'N' },
        { id: 'extrude', name: 'Extrude', shortcut: 'E' },
        { id: 'revolve', name: 'Revolve' },
        { id: 'sweep', name: 'Sweep' },
        { id: 'loft', name: 'Loft' },
        { id: 'fillet', name: 'Fillet/Abrunden' },
        { id: 'chamfer', name: 'Chamfer/Fase' },
        { id: 'shell', name: 'Shell/Aushöhlen' },
      ]
    },
    {
      id: 'transform',
      name: 'Transform',
      icon: Wrench,
      tools: [
        { id: 'move', name: 'Bewegen', shortcut: 'G' },
        { id: 'rotate', name: 'Rotieren', shortcut: 'R' },
        { id: 'scale', name: 'Skalieren', shortcut: 'S' },
        { id: 'mirror', name: 'Spiegeln' },
        { id: 'pattern_linear', name: 'Linear Pattern' },
        { id: 'pattern_circular', name: 'Circular Pattern' },
        { id: 'duplicate', name: 'Duplizieren', shortcut: 'D' },
      ]
    },
    {
      id: 'boolean',
      name: 'Boolean',
      icon: Scissors,
      tools: [
        { id: 'union', name: 'Vereinigung' },
        { id: 'subtract', name: 'Differenz' },
        { id: 'intersect', name: 'Schnittmenge' },
      ]
    },
    {
      id: 'print3d',
      name: '3D-Druck',
      icon: Printer,
      tools: [
        { id: 'hollow', name: 'Aushöhlen' },
        { id: 'wallthickness', name: 'Wandstärke prüfen' },
        { id: 'lattice', name: 'Gitterstruktur' },
        { id: 'supports', name: 'Support-Strukturen' },
      ]
    },
    {
      id: 'inspect',
      name: 'Inspect',
      icon: SearchIcon,
      tools: [
        { id: 'section', name: 'Section View' },
        { id: 'measure', name: 'Messen' },
        { id: 'checkgeometry', name: 'Geometrie prüfen' },
        { id: 'surfaceanalysis', name: 'Oberflächenanalyse' },
        { id: 'repair', name: 'Geometrie reparieren' },
      ]
    },
    {
      id: 'data',
      name: 'Datei',
      icon: Database,
      tools: [
        { id: 'importmesh', name: 'Mesh importieren' },
        { id: 'importstep', name: 'STEP importieren' },
        { id: 'exportstl', name: 'STL exportieren' },
        { id: 'exportstep', name: 'STEP exportieren' },
        { id: 'export3mf', name: '3MF exportieren' },
      ]
    }
  ];

  // 2D/Sketch Mode Tools
  const categories2D: ToolCategory[] = [
    {
      id: 'sketch_basic',
      name: 'Basis Geometrie',
      icon: Pencil,
      tools: [
        { id: 'line', name: 'Linie', shortcut: 'L' },
        { id: 'rectangle', name: 'Rechteck', shortcut: 'R' },
        { id: 'circle', name: 'Kreis', shortcut: 'C' },
        { id: 'arc', name: 'Bogen', shortcut: 'A' },
        { id: 'ellipse', name: 'Ellipse' },
        { id: 'polygon', name: 'Polygon', shortcut: 'P' },
        { id: 'spline', name: 'Spline', shortcut: 'S' },
        { id: 'point', name: 'Punkt' },
      ]
    },
    {
      id: 'sketch_modify',
      name: 'Sketch Modify',
      icon: Wrench,
      tools: [
        { id: 'trim', name: 'Trim/Trimmen' },
        { id: 'extend', name: 'Extend/Verlängern' },
        { id: 'offset', name: 'Offset/Versetzen' },
        { id: 'mirror_sketch', name: 'Spiegeln' },
        { id: 'array', name: 'Array/Muster' },
        { id: 'fillet_sketch', name: 'Fillet/Abrunden' },
        { id: 'chamfer_sketch', name: 'Fase' },
      ]
    },
    {
      id: 'sketch_constraints',
      name: 'Constraints',
      icon: Shapes,
      tools: [
        { id: 'horizontal', name: 'Horizontal' },
        { id: 'vertical', name: 'Vertikal' },
        { id: 'parallel', name: 'Parallel' },
        { id: 'perpendicular', name: 'Senkrecht' },
        { id: 'tangent', name: 'Tangential' },
        { id: 'equal', name: 'Gleich' },
        { id: 'fix', name: 'Fixieren' },
      ]
    },
    {
      id: 'sketch_dimension',
      name: 'Dimensionen',
      icon: SearchIcon,
      tools: [
        { id: 'linear_dimension', name: 'Lineare Bemaßung' },
        { id: 'radial_dimension', name: 'Radius-Bemaßung' },
        { id: 'angular_dimension', name: 'Winkel-Bemaßung' },
      ]
    },
    {
      id: 'sketch_tools',
      name: 'Tools',
      icon: Wrench,
      tools: [
        { id: 'finish_sketch', name: 'Sketch beenden', shortcut: 'ESC' },
        { id: 'construction_mode', name: 'Konstruktionsmodus' },
      ]
    }
  ];

  const categories = viewMode === '3D' ? categories3D : categories2D;

  const toggleCategory = (categoryId: string) => {
    setExpandedCategories(prev =>
      prev.includes(categoryId)
        ? prev.filter(id => id !== categoryId)
        : [...prev, categoryId]
    );
  };

  if (collapsed) {
    return (
      <div className="w-12 bg-neutral-800 border-r border-neutral-700 flex flex-col items-center py-4">
        <button
          onClick={onToggleCollapse}
          className="p-2 rounded text-neutral-300 hover:bg-neutral-700 transition-colors"
          title="Panel erweitern"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
        
        <div className="mt-6 flex flex-col gap-4">
          {categories.map(cat => {
            const Icon = cat.icon;
            return (
              <button
                key={cat.id}
                className="p-2 rounded text-neutral-400 hover:bg-neutral-700 hover:text-neutral-200 transition-colors"
                title={cat.name}
              >
                <Icon className="w-5 h-5" />
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="w-64 bg-neutral-800 border-r border-neutral-700 flex flex-col">
      {/* Header */}
      <div className="h-12 border-b border-neutral-700 flex items-center justify-between px-4">
        <h2 className="text-white font-semibold">Werkzeuge</h2>
        <button
          onClick={onToggleCollapse}
          className="p-1 rounded text-neutral-300 hover:bg-neutral-700 transition-colors"
          title="Panel einklappen"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
      </div>

      {/* Tool Categories */}
      <div className="flex-1 overflow-y-auto">
        {categories.map(category => {
          const Icon = category.icon;
          const isExpanded = expandedCategories.includes(category.id);
          
          return (
            <div key={category.id} className="border-b border-neutral-700">
              {/* Category Header */}
              <button
                onClick={() => toggleCategory(category.id)}
                className="w-full px-4 py-3 flex items-center justify-between hover:bg-neutral-700/50 transition-colors"
              >
                <div className="flex items-center gap-2 text-neutral-200">
                  <Icon className="w-4 h-4" />
                  <span className="font-medium text-sm">{category.name}</span>
                </div>
                {isExpanded ? (
                  <ChevronDown className="w-4 h-4 text-neutral-400" />
                ) : (
                  <ChevronRightIcon className="w-4 h-4 text-neutral-400" />
                )}
              </button>

              {/* Category Tools */}
              {isExpanded && (
                <div className="bg-neutral-850">
                  {category.tools.map(tool => (
                    <button
                      key={tool.id}
                      onClick={() => setActiveTool(tool.id)}
                      className={`w-full px-4 py-2 pl-10 flex items-center justify-between text-sm transition-colors ${
                        activeTool === tool.id
                          ? 'bg-blue-600 text-white'
                          : 'text-neutral-300 hover:bg-neutral-700'
                      }`}
                    >
                      <span>{tool.name}</span>
                      {tool.shortcut && (
                        <kbd className="text-xs px-1.5 py-0.5 rounded bg-neutral-700/50">
                          {tool.shortcut}
                        </kbd>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer Info */}
      <div className="p-4 border-t border-neutral-700 text-xs text-neutral-500">
        <div>Strg+K für Schnellzugriff</div>
        <div className="mt-1">{viewMode}-Modus aktiv</div>
      </div>
    </div>
  );
}