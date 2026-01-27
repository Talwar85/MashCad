import { useState, useEffect } from 'react';
import { Toolbar } from '@/app/components/Toolbar';
import { SidePanel } from '@/app/components/SidePanel';
import { PropertiesPanel } from '@/app/components/PropertiesPanel';
import { Viewport3D } from '@/app/components/Viewport3D';
import { CommandPalette } from '@/app/components/CommandPalette';
import { StatusBar } from '@/app/components/StatusBar';
import { QuickActions } from '@/app/components/QuickActions';

export type ViewMode = '3D' | '2D';
export type Tool = string;

export default function App() {
  const [viewMode, setViewMode] = useState<ViewMode>('3D');
  const [activeTool, setActiveTool] = useState<Tool | null>(null);
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [sidePanelCollapsed, setSidePanelCollapsed] = useState(false);
  const [propertiesPanelCollapsed, setPropertiesPanelCollapsed] = useState(false);

  // Command Palette Shortcut (Ctrl+K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setShowCommandPalette(true);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="h-screen flex flex-col bg-neutral-900 text-white overflow-hidden">
      {/* Top Toolbar */}
      <Toolbar 
        viewMode={viewMode} 
        setViewMode={setViewMode}
        activeTool={activeTool}
        setActiveTool={setActiveTool}
        onCommandPaletteOpen={() => setShowCommandPalette(true)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Side Panel */}
        <SidePanel 
          collapsed={sidePanelCollapsed}
          onToggleCollapse={() => setSidePanelCollapsed(!sidePanelCollapsed)}
          activeTool={activeTool}
          setActiveTool={setActiveTool}
          viewMode={viewMode}
        />

        {/* Center Viewport */}
        <div className="flex-1 relative">
          <Viewport3D viewMode={viewMode} activeTool={activeTool} />
          
          {/* Floating Quick Actions */}
          <QuickActions 
            viewMode={viewMode}
            activeTool={activeTool}
            setActiveTool={setActiveTool}
          />
        </div>

        {/* Right Properties Panel */}
        <PropertiesPanel 
          collapsed={propertiesPanelCollapsed}
          onToggleCollapse={() => setPropertiesPanelCollapsed(!propertiesPanelCollapsed)}
          activeTool={activeTool}
        />
      </div>

      {/* Bottom Status Bar */}
      <StatusBar activeTool={activeTool} viewMode={viewMode} />

      {/* Command Palette */}
      {showCommandPalette && (
        <CommandPalette 
          onClose={() => setShowCommandPalette(false)}
          onSelectTool={(tool) => {
            setActiveTool(tool);
            setShowCommandPalette(false);
          }}
          viewMode={viewMode}
        />
      )}
    </div>
  );
}