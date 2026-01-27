import { useRef, useEffect } from 'react';
import type { ViewMode, Tool } from '@/app/App';

interface Viewport3DProps {
  viewMode: ViewMode;
  activeTool: Tool | null;
}

export function Viewport3D({ viewMode, activeTool }: Viewport3DProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    canvas.width = canvas.offsetWidth * window.devicePixelRatio;
    canvas.height = canvas.offsetHeight * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    // Draw grid
    const drawGrid = () => {
      const gridSize = 50;
      const width = canvas.offsetWidth;
      const height = canvas.offsetHeight;

      ctx.strokeStyle = viewMode === '3D' ? '#2a2a2a' : '#2a2a2a';
      ctx.lineWidth = 0.5;

      // Vertical lines
      for (let x = 0; x <= width; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }

      // Horizontal lines
      for (let y = 0; y <= height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Origin axes
      const centerX = width / 2;
      const centerY = height / 2;

      // X axis (red)
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(centerX + 200, centerY);
      ctx.stroke();

      // Y axis (green)
      ctx.strokeStyle = '#22c55e';
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      if (viewMode === '3D') {
        ctx.lineTo(centerX - 100, centerY - 100);
      } else {
        ctx.lineTo(centerX, centerY - 200);
      }
      ctx.stroke();

      // Z axis (blue) - only in 3D mode
      if (viewMode === '3D') {
        ctx.strokeStyle = '#3b82f6';
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(centerX, centerY + 200);
        ctx.stroke();
      }

      // Axis labels
      ctx.fillStyle = '#ffffff';
      ctx.font = '14px sans-serif';
      ctx.fillText('X', centerX + 210, centerY + 5);
      if (viewMode === '3D') {
        ctx.fillText('Y', centerX - 110, centerY - 110);
        ctx.fillText('Z', centerX + 5, centerY + 220);
      } else {
        ctx.fillText('Y', centerX + 5, centerY - 210);
      }
    };

    drawGrid();

    // Cleanup
    return () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [viewMode]);

  return (
    <div className="w-full h-full bg-neutral-900 relative">
      <canvas
        ref={canvasRef}
        className="w-full h-full"
        style={{ imageRendering: 'crisp-edges' }}
      />
      
      {/* Viewport Info */}
      <div className="absolute top-4 left-4 bg-neutral-800/90 border border-neutral-700 rounded px-3 py-2 text-sm">
        <div className="text-neutral-300">
          <span className="text-neutral-500">Modus:</span> {viewMode}
        </div>
        {activeTool && (
          <div className="text-neutral-300 mt-1">
            <span className="text-neutral-500">Werkzeug:</span> {activeTool}
          </div>
        )}
      </div>

      {/* View Controls Hint */}
      <div className="absolute bottom-4 right-4 bg-neutral-800/90 border border-neutral-700 rounded px-3 py-2 text-xs text-neutral-400 space-y-1">
        <div>Rechtsklick + Ziehen: Ansicht drehen</div>
        <div>Scroll: Zoomen</div>
        <div>Mittlere Maustaste: Pan</div>
      </div>
    </div>
  );
}
