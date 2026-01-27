import { Box, Circle, Move, RotateCw, Scissors } from 'lucide-react';
import type { ViewMode, Tool } from '@/app/App';

interface QuickActionsProps {
  viewMode: ViewMode;
  activeTool: Tool | null;
  setActiveTool: (tool: Tool | null) => void;
}

export function QuickActions({ viewMode, activeTool, setActiveTool }: QuickActionsProps) {
  const quickTools = [
    { id: 'cube', icon: Box, label: 'Würfel', color: 'bg-blue-600 hover:bg-blue-700' },
    { id: 'circle', icon: Circle, label: 'Kreis', color: 'bg-green-600 hover:bg-green-700' },
    { id: 'move', icon: Move, label: 'Bewegen', color: 'bg-purple-600 hover:bg-purple-700' },
    { id: 'rotate', icon: RotateCw, label: 'Rotieren', color: 'bg-orange-600 hover:bg-orange-700' },
    { id: 'union', icon: Scissors, label: 'Boolean', color: 'bg-pink-600 hover:bg-pink-700' },
  ];

  return (
    <div className="absolute right-4 top-1/2 -translate-y-1/2 flex flex-col gap-2">
      {quickTools.map((tool) => {
        const Icon = tool.icon;
        return (
          <button
            key={tool.id}
            onClick={() => setActiveTool(tool.id)}
            className={`p-3 rounded-lg shadow-lg transition-all group relative ${
              activeTool === tool.id
                ? `${tool.color} scale-110 ring-2 ring-white/50`
                : `${tool.color} opacity-80 hover:opacity-100`
            }`}
            title={tool.label}
          >
            <Icon className="w-6 h-6 text-white" />
            
            {/* Tooltip */}
            <div className="absolute right-full mr-3 top-1/2 -translate-y-1/2 bg-neutral-900 text-white text-sm px-3 py-1.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
              {tool.label}
            </div>
          </button>
        );
      })}
    </div>
  );
}
