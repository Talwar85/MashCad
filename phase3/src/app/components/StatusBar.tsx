import { Activity, Box, Grid3X3 } from 'lucide-react';
import type { ViewMode, Tool } from '@/app/App';

interface StatusBarProps {
  activeTool: Tool | null;
  viewMode: ViewMode;
}

export function StatusBar({ activeTool, viewMode }: StatusBarProps) {
  return (
    <div className="h-8 bg-neutral-800 border-t border-neutral-700 flex items-center justify-between px-4 text-xs text-neutral-400">
      {/* Left side - Status */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-green-500" />
          <span>Bereit</span>
        </div>
        
        {activeTool && (
          <div className="flex items-center gap-1.5">
            <Box className="w-3.5 h-3.5" />
            <span>Werkzeug: {activeTool}</span>
          </div>
        )}
      </div>

      {/* Center - Coordinates placeholder */}
      <div className="flex items-center gap-4">
        <span>X: 0.00</span>
        <span>Y: 0.00</span>
        <span>Z: 0.00</span>
      </div>

      {/* Right side - View info */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <Grid3X3 className="w-3.5 h-3.5" />
          <span>Grid: 10mm</span>
        </div>
        
        <div className="flex items-center gap-1.5">
          <span>Modus: {viewMode}</span>
        </div>

        <div className="px-2 py-0.5 bg-neutral-700 rounded">
          100%
        </div>
      </div>
    </div>
  );
}