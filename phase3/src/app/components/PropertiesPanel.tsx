import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Tool } from '@/app/App';

interface PropertiesPanelProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  activeTool: Tool | null;
}

export function PropertiesPanel({ collapsed, onToggleCollapse, activeTool }: PropertiesPanelProps) {
  if (collapsed) {
    return (
      <div className="w-12 bg-neutral-800 border-l border-neutral-700 flex flex-col items-center py-4">
        <button
          onClick={onToggleCollapse}
          className="p-2 rounded text-neutral-300 hover:bg-neutral-700 transition-colors"
          title="Properties erweitern"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
      </div>
    );
  }

  return (
    <div className="w-80 bg-neutral-800 border-l border-neutral-700 flex flex-col">
      {/* Header */}
      <div className="h-12 border-b border-neutral-700 flex items-center justify-between px-4">
        <h2 className="text-white font-semibold">Eigenschaften</h2>
        <button
          onClick={onToggleCollapse}
          className="p-1 rounded text-neutral-300 hover:bg-neutral-700 transition-colors"
          title="Panel einklappen"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {activeTool ? (
          <>
            {/* Object Properties */}
            <div>
              <h3 className="text-neutral-400 text-xs uppercase font-semibold mb-2">
                Objekt
              </h3>
              <div className="space-y-2">
                <div>
                  <label className="text-neutral-300 text-sm block mb-1">Name</label>
                  <input
                    type="text"
                    className="w-full bg-neutral-700 border border-neutral-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
                    placeholder="Objekt 1"
                  />
                </div>
              </div>
            </div>

            {/* Transform Properties */}
            <div>
              <h3 className="text-neutral-400 text-xs uppercase font-semibold mb-2">
                Transform
              </h3>
              <div className="space-y-3">
                <div>
                  <label className="text-neutral-300 text-sm block mb-1">Position</label>
                  <div className="grid grid-cols-3 gap-2">
                    {['X', 'Y', 'Z'].map(axis => (
                      <div key={axis}>
                        <label className="text-neutral-500 text-xs">{axis}</label>
                        <input
                          type="number"
                          className="w-full bg-neutral-700 border border-neutral-600 rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
                          defaultValue="0"
                          step="0.1"
                        />
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-neutral-300 text-sm block mb-1">Rotation</label>
                  <div className="grid grid-cols-3 gap-2">
                    {['X', 'Y', 'Z'].map(axis => (
                      <div key={axis}>
                        <label className="text-neutral-500 text-xs">{axis}</label>
                        <input
                          type="number"
                          className="w-full bg-neutral-700 border border-neutral-600 rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
                          defaultValue="0"
                          step="1"
                        />
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-neutral-300 text-sm block mb-1">Skalierung</label>
                  <div className="grid grid-cols-3 gap-2">
                    {['X', 'Y', 'Z'].map(axis => (
                      <div key={axis}>
                        <label className="text-neutral-500 text-xs">{axis}</label>
                        <input
                          type="number"
                          className="w-full bg-neutral-700 border border-neutral-600 rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
                          defaultValue="1"
                          step="0.1"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Material Properties */}
            <div>
              <h3 className="text-neutral-400 text-xs uppercase font-semibold mb-2">
                Material
              </h3>
              <div className="space-y-2">
                <div>
                  <label className="text-neutral-300 text-sm block mb-1">Farbe</label>
                  <div className="flex gap-2">
                    <input
                      type="color"
                      className="w-12 h-8 bg-neutral-700 border border-neutral-600 rounded cursor-pointer"
                      defaultValue="#3b82f6"
                    />
                    <input
                      type="text"
                      className="flex-1 bg-neutral-700 border border-neutral-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
                      defaultValue="#3b82f6"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-neutral-300 text-sm block mb-1">Transparenz</label>
                  <input
                    type="range"
                    className="w-full"
                    min="0"
                    max="100"
                    defaultValue="100"
                  />
                </div>
              </div>
            </div>

            {/* Dimensions */}
            {(activeTool === 'cube' || activeTool === 'cylinder' || activeTool === 'sphere') && (
              <div>
                <h3 className="text-neutral-400 text-xs uppercase font-semibold mb-2">
                  Dimensionen
                </h3>
                <div className="space-y-2">
                  {activeTool === 'cube' && (
                    <>
                      <div>
                        <label className="text-neutral-300 text-sm block mb-1">Breite</label>
                        <input
                          type="number"
                          className="w-full bg-neutral-700 border border-neutral-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
                          defaultValue="1"
                          step="0.1"
                        />
                      </div>
                      <div>
                        <label className="text-neutral-300 text-sm block mb-1">Höhe</label>
                        <input
                          type="number"
                          className="w-full bg-neutral-700 border border-neutral-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
                          defaultValue="1"
                          step="0.1"
                        />
                      </div>
                      <div>
                        <label className="text-neutral-300 text-sm block mb-1">Tiefe</label>
                        <input
                          type="number"
                          className="w-full bg-neutral-700 border border-neutral-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
                          defaultValue="1"
                          step="0.1"
                        />
                      </div>
                    </>
                  )}
                  {activeTool === 'sphere' && (
                    <div>
                      <label className="text-neutral-300 text-sm block mb-1">Radius</label>
                      <input
                        type="number"
                        className="w-full bg-neutral-700 border border-neutral-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
                        defaultValue="1"
                        step="0.1"
                      />
                    </div>
                  )}
                  {activeTool === 'cylinder' && (
                    <>
                      <div>
                        <label className="text-neutral-300 text-sm block mb-1">Radius</label>
                        <input
                          type="number"
                          className="w-full bg-neutral-700 border border-neutral-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
                          defaultValue="1"
                          step="0.1"
                        />
                      </div>
                      <div>
                        <label className="text-neutral-300 text-sm block mb-1">Höhe</label>
                        <input
                          type="number"
                          className="w-full bg-neutral-700 border border-neutral-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
                          defaultValue="2"
                          step="0.1"
                        />
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="text-center text-neutral-500 py-8">
            <p className="text-sm">Kein Objekt ausgewählt</p>
            <p className="text-xs mt-2">Wählen Sie ein Werkzeug, um fortzufahren</p>
          </div>
        )}
      </div>
    </div>
  );
}
