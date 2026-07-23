'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { 
  LayoutDashboard, Upload, Clock, Lightbulb, CheckSquare, Shield, Activity, 
  User, LogOut, ChevronRight, Bell, Menu, X
} from 'lucide-react';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, role, logout } = useAuth();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [loggingOut, setLoggingOut] = useState(false);

  const navItems = [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard, roles: ['patient', 'clinician', 'admin'], color: '#3B82F6' },
    { name: 'Upload', href: '/upload', icon: Upload, roles: ['patient', 'clinician', 'admin'], color: '#10B981' },
    { name: 'Timeline', href: '/timeline', icon: Clock, roles: ['patient', 'clinician', 'admin'], color: '#8B5CF6' },
    { name: 'Insights', href: '/insights', icon: Lightbulb, roles: ['patient', 'clinician', 'admin'], color: '#F59E0B' },
    { name: 'Corrections', href: '/corrections', icon: CheckSquare, roles: ['clinician', 'admin'], color: '#06B6D4' },
    { name: 'Clinician', href: '/clinician', icon: Activity, roles: ['clinician', 'admin'], color: '#EC4899' },
    { name: 'Audit Log', href: '/audit', icon: Shield, roles: ['admin'], color: '#EF4444' },
  ];

  const filteredItems = navItems.filter(i => !role || i.roles.includes(role));

  const handleLogout = async () => {
    setLoggingOut(true);
    await logout();
    router.push('/login');
  };

  const pageTitle = pathname.split('/').filter(Boolean).map(s => 
    s.charAt(0).toUpperCase() + s.slice(1)
  ).join(' › ') || 'Dashboard';

  const initials = user?.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : 'U';

  return (
    <div className="flex h-screen bg-[#050A18] text-white overflow-hidden">
      
      {/* Mobile sidebar backdrop */}
      {!sidebarOpen && (
        <div className="fixed inset-0 bg-black/60 z-20 lg:hidden" onClick={() => setSidebarOpen(true)} />
      )}

      {/* Sidebar */}
      <aside className={`${sidebarOpen ? 'w-60' : 'w-0 lg:w-16'} flex-shrink-0 bg-[#111C30] border-r border-slate-700/40 flex flex-col transition-all duration-300 overflow-hidden z-30`}>
        {/* Logo */}
        <div className="h-16 flex items-center px-5 border-b border-slate-700/40 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-[#4F7CFF] flex items-center justify-center font-black text-base shadow-[0_0_15px_rgba(79,124,255,0.3)] shrink-0">
            H
          </div>
          {sidebarOpen && (
            <div className="ml-3 overflow-hidden">
              <span className="font-black text-lg whitespace-nowrap">HealthBuddy</span>
              <span className="block text-[9px] text-blue-400 font-semibold uppercase tracking-widest whitespace-nowrap -mt-0.5">Health Intelligence</span>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-0.5">
          {sidebarOpen && (
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-600 px-3 py-2">Navigation</p>
          )}
          {filteredItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                href={item.href}
                title={!sidebarOpen ? item.name : undefined}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 group ${
                  isActive 
                    ? 'text-white' 
                    : 'text-gray-500 hover:text-gray-200 hover:bg-white/4'
                }`}
                style={isActive ? {
                  background: `linear-gradient(135deg, ${item.color}20, ${item.color}10)`,
                  border: `1px solid ${item.color}30`,
                  color: item.color
                } : {}}
              >
                <Icon 
                  className="w-4 h-4 shrink-0" 
                  style={isActive ? { color: item.color } : {}}
                />
                {sidebarOpen && (
                  <>
                    <span className="flex-1 whitespace-nowrap">{item.name}</span>
                    {isActive && <ChevronRight className="w-3 h-3" style={{ color: item.color }} />}
                  </>
                )}
              </Link>
            );
          })}
        </nav>

        {/* User footer */}
        <div className="p-3 border-t border-white/5 shrink-0">
          <div className={`flex items-center gap-3 p-2 rounded-xl hover:bg-white/4 transition-colors ${sidebarOpen ? '' : 'justify-center'}`}>
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center text-xs font-bold shrink-0">
              {initials}
            </div>
            {sidebarOpen && (
              <>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-white truncate">{user?.full_name || 'User'}</p>
                  <p className="text-[10px] text-gray-500 truncate capitalize">{role || 'patient'}</p>
                </div>
                <button 
                  onClick={handleLogout}
                  disabled={loggingOut}
                  className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
                  title="Sign out"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </>
            )}
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Top Header */}
        <header className="h-16 bg-[#111C30]/80 backdrop-blur-md border-b border-slate-700/40 flex items-center justify-between px-6 z-10 shrink-0">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setSidebarOpen(v => !v)}
              className="p-2 text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
            >
              {sidebarOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </button>
            <div>
              <h2 className="text-sm font-semibold text-white">{pageTitle}</h2>
              <p className="text-[11px] text-gray-600">HealthBuddy Health Intelligence Platform</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative">
              <button className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-white/5 transition-colors">
                <Bell className="w-5 h-5" />
              </button>
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
            </div>
            <div className="flex items-center gap-2 pl-3 border-l border-white/8">
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center text-[10px] font-bold">
                {initials}
              </div>
              <div className="hidden sm:block">
                <p className="text-xs font-medium text-white leading-none">{user?.full_name?.split(' ')[0]}</p>
                <p className="text-[10px] text-gray-500 capitalize">{role}</p>
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <div className="flex-1 overflow-auto">
          <div className="p-6 lg:p-8 max-w-[1400px] mx-auto">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
