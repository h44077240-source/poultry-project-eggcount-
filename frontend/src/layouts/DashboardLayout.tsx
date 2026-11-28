import React, { useState, useEffect } from 'react'
import { Outlet, Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import Sidebar from '../components/Sidebar'
import MobileBottomNav from '../components/MobileBottomNav'
import { Shield, Sun, Moon, Menu } from 'lucide-react'

export default function DashboardLayout() {
  const { isAuthenticated, loading } = useAuth()
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('theme') || 'dark'
  })
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  useEffect(() => {
    if (theme === 'light') {
      document.documentElement.classList.add('light')
    } else {
      document.documentElement.classList.remove('light')
    }
    localStorage.setItem('theme', theme)
  }, [theme])

  if (loading) return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center', minHeight:'100vh', gap:12 }}>
      <div className="spinner" />
      <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Loading GioTag...</span>
    </div>
  )

  if (!isAuthenticated) return <Navigate to="/login" replace />

  return (
    <div className="layout">
      <Sidebar isOpen={isMobileMenuOpen} onClose={() => setIsMobileMenuOpen(false)} />
      <div className="main-content">
        <header className="topbar">
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <button
              className="mobile-menu-btn"
              onClick={() => setIsMobileMenuOpen(true)}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--text-primary)',
                cursor: 'pointer',
                padding: 4,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
              aria-label="Open Menu"
            >
              <Menu size={22} />
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <Shield size={18} color="var(--brand-400)" />
              <span className="brand-mobile-title" style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                KR Poultry
              </span>
            </div>
            <span className="topbar-title desktop-only" style={{ fontSize:'0.8rem', color:'var(--text-muted)' }}>
              Secure Evidence Management Platform
            </span>
          </div>
          <div style={{ display:'flex', alignItems:'center', gap: 10 }}>
            {/* Live AI Status Pill */}
            <div
              className="ai-status-pill"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '4px 10px',
                borderRadius: 20,
                background: 'rgba(16, 185, 129, 0.12)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                color: '#059669',
                fontSize: '0.75rem',
                fontWeight: 700,
              }}
            >
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#10b981', boxShadow: '0 0 6px #10b981' }} />
              <span className="ai-status-text">AI Active</span>
            </div>

            {/* Theme Toggle */}
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 32,
                height: 32,
                borderRadius: '50%',
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-primary)',
                cursor: 'pointer',
                transition: 'all var(--transition)'
              }}
              title="Toggle Light/Dark Theme"
            >
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
            </button>

            <div className="desktop-only" style={{ display:'flex', alignItems:'center', gap:8 }}>
              <div style={{
                width:8, height:8, borderRadius:'50%',
                background:'#10b981',
                boxShadow:'0 0 6px rgba(16,185,129,0.6)'
              }} />
              <span style={{ fontSize:'0.75rem', color:'var(--text-muted)' }}>System Online</span>
            </div>
          </div>
        </header>
        <div className="page-content fade-in">
          <Outlet />
        </div>
        <MobileBottomNav onOpenMenu={() => setIsMobileMenuOpen(true)} />
      </div>
    </div>
  )
}
