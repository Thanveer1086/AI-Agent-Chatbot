import React, { useState, useEffect } from 'react';
import { Cpu, RefreshCw, CheckCircle2, Server, Terminal, Wrench } from 'lucide-react';
import { MCPServerInfo, MCPTool } from '../../types/admin';

export const MCPInspector: React.FC = () => {
  const [servers, setServers] = useState<MCPServerInfo[]>([]);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isReloading, setIsReloading] = useState<boolean>(false);

  const fetchMCPState = async () => {
    setIsLoading(true);
    try {
      const [serversResp, toolsResp] = await Promise.all([
        fetch('/api/mcp/servers'),
        fetch('/api/mcp/tools'),
      ]);
      const serversData = await serversResp.json();
      const toolsData = await toolsResp.json();

      setServers(serversData.servers || []);
      setTools(toolsData.tools || []);
    } catch (err) {
      console.error('Error fetching MCP state:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReload = async () => {
    setIsReloading(true);
    try {
      await fetch('/api/mcp/reload', { method: 'POST' });
      await fetchMCPState();
    } catch (err) {
      console.error('Error reloading MCP tools:', err);
    } finally {
      setIsReloading(false);
    }
  };

  useEffect(() => {
    fetchMCPState();
  }, []);

  return (
    <div className="h-full overflow-y-auto bg-slate-50 p-6 md:p-10 lg:px-20 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Model Context Protocol (MCP) Inspector</h2>
          <p className="text-xs text-slate-500">
            Real-time inspection of dynamic tool discovery, server connections, and JSON schemas.
          </p>
        </div>
        <button
          onClick={handleReload}
          disabled={isReloading}
          className="flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isReloading ? 'animate-spin' : ''}`} />
          Reload Tool Catalog
        </button>
      </div>

      {/* Servers Grid */}
      <div>
        <h3 className="font-semibold text-slate-800 text-sm mb-3">Configured MCP Servers</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {servers.map((srv, idx) => (
            <div key={idx} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Server className="h-4 w-4 text-blue-600" />
                  <span className="font-bold text-slate-800 text-sm">{srv.name}</span>
                </div>
                <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-200">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  {srv.status.toUpperCase()}
                </span>
              </div>
              <div className="mt-4 flex items-center justify-between text-xs text-slate-500 font-mono">
                <span>Transport: {srv.transport}</span>
                <span>{srv.tool_count} tools exposed</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Discovered Tools List */}
      <div>
        <h3 className="font-semibold text-slate-800 text-sm mb-3">
          Dynamically Loaded Tools ({tools.length})
        </h3>
        <div className="space-y-3">
          {tools.length === 0 ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-xs text-slate-400">
              No MCP tools discovered. Click "Reload Tool Catalog" to query servers.
            </div>
          ) : (
            tools.map((t, idx) => (
              <div key={idx} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Wrench className="h-4 w-4 text-blue-600" />
                    <span className="font-mono text-sm font-bold text-slate-900">{t.tool_name}</span>
                    <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-mono text-slate-600 border border-slate-200">
                      {t.server_name}
                    </span>
                  </div>
                  <span className="text-[11px] font-mono text-slate-400">{t.transport}</span>
                </div>

                <p className="mt-2 text-xs text-slate-600">{t.description}</p>

                {/* Schema JSON preview */}
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Input Schema
                  </span>
                  <pre className="mt-1 font-mono text-[11px] text-slate-700 overflow-x-auto">
                    {JSON.stringify(t.input_schema, null, 2)}
                  </pre>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
