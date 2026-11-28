import React from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, Layers, CheckSquare, Image, Menu } from 'lucide-react'

interface MobileBottomNavProps {
  onOpenMenu: () => void
}

export default function MobileBottomNav({ onOpenMenu }: MobileBottomNavProps) {
  const location = useLocation()

  const navItems = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/hen-comb-tracking', label: 'Hens', icon: Layers },
    { to: '/egg-counter', label: 'Eggs', icon: CheckSquare },
    { to: '/evidence', label: 'Evidence', icon: Image },
  ]

  return (
    <nav className="mobile-bottom-nav">
      {navItems.map((item) => {
        const isActive = location.pathname === item.to
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive: navActive }) =>
              `mobile-nav-item ${navActive || isActive ? 'active' : ''}`
            }
          >
            <div className="mobile-nav-icon-wrapper">
              <item.icon size={20} />
            </div>
            <span className="mobile-nav-label">{item.label}</span>
          </NavLink>
        )
      })}

      {/* 5th item: More Menu Drawer */}
      <button
        type="button"
        onClick={onOpenMenu}
        className="mobile-nav-item mobile-nav-btn"
        aria-label="Open Navigation Menu"
      >
        <div className="mobile-nav-icon-wrapper">
          <Menu size={20} />
        </div>
        <span className="mobile-nav-label">Menu</span>
      </button>
    </nav>
  )
}
