'use client';

import React from 'react';
import { CheckSquare, AlertCircle, RefreshCw, Check, User } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

export default function CorrectionsPage() {
  const { role } = useAuth();

  const corrections = [
    {
      id: 'cor-1',
      type: 'ocr_error',
      original: 'Hbg: 12.l',
      suggested: 'Hbg: 12.1',
      doc: 'Lab_Report_2024.pdf',
      patient: 'John Doe',
      status: 'pending'
    },
    {
      id: 'cor-2',
      type: 'unit_error',
      original: 'Weight: 85 lbs',
      suggested: 'Weight: 85 kg',
      doc: 'Intake_Form.pdf',
      patient: 'Jane Smith',
      status: 'in_review'
    }
  ];

  if (role !== 'clinician' && role !== 'admin') {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-center">
        <AlertCircle className="w-16 h-16 text-red-500 mb-4" />
        <h2 className="text-2xl font-bold text-white mb-2">Access Denied</h2>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-[fadeIn_0.3s_ease-out]">
      <div>
        <h1 className="text-3xl font-bold text-white mb-2 flex items-center">
          <CheckSquare className="w-8 h-8 mr-3 text-[#3B82F6]" /> Extraction Corrections
        </h1>
        <p className="text-gray-400">Human-in-the-loop queue for flagged OCR and NER extractions.</p>
      </div>

      <div className="bg-[#111827] border border-[rgba(255,255,255,0.05)] rounded-2xl p-6 shadow-lg">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[rgba(255,255,255,0.05)] text-gray-500 text-sm uppercase tracking-wider">
              <th className="pb-4 font-medium">Issue Type</th>
              <th className="pb-4 font-medium">Original Extraction</th>
              <th className="pb-4 font-medium">Suggested Fix</th>
              <th className="pb-4 font-medium">Patient / Doc</th>
              <th className="pb-4 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[rgba(255,255,255,0.05)]">
            {corrections.map((item) => (
              <tr key={item.id} className="hover:bg-[rgba(255,255,255,0.01)] transition-colors">
                <td className="py-4">
                  <span className="text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-md bg-[rgba(59,130,246,0.1)] text-[#3B82F6] border border-[rgba(59,130,246,0.2)]">
                    {item.type.replace('_', ' ')}
                  </span>
                </td>
                <td className="py-4 font-mono text-red-400 line-through decoration-red-900/50">
                  {item.original}
                </td>
                <td className="py-4 font-mono text-emerald-400 font-medium">
                  {item.suggested}
                </td>
                <td className="py-4">
                  <div className="text-sm text-gray-300 flex items-center"><User className="w-3.5 h-3.5 mr-1" /> {item.patient}</div>
                  <div className="text-xs text-gray-500 mt-1">{item.doc}</div>
                </td>
                <td className="py-4 text-right">
                  <div className="flex justify-end space-x-2">
                    <button className="p-2 rounded-lg bg-[rgba(255,255,255,0.05)] hover:bg-[rgba(255,255,255,0.1)] text-gray-300 transition-colors" title="Edit Manually">
                      <RefreshCw className="w-4 h-4" />
                    </button>
                    <button className="px-3 py-1.5 rounded-lg bg-[#3B82F6] hover:bg-[#2563EB] text-white text-sm font-medium transition-colors flex items-center">
                      <Check className="w-4 h-4 mr-1.5" /> Accept Fix
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
