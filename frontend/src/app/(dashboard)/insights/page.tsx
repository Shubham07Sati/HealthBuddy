'use client';

import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { patientsApi } from '@/lib/api';
import { Lightbulb, AlertTriangle, CheckCircle, ChevronDown, ChevronUp, FileSearch, ShieldAlert } from 'lucide-react';

export default function InsightsPage() {
  const { user } = useAuth();
  const [insights, setInsights] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Mock data removed in favor of real API call

  useEffect(() => {
    if (user?.id) {
      patientsApi.getInsights(user.id)
        .then((res: any) => setInsights(res.items || []))
        .catch(console.error)
        .finally(() => setLoading(false));
    }
  }, [user]);

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  const getSeverityColors = (severity: string) => {
    switch(severity) {
      case 'critical': return 'border-red-500 bg-[rgba(239,68,68,0.05)] text-red-500';
      case 'high': return 'border-orange-500 bg-[rgba(249,115,22,0.05)] text-orange-500';
      case 'moderate': return 'border-yellow-500 bg-[rgba(234,179,8,0.05)] text-yellow-500';
      default: return 'border-blue-500 bg-[rgba(59,130,246,0.05)] text-blue-500';
    }
  };

  return (
    <div className="space-y-8 animate-[fadeInUp_0.4s_ease-out]">
      <div className="relative overflow-hidden bg-gradient-to-br from-amber-500/10 via-amber-600/5 to-transparent border border-amber-500/20 rounded-3xl p-8">
        <h1 className="text-3xl font-black text-white mb-2 flex items-center gap-3">
          <Lightbulb className="w-8 h-8 text-amber-400" /> Generated Insights
        </h1>
        <p className="text-gray-400">AI-generated, evidence-grounded observations verified by an independent agent.</p>
        <div className="mt-4 flex items-center gap-4 text-sm">
          <span className="flex items-center gap-1.5 text-emerald-400"><CheckCircle className="w-4 h-4" /> {insights.length} Verified</span>
          <span className="flex items-center gap-1.5 text-amber-400"><AlertTriangle className="w-4 h-4" /> {insights.filter((i:any) => i.requires_clinician_review).length} Require Review</span>
        </div>
      </div>

      <div className="space-y-6">
        {insights.map((insight) => {
          const isExpanded = expandedId === insight.draft_id;
          const sevColors = getSeverityColors(insight.severity);
          
          return (
            <div 
              key={insight.draft_id} 
              className={`bg-[#111827] border-l-4 rounded-r-2xl rounded-l-md shadow-lg overflow-hidden transition-all duration-300 ${isExpanded ? 'border-y border-r border-[rgba(255,255,255,0.1)] my-8' : 'border-y border-r border-[rgba(255,255,255,0.05)] hover:bg-[rgba(255,255,255,0.02)]'}`}
              style={{ borderLeftColor: sevColors.split(' ')[0].replace('border-', '') }}
            >
              {/* Header / Summary */}
              <div 
                className="p-6 cursor-pointer flex items-start justify-between"
                onClick={() => toggleExpand(insight.draft_id)}
              >
                <div className="flex-1 pr-8">
                  <div className="flex items-center space-x-3 mb-3">
                    <span className={`text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-md ${sevColors}`}>
                      {insight.severity} Priority
                    </span>
                    <span className="text-xs text-gray-500 flex items-center">
                      <CheckCircle className="w-3.5 h-3.5 mr-1 text-emerald-500" /> Verified
                    </span>
                  </div>
                  <p className="text-lg text-white font-medium leading-relaxed">
                    {insight.patient_facing_text}
                  </p>
                </div>
                <div className="shrink-0 pt-2">
                  {isExpanded ? <ChevronUp className="w-6 h-6 text-gray-500" /> : <ChevronDown className="w-6 h-6 text-gray-500" />}
                </div>
              </div>

              {/* Expanded Details */}
              <div className={`transition-all duration-300 ease-in-out ${isExpanded ? 'max-h-[1000px] opacity-100' : 'max-h-0 opacity-0'} overflow-hidden`}>
                <div className="p-6 pt-0 border-t border-[rgba(255,255,255,0.05)] bg-[rgba(0,0,0,0.2)]">
                  
                  {/* Clinician View */}
                  <div className="my-6">
                    <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Clinician Translation</h4>
                    <p className="text-gray-300 font-mono text-sm bg-[#111827] p-4 rounded-lg border border-[rgba(255,255,255,0.05)]">
                      {insight.clinician_facing_text}
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
                    {/* Assertions */}
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 flex items-center">
                        <ShieldAlert className="w-4 h-4 mr-1.5" /> Atomic Assertions
                      </h4>
                      <ul className="space-y-2">
                        {insight.atomic_assertions?.map((assertion: any, i: number) => (
                          <li key={i} className="flex items-start text-sm text-gray-300 bg-[rgba(255,255,255,0.02)] p-2.5 rounded-lg">
                            <CheckCircle className="w-4 h-4 text-emerald-500 mr-2 shrink-0 mt-0.5" />
                            <span>{assertion.assertion_text}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Evidence */}
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3 flex items-center">
                        <FileSearch className="w-4 h-4 mr-1.5" /> Retrieved Evidence
                      </h4>
                      <div className="space-y-3">
                        {insight.evidence?.map((ev: any, i: number) => (
                          <div key={i} className="text-sm bg-[#111827] border border-[rgba(255,255,255,0.05)] rounded-lg p-3">
                            <p className="text-gray-300 mb-1.5">"{ev.text}"</p>
                            <p className="text-xs text-[#3B82F6] font-medium">&mdash; {ev.source}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
