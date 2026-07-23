'use client';

import React, { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { patientsApi } from '@/lib/api';
import { PatientSummary } from '@/types';
import Link from 'next/link';
import { TrendingUp, FileText, AlertTriangle, Activity, Upload, ChevronRight, Brain } from 'lucide-react';

export default function DashboardPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<PatientSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (user?.id) {
      patientsApi.getSummary(user.id)
        .then(setSummary)
        .catch(err => {
          console.error(err);
          setError('Could not load health data. Please try again.');
        })
        .finally(() => setLoading(false));
    }
  }, [user]);

  const firstName = user?.full_name?.split(' ')[0] || 'there';

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  if (loading) {
    return (
      <div className="space-y-8 animate-pulse">
        <div className="h-24 bg-white/5 rounded-2xl" />
        <div className="grid grid-cols-4 gap-6">
          {[1,2,3,4].map(i => <div key={i} className="h-32 bg-white/5 rounded-2xl" />)}
        </div>
        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2 h-64 bg-white/5 rounded-2xl" />
          <div className="h-64 bg-white/5 rounded-2xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-[fadeInUp_0.4s_ease-out]">
      {/* Welcome Banner */}
      <div className="relative overflow-hidden bg-[#111C30] border border-slate-700/50 rounded-2xl p-7">
        <div className="relative z-10 flex items-center justify-between gap-4">
          <div>
            <p className="text-[#93B4FF] text-xs font-semibold uppercase tracking-wider mb-1">{greeting}</p>
            <h1 className="text-2xl font-bold text-white mb-1.5">{firstName}'s Health Dashboard</h1>
            <p className="text-slate-400 text-sm max-w-lg">Your longitudinal medical intelligence is up to date. Here's what the AI pipeline has found.</p>
          </div>
          <Link
            href="/upload"
            className="shrink-0 flex items-center gap-2 bg-[#4F7CFF] hover:bg-[#3B6EF0] text-white px-5 py-2.5 rounded-xl font-semibold shadow-lg shadow-[#4F7CFF]/20 transition-all hover:-translate-y-0.5 text-sm"
          >
            <Upload className="w-4 h-4" />
            Upload Document
          </Link>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-6">
        <StatCard
          title="Active Medications"
          value={summary?.active_medications ?? '—'}
          icon={Activity}
          color="#10B981"
          glow="rgba(16,185,129,0.15)"
          trend="+0 this month"
        />
        <StatCard
          title="Tracked Metrics"
          value={summary?.tracked_metrics ?? '—'}
          icon={TrendingUp}
          color="#3B82F6"
          glow="rgba(59,130,246,0.15)"
          trend="Across all documents"
        />
        <StatCard
          title="Documents Processed"
          value={summary?.document_count ?? '—'}
          icon={FileText}
          color="#8B5CF6"
          glow="rgba(139,92,246,0.15)"
          trend="All analyzed by AI"
        />
        <StatCard
          title="Pending Reviews"
          value={summary?.pending_reviews ?? '—'}
          icon={AlertTriangle}
          color="#F59E0B"
          glow="rgba(245,158,11,0.15)"
          trend="Awaiting clinician"
          urgent={Number(summary?.pending_reviews) > 0}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left: Main content (2/3) */}
        <div className="lg:col-span-2 space-y-6">

          {/* Error state */}
          {error && (
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm">
              {error}
            </div>
          )}
          
          {/* Recent Insights */}
          <section className="bg-[#111C30] border border-slate-700/40 rounded-2xl overflow-hidden">
            <div className="p-6 border-b border-slate-700/40 flex items-center justify-between">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Brain className="w-5 h-5 text-amber-400" />
                AI Insights
              </h2>
              <Link href="/insights" className="text-xs text-gray-400 hover:text-white flex items-center gap-1 transition-colors">
                View all <ChevronRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="p-6 space-y-4">
              {summary?.recent_insights && summary.recent_insights.length > 0 ? (
                summary.recent_insights.map((insight: any, i: number) => (
                  <div key={i} className="group p-5 rounded-xl bg-white/2 border border-white/5 hover:border-blue-500/25 hover:bg-blue-500/5 transition-all cursor-default">
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                          insight.severity === 'high' || insight.severity === 'critical' 
                            ? 'bg-red-400 animate-pulse' 
                            : insight.severity === 'moderate' ? 'bg-amber-400' : 'bg-blue-400'
                        }`} />
                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${
                          insight.severity === 'high' || insight.severity === 'critical'
                            ? 'bg-red-500/10 border-red-500/20 text-red-400'
                            : insight.severity === 'moderate' ? 'bg-amber-500/10 border-amber-500/20 text-amber-400'
                            : 'bg-blue-500/10 border-blue-500/20 text-blue-400'
                        } uppercase tracking-wider`}>
                          {insight.severity || insight.insight_type || 'Insight'}
                        </span>
                      </div>
                      <span className="text-xs text-gray-600">{new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                    </div>
                    <p className="text-white text-sm leading-relaxed mb-3">{insight.patient_facing_text}</p>
                    <Link href="/insights" className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors">
                      View evidence <ChevronRight className="w-3 h-3" />
                    </Link>
                  </div>
                ))
              ) : (
                <div className="text-center py-12">
                  <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mx-auto mb-4">
                    <Brain className="w-8 h-8 text-gray-600" />
                  </div>
                  <p className="text-gray-500 font-medium mb-1">No insights generated yet</p>
                  <p className="text-gray-600 text-sm">Upload a document to start the AI pipeline</p>
                  <Link href="/upload" className="inline-flex items-center gap-2 mt-4 text-sm text-blue-400 hover:text-blue-300 transition-colors">
                    <Upload className="w-4 h-4" /> Upload your first document
                  </Link>
                </div>
              )}
            </div>
          </section>

          {/* Trend Highlights */}
          <section className="bg-[#111C30] border border-slate-700/40 rounded-2xl overflow-hidden">
            <div className="p-6 border-b border-slate-700/40 flex items-center justify-between">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-emerald-400" />
                Longitudinal Trends
              </h2>
              <Link href="/timeline" className="text-xs text-gray-400 hover:text-white flex items-center gap-1 transition-colors">
                Full timeline <ChevronRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="p-6">
              {summary?.top_trends && summary.top_trends.length > 0 ? (
                <div className="space-y-4">
                  {summary.top_trends.slice(0, 3).map((trend: any, i: number) => (
                    <div key={i} className="flex items-center justify-between p-4 rounded-xl bg-white/2 border border-white/5">
                      <div>
                        <p className="font-medium text-white text-sm">{trend.metric_display || trend.metric_name}</p>
                        <p className="text-xs text-gray-500 mt-0.5">{trend.data_point_count} data points</p>
                      </div>
                      <span className={`text-sm font-bold ${
                        trend.direction === 'improving' ? 'text-emerald-400' :
                        trend.direction === 'worsening' ? 'text-red-400' : 'text-gray-400'
                      }`}>
                        {trend.direction === 'improving' ? '↑ Improving' :
                         trend.direction === 'worsening' ? '↓ Worsening' : '→ Stable'}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-10 border-2 border-dashed border-white/8 rounded-xl">
                  <TrendingUp className="w-10 h-10 text-gray-600 mx-auto mb-3" />
                  <p className="text-gray-500 text-sm">Trend charts will appear after documents are uploaded</p>
                  <p className="text-gray-600 text-xs mt-1">Powered by Recharts · Real-time updates</p>
                </div>
              )}
            </div>
          </section>
        </div>

        {/* Right column (1/3) */}
        <div className="space-y-6">
          
          {/* Pipeline status */}
          <section className="bg-[#111C30] border border-slate-700/40 rounded-2xl p-5">
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-5">Pipeline Status</h2>
            <div className="relative w-36 h-36 mx-auto mb-6">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" stroke="rgba(255,255,255,0.06)" strokeWidth="10" fill="none" />
                <circle 
                  cx="60" cy="60" r="50" 
                  stroke="url(#pipelineGrad)" 
                  strokeWidth="10" fill="none" 
                  strokeDasharray="314" 
                  strokeDashoffset="47" 
                  strokeLinecap="round"
                  className="transition-all duration-1000"
                />
                <defs>
                  <linearGradient id="pipelineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#3B82F6" />
                    <stop offset="100%" stopColor="#10B981" />
                  </linearGradient>
                </defs>
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-2xl font-black text-white">85%</span>
                <span className="text-xs text-gray-500">Pipeline Health</span>
              </div>
            </div>
            <div className="space-y-2">
              {[
                { name: 'OCR Agent', status: 'operational', color: '#10B981' },
                { name: 'NER Agent', status: 'operational', color: '#10B981' },
                { name: 'Reasoning Agent', status: 'operational', color: '#10B981' },
                { name: 'Verification Agent', status: 'operational', color: '#10B981' },
              ].map(agent => (
                <div key={agent.name} className="flex items-center justify-between text-sm">
                  <span className="text-gray-400">{agent.name}</span>
                  <span className="flex items-center gap-1.5 text-xs font-medium" style={{ color: agent.color }}>
                    <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: agent.color }} />
                    {agent.status}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* Recent Documents */}
          <section className="bg-[#111C30] border border-slate-700/40 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Recent Documents</h2>
              <Link href="/upload" className="text-xs text-blue-400 hover:text-blue-300 transition-colors">Upload +</Link>
            </div>
            <div className="space-y-3">
              {(summary?.recent_documents && summary.recent_documents.length > 0) ? (
                summary.recent_documents.slice(0, 3).map((doc: any, i: number) => (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-xl bg-white/2 border border-white/5">
                    <div className="w-9 h-9 rounded-lg bg-red-500/15 border border-red-500/20 flex items-center justify-center shrink-0">
                      <FileText className="w-4 h-4 text-red-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-200 truncate">{doc.filename}</p>
                      <p className="text-xs text-gray-500">{doc.status}</p>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-6">
                  <FileText className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                  <p className="text-gray-600 text-xs">No documents yet</p>
                </div>
              )}
            </div>
          </section>

          {/* Quick Actions */}
          <section className="bg-[#111C30] border border-slate-700/40 rounded-2xl p-5">
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Quick Actions</h2>
            <div className="space-y-2">
              {[
                { href: '/upload', label: 'Upload Document', icon: Upload, color: '#3B82F6' },
                { href: '/timeline', label: 'View Timeline', icon: Activity, color: '#10B981' },
                { href: '/insights', label: 'See Insights', icon: Brain, color: '#8B5CF6' },
              ].map(action => (
                <Link key={action.href} href={action.href} className="flex items-center gap-3 p-3 rounded-xl hover:bg-white/4 border border-transparent hover:border-white/6 transition-all group">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${action.color}20`, border: `1px solid ${action.color}30` }}>
                    <action.icon className="w-4 h-4" style={{ color: action.color }} />
                  </div>
                  <span className="text-sm text-gray-300 group-hover:text-white transition-colors font-medium">{action.label}</span>
                  <ChevronRight className="w-4 h-4 text-gray-600 group-hover:text-gray-400 ml-auto transition-colors" />
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function StatCard({ title, value, icon: Icon, color, glow, trend, urgent }: {
  title: string; value: any; icon: any; color: string; glow: string; trend?: string; urgent?: boolean;
}) {
  return (
    <div className={`relative bg-[#0D1526] border rounded-2xl p-6 overflow-hidden group hover:-translate-y-1 transition-all duration-200 ${urgent ? 'border-amber-500/30 animate-[pulseGlow_2s_ease-in-out_infinite]' : 'border-white/6 hover:border-white/10'}`}>
      <div className="absolute -right-4 -top-4 w-24 h-24 rounded-full blur-2xl opacity-0 group-hover:opacity-100 transition-opacity" style={{ backgroundColor: color }} />
      <div className="relative z-10">
        <div className="flex items-start justify-between mb-4">
          <p className="text-sm font-medium text-gray-400">{title}</p>
          <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ backgroundColor: `${color}20`, border: `1px solid ${color}30` }}>
            <Icon className="w-5 h-5" style={{ color }} />
          </div>
        </div>
        <p className="text-4xl font-black text-white mb-1">{value}</p>
        {trend && <p className="text-xs text-gray-600">{trend}</p>}
      </div>
    </div>
  );
}
