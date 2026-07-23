'use client';

import Link from 'next/link';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0C1222] text-white">
      {/* Subtle background gradient — no blobs */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0C1222] via-[#0F1A30] to-[#0C1222]" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(148,163,184,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(148,163,184,0.03)_1px,transparent_1px)] bg-[size:48px_48px]" />
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-[#4F7CFF] rounded-full blur-[160px] opacity-[0.06]" />
      </div>

      {/* Navbar */}
      <nav className="relative z-20 border-b border-slate-700/40 bg-[#0C1222]/80 backdrop-blur-md sticky top-0">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#4F7CFF] flex items-center justify-center font-bold text-sm shadow-lg">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <span className="font-bold text-white tracking-tight">HealthBuddy</span>
            <span className="text-[10px] font-semibold uppercase tracking-widest text-[#4F7CFF] bg-[#4F7CFF]/10 border border-[#4F7CFF]/20 px-2 py-0.5 rounded-full">Beta</span>
          </div>
          <div className="hidden md:flex items-center gap-7 text-sm text-slate-400">
            <a href="#features" className="hover:text-white transition-colors">Features</a>
            <a href="#pipeline" className="hover:text-white transition-colors">AI Pipeline</a>
            <a href="#about" className="hover:text-white transition-colors">About</a>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm text-slate-300 hover:text-white font-medium px-4 py-2 rounded-lg hover:bg-slate-700/40 transition-all">
              Sign In
            </Link>
            <Link href="/register" className="text-sm font-semibold bg-[#4F7CFF] hover:bg-[#3B6EF0] text-white px-5 py-2 rounded-lg transition-all shadow-lg shadow-[#4F7CFF]/20">
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <main className="relative z-10 max-w-6xl mx-auto px-6 pt-20 pb-16">
        <div className="text-center max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 bg-[#4F7CFF]/10 border border-[#4F7CFF]/20 rounded-full px-4 py-1.5 text-xs font-medium text-[#93B4FF] mb-8 uppercase tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Multi-Agent AI · 9 Specialized Agents · Evidence-Grounded
          </div>

          <h1 className="text-5xl md:text-6xl font-bold tracking-tight mb-4 leading-tight text-white">
            Health<span className="text-[#4F7CFF]">Buddy</span>
          </h1>
          <p className="text-base md:text-lg font-semibold text-[#93B4FF] mb-6 tracking-tight">
            AI-Powered Longitudinal Health Intelligence Platform
          </p>

          <p className="text-lg text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            Transform fragmented medical reports into meaningful clinical insights using our multi-agent AI pipeline — extracting, normalizing, and reasoning across your complete health history.
          </p>

          <div className="flex flex-col sm:flex-row justify-center gap-3 mb-16">
            <Link href="/upload" className="bg-[#4F7CFF] hover:bg-[#3B6EF0] text-white px-8 py-3.5 rounded-lg font-semibold text-sm shadow-lg shadow-[#4F7CFF]/25 transition-all hover:-translate-y-0.5">
              Upload Medical Reports →
            </Link>
            <Link href="/dashboard" className="bg-slate-700/40 hover:bg-slate-700/70 border border-slate-600/50 text-slate-200 px-8 py-3.5 rounded-lg font-semibold text-sm transition-all hover:-translate-y-0.5">
              View Dashboard
            </Link>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-3xl mx-auto">
            {[
              { value: '9', label: 'AI Agents' },
              { value: '<60s', label: 'Per Document' },
              { value: '100%', label: 'Evidence-Grounded' },
              { value: 'HIPAA', label: 'Compliant Design' },
            ].map(s => (
              <div key={s.label} className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-4 text-center">
                <div className="text-2xl font-bold text-white mb-0.5">{s.value}</div>
                <div className="text-xs text-slate-500 font-medium">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </main>

      {/* Features */}
      <section id="features" className="relative z-10 max-w-6xl mx-auto px-6 py-20">
        <div className="text-center mb-14">
          <h2 className="text-3xl font-bold text-white mb-3">Built for Clinical Intelligence</h2>
          <p className="text-slate-400 max-w-xl mx-auto">From fragmented documents to a unified, intelligent health record.</p>
        </div>
        <div className="grid md:grid-cols-3 gap-5">
          {[
            { icon: '🤖', title: '9 Specialized AI Agents', desc: 'A dedicated pipeline of nine agents handles OCR, entity recognition, normalization, and reasoning end to end.' },
            { icon: '📈', title: 'Longitudinal Health Analysis', desc: 'Tracks lab values across years and providers, normalizing units automatically to reveal your health trajectory.' },
            { icon: '💡', title: 'AI Clinical Insights', desc: 'Synthesizes evidence across your full history into clear, actionable insights — not just isolated data points.' },
            { icon: '🔐', title: 'Privacy Protection', desc: 'All protected health information is encrypted at rest, tokenized, and access-controlled at every endpoint.' },
            { icon: '✅', title: 'Evidence Grounded Medical Intelligence', desc: 'Every insight is independently verified by a second AI agent and links back to its exact source evidence.' },
            { icon: '👨‍⚕️', title: 'Clinician Portal', desc: 'Clinicians get a review queue to approve, modify, or override AI-generated insights before patient delivery.' },
          ].map(f => (
            <div key={f.title} className="bg-slate-800/30 border border-slate-700/40 rounded-2xl p-6 hover:border-[#4F7CFF]/30 hover:bg-slate-800/50 transition-all duration-200 group">
              <div className="w-11 h-11 bg-slate-700/60 rounded-xl flex items-center justify-center text-2xl mb-5 group-hover:bg-[#4F7CFF]/10 transition-colors">
                {f.icon}
              </div>
              <h3 className="font-semibold text-white mb-2">{f.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pipeline */}
      <section id="pipeline" className="relative z-10 max-w-6xl mx-auto px-6 py-20">
        <div className="text-center mb-14">
          <h2 className="text-3xl font-bold text-white mb-3">Multi-Agent Processing Pipeline</h2>
          <p className="text-slate-400 max-w-xl mx-auto">Each agent specializes in one task and passes structured, validated data to the next.</p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[
            { n: '01', name: 'Medical Report Upload', desc: 'Document type detection & quality routing' },
            { n: '02', name: 'OCR Processing', desc: 'Text extraction with bounding-box precision' },
            { n: '03', name: 'PHI Tokenization', desc: 'Protected health info redacted & tokenized' },
            { n: '04', name: 'Medical Entity Recognition', desc: 'Labs, meds, diagnoses, procedures, vitals' },
            { n: '05', name: 'Normalization', desc: 'SNOMED-CT, LOINC, RxNorm mapping' },
            { n: '06', name: 'Trend Analysis', desc: 'Longitudinal trends & anomaly detection' },
            { n: '07', name: 'Knowledge Retrieval', desc: 'Clinical guidelines & evidence lookup' },
            { n: '08', name: 'Clinical Reasoning', desc: 'Synthesizes evidence into patient insights' },
            { n: '09', name: 'Verification', desc: 'Independent critique of every insight' },
            { n: '10', name: 'Personalized Health Insights', desc: 'Delivered to your dashboard, evidence-linked' },
          ].map(step => (
            <div key={step.n} className="flex gap-4 bg-slate-800/30 border border-slate-700/40 rounded-xl p-4 hover:border-slate-600/60 transition-colors">
              <span className="text-[#4F7CFF] font-bold text-sm font-mono mt-0.5 shrink-0 w-8">{step.n}</span>
              <div>
                <div className="font-semibold text-sm text-white mb-0.5">{step.name}</div>
                <div className="text-xs text-slate-500">{step.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section id="about" className="relative z-10 max-w-3xl mx-auto px-6 py-20">
        <div className="bg-slate-800/40 border border-slate-700/50 rounded-2xl p-12 text-center">
          <h2 className="text-3xl font-bold text-white mb-4">Ready to get started?</h2>
          <p className="text-slate-400 mb-8">Create a free account and upload your first medical document in under 2 minutes.</p>
          <Link href="/register" className="inline-block bg-[#4F7CFF] hover:bg-[#3B6EF0] text-white px-10 py-3.5 rounded-lg font-semibold shadow-lg shadow-[#4F7CFF]/25 transition-all hover:-translate-y-0.5">
            Create Account
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-slate-700/40 py-8 text-center text-slate-600 text-sm">
        © 2025 HealthBuddy · AI-Powered Longitudinal Health Intelligence Platform · Built for clinical excellence
      </footer>
    </div>
  );
}
