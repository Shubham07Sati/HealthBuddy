'use client';

import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { patientsApi } from '@/lib/api';
import { TimelineResponse } from '@/types';
import { Search, Filter, Calendar, Activity, Database, Stethoscope, ChevronRight, FileText } from 'lucide-react';

export default function TimelinePage() {
  const { user } = useAuth();
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // Mock data removed in favor of real API call

  useEffect(() => {
    if (user?.id) {
      patientsApi.getTimeline(user.id)
        .then(setData)
        .catch(console.error)
        .finally(() => setLoading(false));
    }
  }, [user]);

  const getTypeIcon = (type: string) => {
    switch(type) {
      case 'lab_value': return <Activity className="w-5 h-5 text-blue-400" />;
      case 'medication': return <Database className="w-5 h-5 text-emerald-400" />;
      case 'diagnosis': return <Stethoscope className="w-5 h-5 text-purple-400" />;
      default: return <Activity className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    if (status === 'low') return 'text-amber-400';
    if (status === 'high') return 'text-red-400';
    return 'text-white';
  };

  return (
    <div className="space-y-8 animate-[fadeIn_0.3s_ease-out]">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Patient Timeline</h1>
          <p className="text-gray-400">A chronological record of every extracted clinical entity.</p>
        </div>
        
        <div className="flex items-center space-x-3">
          <button className="bg-[rgba(255,255,255,0.05)] border border-[rgba(255,255,255,0.1)] hover:bg-[rgba(255,255,255,0.1)] text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center">
            <Filter className="w-4 h-4 mr-2" /> Filter
          </button>
          <div className="relative">
            <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input 
              type="text" 
              placeholder="Search entities..." 
              className="bg-[rgba(0,0,0,0.2)] border border-[rgba(255,255,255,0.1)] rounded-lg pl-9 pr-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-[#3B82F6]"
            />
          </div>
        </div>
      </div>

      <div className="bg-[#111827] border border-[rgba(255,255,255,0.05)] rounded-2xl p-8 shadow-lg min-h-[500px]">
        
        {/* Timeline visualization */}
        <div className="relative border-l-2 border-[rgba(255,255,255,0.1)] ml-4 md:ml-6 space-y-12">
          
          {(data?.items || []).map((group: any, groupIdx: number) => (
            <div key={groupIdx} className="relative">
              {/* Month Header */}
              <div className="flex items-center mb-6 -ml-4">
                <div className="w-8 h-8 rounded-full bg-[#1F2937] border-2 border-[#3B82F6] flex items-center justify-center shrink-0 z-10 shadow-[0_0_10px_rgba(59,130,246,0.3)]">
                  <Calendar className="w-4 h-4 text-[#3B82F6]" />
                </div>
                <h3 className="text-lg font-bold text-white ml-4 tracking-wide">{group.month}</h3>
              </div>
              
              <div className="space-y-6">
                {group.events.map((event, i) => (
                  <div key={event.id} className="relative ml-8 group cursor-pointer">
                    {/* Line connector to item */}
                    <div className="absolute top-6 -left-8 w-8 h-px bg-[rgba(255,255,255,0.1)]"></div>
                    {/* Item dot */}
                    <div className="absolute top-5 -left-10 w-4 h-4 rounded-full bg-[#1F2937] border-2 border-[rgba(255,255,255,0.2)] group-hover:border-white transition-colors z-10"></div>
                    
                    {/* Card */}
                    <div className="bg-[rgba(255,255,255,0.02)] border border-[rgba(255,255,255,0.05)] hover:border-[rgba(255,255,255,0.2)] rounded-xl p-5 backdrop-blur-sm transition-all group-hover:bg-[rgba(255,255,255,0.03)] shadow-md">
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        
                        <div className="flex items-center space-x-4">
                          <div className="p-3 bg-[rgba(0,0,0,0.2)] rounded-lg">
                            {getTypeIcon(event.type)}
                          </div>
                          <div>
                            <div className="flex items-center space-x-2">
                              <span className="text-xs font-medium text-gray-500 px-2 py-0.5 rounded-full bg-[rgba(255,255,255,0.05)] uppercase tracking-wider">{event.type.replace('_', ' ')}</span>
                              <span className="text-sm text-gray-400">{event.date}</span>
                            </div>
                            <h4 className="text-xl font-semibold text-white mt-1">{event.label}</h4>
                          </div>
                        </div>
                        
                        <div className="flex items-center md:flex-col md:items-end space-x-4 md:space-x-0 md:space-y-2">
                          <div className="text-2xl font-bold bg-[rgba(0,0,0,0.2)] px-4 py-1.5 rounded-lg border border-[rgba(255,255,255,0.05)]">
                            <span className={getStatusColor(event.status)}>{event.value}</span>
                            <span className="text-sm text-gray-500 ml-2">{event.unit}</span>
                          </div>
                          <div className="hidden md:flex items-center text-xs text-gray-500 group-hover:text-[#3B82F6] transition-colors">
                            <FileText className="w-3.5 h-3.5 mr-1" />
                            {event.doc}
                          </div>
                        </div>

                      </div>
                      
                      {/* Confidence bar */}
                      <div className="mt-4 pt-4 border-t border-[rgba(255,255,255,0.05)] flex items-center justify-between">
                        <div className="flex items-center space-x-3 flex-1 max-w-sm">
                          <span className="text-xs text-gray-500">Confidence</span>
                          <div className="h-1.5 flex-1 bg-[rgba(255,255,255,0.1)] rounded-full overflow-hidden">
                            <div 
                              className={`h-full rounded-full ${event.confidence > 0.9 ? 'bg-emerald-400' : 'bg-amber-400'}`}
                              style={{ width: `${event.confidence * 100}%` }}
                            />
                          </div>
                          <span className="text-xs font-medium text-gray-400">{Math.round(event.confidence * 100)}%</span>
                        </div>
                        <ChevronRight className="w-5 h-5 text-gray-600 group-hover:text-white transition-colors" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* End cap */}
          <div className="relative -ml-2.5">
            <div className="w-5 h-5 rounded-full border-4 border-[#111827] bg-[rgba(255,255,255,0.1)]"></div>
          </div>

        </div>
      </div>
    </div>
  );
}
