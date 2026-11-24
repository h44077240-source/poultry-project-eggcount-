import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { dashboardApi } from '../services/api'
import type { DashboardStats } from '../types'
import { formatDate } from '../utils/helpers'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import {
  Image, CheckCircle, AlertTriangle, Clock, Users,
  Smartphone, Blocks, TrendingUp, Shield, CheckSquare, Camera,
  Calendar, Layers, Activity
} from 'lucide-react'

interface TrendPoint { date: string; count: number }
interface StatusDist  { status: string; count: number }
interface DailyHenSummary {
  date: string;
  formatted_date: string;
  total_hens: number;
  sessions_count: number;
  peak_visible: number;
}

const STATUS_COLORS: Record<string, string> = {
  VERIFIED: '#10b981',
  SUSPICIOUS: '#ef4444',
  REVIEW_REQUIRED: '#f59e0b',
  PENDING_SYNC: '#6366f1',
  UPLOADED: '#3b82f6',
  REJECTED: '#6b7280',
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [trend, setTrend] = useState<TrendPoint[]>([])
  const [statusDist, setStatusDist] = useState<StatusDist[]>([])
  const [dailyHens, setDailyHens] = useState<DailyHenSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      dashboardApi.stats(),
      dashboardApi.trend(30),
      dashboardApi.statusDist(),
      dashboardApi.dailyHenSummary().catch(() => ({ data: [] })),
    ]).then(([s, t, d, h]) => {
      setStats(s.data)
      setTrend(t.data)
      setStatusDist(d.data)
      setDailyHens(Array.isArray(h.data) ? h.data : [])
    }).catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="loading-screen">
      <div className="spinner" style={{ width:32, height:32 }} />
      <span>Loading dashboard...</span>
    </div>
  )

  const statCards = stats ? [
    { label:'Total Evidence', value: stats.total_evidence, icon: Image, color:'#6366f1', sub:`${stats.evidence_today} today` },
    { label:'Verified',       value: stats.verified_evidence, icon: CheckCircle, color:'#10b981', sub:`${stats.evidence_this_week} this week` },
    { label:'Suspicious',     value: stats.suspicious_evidence, icon: AlertTriangle, color:'#ef4444', sub:'Requires review' },
    { label:'Pending Sync',   value: stats.pending_sync, icon: Clock, color:'#f59e0b', sub:'Awaiting upload' },
    { label:'Active Users',   value: stats.active_users, icon: Users, color:'#8b5cf6', sub:'Registered users' },
    { label:'Devices',        value: stats.registered_devices, icon: Smartphone, color:'#06b6d4', sub:`${stats.authorized_devices} authorized` },
    { label:'Blockchain Records', value: stats.blockchain_records, icon: Blocks, color:'#ec4899', sub:'Hash registered' },
    { label:'This Week',      value: stats.evidence_this_week, icon: TrendingUp, color:'#14b8a6', sub:'Evidence captured' },
  ] : []



  return (
    <div className="page-with-bg">
      <div className="page-header">
        <div>
          <h1 className="page-title">Mission Control</h1>
          <p className="page-subtitle">Evidence monitoring dashboard — {formatDate(new Date().toISOString())}</p>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <Shield size={16} color="var(--brand-400)" />
          <span style={{ fontSize:'0.8rem', color:'var(--brand-400)', fontWeight:600 }}>System Secure</span>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="stat-grid">
        {statCards.map((card) => (
          <div key={card.label} className="stat-card" style={{ '--stat-color': card.color } as React.CSSProperties}>
            <div className="stat-icon">
              <card.icon size={20} color={card.color} />
            </div>
            <div>
              <div className="stat-value">{card.value.toLocaleString()}</div>
              <div className="stat-label">{card.label}</div>
              <div className="stat-change" style={{ color: card.color }}>{card.sub}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="charts-grid" style={{ marginTop: '24px' }}>
        {/* Evidence Trend */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Evidence Captured (30 Days)</h3>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={trend}>
              <defs>
                <linearGradient id="countGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="date" tick={{ fill:'#64748b', fontSize:11 }} tickFormatter={(v) => v.slice(5)} />
              <YAxis tick={{ fill:'#64748b', fontSize:11 }} />
              <Tooltip contentStyle={{ background:'#1a2235', border:'1px solid rgba(255,255,255,0.1)', borderRadius:8, color:'#f1f5f9', fontSize:12 }} />
              <Area type="monotone" dataKey="count" stroke="#6366f1" fill="url(#countGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Status Distribution */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Evidence Status Distribution</h3>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={statusDist} dataKey="count" nameKey="status" cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3}>
                {statusDist.map((entry) => (
                  <Cell key={entry.status} fill={STATUS_COLORS[entry.status] ?? '#6366f1'} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background:'#1a2235', border:'1px solid rgba(255,255,255,0.1)', borderRadius:8, color:'#f1f5f9', fontSize:12 }} />
              <Legend formatter={(v) => <span style={{ color:'#94a3b8', fontSize:11 }}>{v}</span>} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Quick Actions Section */}
      <div className="card" style={{ marginTop: '24px' }}>
        <div className="card-header">
          <h3 className="card-title">Quick Actions</h3>
        </div>
        <div style={{ padding: '24px', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
          <Link to="/hen-comb-tracking" style={{ textDecoration: 'none', flex: '1 1 300px' }}>
            <div style={{ 
              background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(16, 185, 129, 0.05) 100%)',
              border: '1px solid rgba(16, 185, 129, 0.2)',
              borderRadius: '12px',
              padding: '24px',
              display: 'flex',
              alignItems: 'center',
              gap: '20px',
              transition: 'all 0.2s ease',
              cursor: 'pointer'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)'
              e.currentTarget.style.boxShadow = '0 8px 24px rgba(16, 185, 129, 0.15)'
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.transform = 'translateY(0)'
              e.currentTarget.style.boxShadow = 'none'
            }}
            >
              <div style={{ 
                width: '64px', height: '64px', borderRadius: '16px', background: '#059669', 
                display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 12px rgba(16, 185, 129, 0.4)'
              }}>
                <Activity color="white" size={32} />
              </div>
              <div>
                <h3 style={{ fontSize: '1.25rem', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '4px' }}>Hen Counting AI Tracker</h3>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>Automated hen head/comb tracking and flock counting with live/video stream.</p>
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px', color: '#059669', fontWeight: '600', fontSize: '0.9rem' }}>
                <Camera size={18} /> Open Tracker
              </div>
            </div>
          </Link>

          <Link to="/egg-counter" style={{ textDecoration: 'none', flex: '1 1 300px' }}>
            <div style={{ 
              background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(99, 102, 241, 0.05) 100%)',
              border: '1px solid rgba(99, 102, 241, 0.2)',
              borderRadius: '12px',
              padding: '24px',
              display: 'flex',
              alignItems: 'center',
              gap: '20px',
              transition: 'all 0.2s ease',
              cursor: 'pointer'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)'
              e.currentTarget.style.boxShadow = '0 8px 24px rgba(99, 102, 241, 0.15)'
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.transform = 'translateY(0)'
              e.currentTarget.style.boxShadow = 'none'
            }}
            >
              <div style={{ 
                width: '64px', height: '64px', borderRadius: '16px', background: '#6366f1', 
                display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 12px rgba(99, 102, 241, 0.4)'
              }}>
                <CheckSquare color="white" size={32} />
              </div>
              <div>
                <h3 style={{ fontSize: '1.25rem', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '4px' }}>Egg Counter AI Vision</h3>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>Upload or capture photos to count and verify eggs instantly with deep learning.</p>
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px', color: '#6366f1', fontWeight: '600', fontSize: '0.9rem' }}>
                <Camera size={18} /> Open Counter
              </div>
            </div>
          </Link>
        </div>
      </div>

      {/* ─── Daily Hen Count (Date-Wise Poultry Summary) ─── */}
      <div className="card" style={{ marginTop: '24px' }}>
        <div className="card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: 'rgba(16,185,129,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Calendar size={20} color="#059669" />
            </div>
            <div>
              <h3 className="card-title" style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
                Daily Hen Count Summary (Date-Wise)
              </h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
                Total verified hens counted per calendar day across recorded flock sessions
              </p>
            </div>
          </div>
          <Link
            to="/hen-comb-tracking"
            style={{
              padding: '6px 14px',
              borderRadius: 8,
              background: '#059669',
              color: '#ffffff',
              fontSize: '0.82rem',
              fontWeight: 600,
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6
            }}
          >
            <Activity size={14} /> Open Hen Counting
          </Link>
        </div>

        {dailyHens.length === 0 ? (
          <div style={{ padding: '30px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            No hen counting sessions saved yet. Run Hen Counting to log verified flock counts.
          </div>
        ) : (
          <div style={{ padding: '20px 24px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
            {dailyHens.map((day) => {
              const isToday = day.date === new Date().toISOString().slice(0, 10);
              return (
                <div
                  key={day.date}
                  style={{
                    background: isToday ? 'linear-gradient(135deg, #ffffff 0%, #ecfdf5 100%)' : 'var(--bg-elevated)',
                    border: isToday ? '2px solid #10b981' : '1px solid rgba(0,0,0,0.08)',
                    borderRadius: 12,
                    padding: '16px',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                    position: 'relative'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                      {day.formatted_date}
                    </div>
                    {isToday && (
                      <span style={{ fontSize: '0.68rem', fontWeight: 700, background: '#10b981', color: '#ffffff', padding: '2px 7px', borderRadius: 6 }}>
                        TODAY
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 10 }}>
                    <span style={{ fontSize: '1.8rem', fontWeight: 800, color: '#059669', lineHeight: 1 }}>
                      {day.total_hens}
                    </span>
                    <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-muted)' }}>total hens</span>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 8, display: 'flex', justifyContent: 'space-between' }}>
                    <span>{day.sessions_count} {day.sessions_count === 1 ? 'session' : 'sessions'}</span>
                    <span>Peak {day.peak_visible} in frame</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Quick status overview */}
      {stats && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">System Status Overview</h3>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(180px,1fr))', gap:16 }}>
            {[
              { label:'Evidence Integrity', value:'Monitored', color:'#10b981' },
              { label:'AI Service', value:'Online', color:'#10b981' },
              { label:'Blockchain Ledger', value:'Active', color:'#10b981' },
              { label:'GPS Services', value:'Active', color:'#10b981' },
              { label:'Storage', value:'Available', color:'#10b981' },
              { label:'Authentication', value:'Secured', color:'#10b981' },
            ].map(item => (
              <div key={item.label} style={{ display:'flex', alignItems:'center', gap:8 }}>
                <div style={{ width:8, height:8, borderRadius:'50%', background:item.color, boxShadow:`0 0 6px ${item.color}80` }} />
                <div>
                  <div style={{ fontSize:'0.7rem', color:'var(--text-muted)' }}>{item.label}</div>
                  <div style={{ fontSize:'0.8rem', color:item.color, fontWeight:600 }}>{item.value}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
