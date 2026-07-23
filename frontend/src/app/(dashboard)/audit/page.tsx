'use client';

import React from 'react';
import { Shield, Clock, HardDrive, Terminal } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

export default function AuditPage() {
  const { role } = useAuth();

  const auditLogs = [
    {
      id: 'aud-1',
      agent: 'IngestionAgent',
      action: 'Document Upload & Triage',
      status: 'success',
      duration: '42ms',
      timestamp: '2024-01-15 14:32:01 UTC',
      hash: 'a7b8c9d0e1f2...'
    },
    {
      id: 'aud-2',
      agent: 'OCRAgent',
      action: 'PaddleOCR Layout Extraction',
      status: 'success',
      duration: '2105ms',
      timestamp: '2024-01-15 14:32:03 UTC',
      hash: 'b1c2d3e4f5g6...'
    },
    {
      id: 'aud-3',
      agent: 'ReasoningAgent',
      action: 'Insight Generation (Claude-3.5-Sonnet)',
      status: 'success',
      duration: '4890ms',
      timestamp: '2024-01-15 14:32:10 UTC',
      hash: 'f9e8d7c6b5a4...'
    }
  ];

  if (role !== 'admin') {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-center">
        <Shield className="w-16 h-16 text-red-500 mb-4" />
        <h2 className="text-2xl font-bold text-white mb-2">Access Denied</h2>
        <p className="text-gray-400">System audit logs are restricted to platform administrators.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-[fadeIn_0.3s_ease-out]">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2 flex items-center">
            <Shield className="w-8 h-8 mr-3 text-indigo-400" /> System Audit Ledger
          </h1>
          <p className="text-gray-400">Cryptographically verifiable log of every agent action and model inference.</p>
        </div>
      </div>

      <div className="bg-[#111827] border border-[rgba(255,255,255,0.05)] rounded-2xl overflow-hidden shadow-lg">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-[rgba(0,0,0,0.2)] border-b border-[rgba(255,255,255,0.05)] text-gray-500 text-xs uppercase tracking-wider">
                <th className="p-4 font-medium">Timestamp</th>
                <th className="p-4 font-medium">Agent</th>
                <th className="p-4 font-medium">Action</th>
                <th className="p-4 font-medium">Latency</th>
                <th className="p-4 font-medium">I/O Hash</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[rgba(255,255,255,0.05)] font-mono text-sm">
              {auditLogs.map((log) => (
                <tr key={log.id} className="hover:bg-[rgba(255,255,255,0.01)] transition-colors">
                  <td className="p-4 text-gray-400 flex items-center">
                    <Clock className="w-3.5 h-3.5 mr-2" /> {log.timestamp}
                  </td>
                  <td className="p-4 text-[#3B82F6] font-medium">
                    <div className="flex items-center">
                      <Terminal className="w-3.5 h-3.5 mr-2 text-gray-500" /> {log.agent}
                    </div>
                  </td>
                  <td className="p-4 text-gray-300">
                    {log.action}
                  </td>
                  <td className="p-4 text-emerald-400">
                    {log.duration}
                  </td>
                  <td className="p-4 text-gray-500 flex items-center">
                    <HardDrive className="w-3.5 h-3.5 mr-2" /> {log.hash}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
