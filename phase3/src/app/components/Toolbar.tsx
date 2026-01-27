import { 
  Box, Circle, Square, 
  Move, RotateCw, Copy, Trash2, Undo2, Redo2, 
  Save, FolderOpen, Download, Upload, Search, Settings,
  Command, ChevronDown, Hexagon, Cylinder as CylinderIcon
} from 'lucide-react';
import type { ViewMode, Tool } from '@/app/App';

interface ToolbarProps {
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
  activeTool: Tool | null;
  setActiveTool: (tool: Tool | null) => void;
  onCommandPaletteOpen: () => void;
}

export function Toolbar({ 
  viewMode, 
  setViewMode, 
  activeTool, 
  setActiveTool,
  onCommandPaletteOpen 
}: ToolbarProps) {
  
  const toolGroups = [
    {
      name: 'Dateien',
      tools: [
        { id: 'new', icon: FolderOpen, label: 'Neu' },
        { id: 'save', icon: Save, label: 'Speichern' },
        { id: 'import', icon: Upload, label: 'Import' },
        { id: 'export', icon: Download, label: 'Export' },
      ]
    },
    {
      name: 'Bearbeiten',
      tools: [
        { id: 'undo', icon: Undo2, label: 'Rückgängig' },
        { id: 'redo', icon: Redo2, label: 'Wiederholen' },
      ]
    },
    {
      name: 'Primitives',
      tools: [
        { id: 'cube', icon: Box, label: 'Würfel' },
        { id: 'circle', icon: Circle, label: 'Kreis' },
        { id: 'square', icon: Square, label: 'Rechteck' },
        { id: 'hexagon', icon: Hexagon, label: 'Sechseck' },
        { id: 'cylinder', icon: CylinderIcon, label: 'Zylinder' },
      ]
    },
    {
      name: 'Transform',
      tools: [
        { id: 'move', icon: Move, label: 'Bewegen' },
        { id: 'rotate', icon: RotateCw, label: 'Rotieren' },
        { id: 'copy', icon: Copy, label: 'Kopieren' },
        { id: 'delete', icon: Trash2, label: 'Löschen' },
      ]
    }
  ];

  return (
    <div className="h-14 bg-neutral-800 border-b border-neutral-700 flex items-center px-4 gap-4">
      {/* Logo / App Name */}
      <div className="text-white font-semibold text-lg mr-4">
        3D CAD
      </div>

      {/* View Mode Toggle */}
      <div className="flex gap-2 mr-4">
        <button
          onClick={() => setViewMode('3D')}
          className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
            viewMode === '3D' 
              ? 'bg-blue-600 text-white' 
              : 'bg-neutral-700 text-neutral-300 hover:bg-neutral-600'
          }`}
        >
          3D
        </button>
        <button
          onClick={() => setViewMode('2D')}
          className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
            viewMode === '2D' 
              ? 'bg-blue-600 text-white' 
              : 'bg-neutral-700 text-neutral-300 hover:bg-neutral-600'
          }`}
        >
          2D
        </button>
      </div>

      {/* Tool Groups */}
      <div className="flex-1 flex items-center gap-1 overflow-x-auto">
        {toolGroups.map((group, idx) => (
          <div key={group.name} className="flex items-center gap-1">
            {idx > 0 && <div className="w-px h-6 bg-neutral-700 mx-2" />}
            <div className="flex items-center gap-1">
              {group.tools.map((tool) => {
                const Icon = tool.icon;
                return (
                  <button
                    key={tool.id}
                    onClick={() => setActiveTool(tool.id)}
                    className={`p-2 rounded transition-colors relative group ${
                      activeTool === tool.id
                        ? 'bg-blue-600 text-white'
                        : 'text-neutral-300 hover:bg-neutral-700'
                    }`}
                    title={tool.label}
                  >
                    <Icon className="w-5 h-5" />
                    
                    {/* Tooltip */}
                    <div className="absolute top-full mt-1 left-1/2 -translate-x-1/2 bg-neutral-900 text-white text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
                      {tool.label}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={onCommandPaletteOpen}
          className="p-2 rounded text-neutral-300 hover:bg-neutral-700 transition-colors flex items-center gap-2 text-sm"
          title="Befehlspalette (Strg+K)"
        >
          <Search className="w-5 h-5" />
          <span className="hidden md:inline">Suchen</span>
          <kbd className="hidden md:inline px-1.5 py-0.5 bg-neutral-700 rounded text-xs">⌘K</kbd>
        </button>
        
        <button
          className="p-2 rounded text-neutral-300 hover:bg-neutral-700 transition-colors"
          title="Einstellungen"
        >
          <Settings className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}