import React, { useState, useEffect } from 'react'
import { Outlet, Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import Sidebar from '../components/Sidebar'
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
          <div style={{ display:'flex', alignItems:'center', gap:12 }}>
            <button
              className="mobile-menu-btn"
              onClick={() => setIsMobileMenuOpen(true)}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--text-primary)',
                cursor: 'pointer'
              }}
            >
              <Menu size={24} />
            </button>
            <Shield size={18} color="var(--brand-400)" />
            <span className="topbar-title" style={{ fontSize:'0.8rem', color:'var(--text-muted)' }}>
              Secure Evidence Management Platform
            </span>
          </div>
          <div style={{ display:'flex', alignItems:'center', gap:16 }}>
            {/* Live AI Status Pill */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '4px 12px',
                borderRadius: 20,
                background: 'rgba(16, 185, 129, 0.12)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                color: '#059669',
                fontSize: '0.78rem',
                fontWeight: 700,
              }}
            >
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#10b981', boxShadow: '0 0 6px #10b981' }} />
              <span>AI Engine Active</span>
            </div>

            {/* Theme Toggle Pill Button */}
            <button
              type="button"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 7,
                padding: '6px 14px',
                borderRadius: 20,
                background: theme === 'dark' ? 'rgba(30, 41, 59, 0.9)' : 'rgba(241, 245, 249, 0.95)',
                border: '1px solid var(--border-default)',
                color: 'var(--text-primary)',
                fontSize: '0.82rem',
                fontWeight: 700,
                cursor: 'pointer',
                boxShadow: 'var(--shadow-sm)',
                transition: 'all 0.2s ease',
              }}
              title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} mode`}
            >
              {theme === 'dark' ? (
                <>
                  <Sun size={15} color="#f59e0b" fill="#f59e0b" />
                  <span>Light Mode</span>
                </>
              ) : (
                <>
                  <Moon size={15} color="#6366f1" fill="#6366f1" />
                  <span>Dark Mode</span>
                </>
              )}
            </button>

            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
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
      </div>
    </div>
  )
}
