'use client';

import React, { useState } from 'react';
import { Activity, Check, X, Edit3, ShieldAlert, FileSearch, User } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

export default function ClinicianReviewPage() {
  const { role } = useAuth();
  const [activeTab, setActiveTab] = useState<'pending' | 'reviewed'>('pending');

  // Mock data
  const queue = [
    {
      id: 'rev-1',
      patient_name: 'John Doe',
      insight_type: 'risk_flag',
      text: 'Patient demonstrates progressive eGFR decline (58 → 42 mL/min/1.73m2). Metformin dose adjustment may be indicated.',
      severity: 'high',
      confidence: 0.94,
      date: '2 hours ago'
    },
    {
      id: 'rev-2',
      patient_name: 'Jane Smith',
      insight_type: 'medication',
      text: 'New prescription for Atorvastatin 40mg detected. Baseline ALT not found in recent history.',
      severity: 'moderate',
      confidence: 0.98,
      date: '5 hours ago'
    }
  ];

  if (role !== 'clinician' && role !== 'admin') {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-center">
        <ShieldAlert className="w-16 h-16 text-red-500 mb-4" />
        <h2 className="text-2xl font-bold text-white mb-2">Access Denied</h2>
        <p className="text-gray-400">You must be logged in as a clinician to view this page.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-[fadeIn_0.3s_ease-out]">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2 flex items-center">
            <Activity className="w-8 h-8 mr-3 text-emerald-400" /> Clinician Review Queue
          </h1>
          <p className="text-gray-400">Review, approve, or modify high-priority insights before they are released to patients.</p>
        </div>
      </div>

      <div className="bg-[#111827] border border-[rgba(255,255,255,0.05)] rounded-2xl overflow-hidden shadow-lg">
        {/* Tabs */}
        <div className="flex border-b border-[rgba(255,255,255,0.05)]">
          <button 
            onClick={() => setActiveTab('pending')}
            className={`flex-1 py-4 text-center font-medium transition-colors ${activeTab === 'pending' ? 'text-[#3B82F6] border-b-2 border-[#3B82F6] bg-[rgba(59,130,246,0.05)]' : 'text-gray-400 hover:bg-[rgba(255,255,255,0.02)]'}`}
          >
            Pending Review ({queue.length})
          </button>
          <button 
            onClick={() => setActiveTab('reviewed')}
            className={`flex-1 py-4 text-center font-medium transition-colors ${activeTab === 'reviewed' ? 'text-[#3B82F6] border-b-2 border-[#3B82F6] bg-[rgba(59,130,246,0.05)]' : 'text-gray-400 hover:bg-[rgba(255,255,255,0.02)]'}`}
          >
            Recently Reviewed
          </button>
        </div>

        {/* Queue Items */}
        <div className="divide-y divide-[rgba(255,255,255,0.05)]">
          {queue.map((item) => (
            <div key={item.id} className="p-6 hover:bg-[rgba(255,255,255,0.01)] transition-colors">
              <div className="flex justify-between items-start mb-4">
                <div className="flex items-center space-x-3">
                  <span className={`text-xs font-bold uppercase tracking-wider px-2 py-1 rounded-md ${item.severity === 'high' ? 'bg-[rgba(239,68,68,0.1)] text-red-400 border border-[rgba(239,68,68,0.2)]' : 'bg-[rgba(234,179,8,0.1)] text-yellow-400 border border-[rgba(234,179,8,0.2)]'}`}>
                    {item.severity} Priority
                  </span>
                  <span className="text-sm text-gray-500">{item.date}</span>
                </div>
                <div className="flex items-center text-sm font-medium text-gray-300 bg-[rgba(255,255,255,0.05)] px-3 py-1.5 rounded-lg">
                  <User className="w-4 h-4 mr-2 text-gray-400" /> {item.patient_name}
                </div>
              </div>
              
              <div className="mb-6">
                <p className="text-lg text-white font-medium bg-[rgba(0,0,0,0.2)] p-4 rounded-lg border border-[rgba(255,255,255,0.05)]">
                  {item.text}
                </p>
              </div>
              
              <div className="flex items-center justify-between border-t border-[rgba(255,255,255,0.05)] pt-4 mt-4">
                <button className="text-sm text-[#3B82F6] hover:underline flex items-center">
                  <FileSearch className="w-4 h-4 mr-1.5" /> View Evidence & Patient File
                </button>
                <div className="flex space-x-3">
                  <button className="flex items-center px-4 py-2 rounded-lg border border-gray-600 text-gray-300 hover:bg-[rgba(255,255,255,0.05)] transition-colors">
                    <Edit3 className="w-4 h-4 mr-2" /> Modify
                  </button>
                  <button className="flex items-center px-4 py-2 rounded-lg border border-red-900/50 text-red-400 hover:bg-[rgba(239,68,68,0.1)] transition-colors">
                    <X className="w-4 h-4 mr-2" /> Reject
                  </button>
                  <button className="flex items-center px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg transition-colors">
                    <Check className="w-4 h-4 mr-2" /> Approve
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
