/**
 * Dynamic API and Backend URL Resolver for GioTag Dashboard.
 * 
 * Works seamlessly across:
 * 1. Localhost (empty string -> Vite dev proxy forwards /api to 127.0.0.1:8000)
 * 2. Mobile LAN / Hotspot testing (e.g. 192.168.x.x / 10.x.x.x)
 * 3. Render cloud hosting (automatically detects *.onrender.com backend,
 *    or uses VITE_API_URL, or user custom backend URL stored in localStorage).
 */

export function sanitizeBackendUrl(url: string | null | undefined): string {
  if (!url) return ''
  let clean = url.trim().replace(/\/+$/, '')
  if (!clean) return ''
  // Add protocol if missing and looks like a domain or ip
  if (!clean.startsWith('http://') && !clean.startsWith('https://')) {
    if (clean.includes('localhost') || clean.startsWith('127.0.0.1') || clean.startsWith('192.168.') || clean.startsWith('10.')) {
      clean = `http://${clean}`
    } else {
      clean = `https://${clean}`
    }
  }
  // Strip common frontend route suffixes if user copied browser address bar
  clean = clean.replace(/\/(hen-comb-tracking|dashboard|devices|users|evidence|egg-counter|gis-map|ai-verification|blockchain|reports|audit-logs).*$/i, '')
  // Strip trailing API router paths so base is clean origin or root
  clean = clean.replace(/\/api\/tracker\/?$/i, '')
  clean = clean.replace(/\/api\/?$/i, '')
  return clean.replace(/\/+$/, '')
}

export function getApiBaseUrl(): string {
  // 1. Smart Cloud Auto-Resolution for Railway & Render (Host check takes priority on Railway)
  if (typeof window !== 'undefined') {
    const host = window.location.hostname
    // If running directly on Railway, use same-origin relative URLs
    if (host.includes('.up.railway.app')) {
      return ''
    }
  }

  // 2. User manual override (stored in localStorage via UI settings)
  if (typeof window !== 'undefined') {
    const custom = localStorage.getItem('giotag_backend_url') || localStorage.getItem('API_URL')
    if (custom && custom.trim()) {
      const sanitized = sanitizeBackendUrl(custom)
      // On HTTPS, do not allow stale http://localhost or insecure URLs
      if (window.location.protocol === 'https:' && sanitized.startsWith('http://')) {
        // ignore insecure override on HTTPS production
      } else {
        return sanitized
      }
    }
  }

  // 3. Vite Build-time Environment Variable (if populated during deploy)
  const envUrl = (import.meta.env.VITE_API_URL || '').trim()
  if (envUrl) {
    return sanitizeBackendUrl(envUrl)
  }

  // 4. Smart Cloud Auto-Resolution for Render & Static Hosts
  if (typeof window !== 'undefined') {
    const host = window.location.hostname
    if (host.includes('.onrender.com')) {
      if (host.includes('-frontend.')) {
        return `https://${host.replace('-frontend.', '-backend.')}`
      }
      if (host.includes('frontend.')) {
        return `https://${host.replace('frontend.', 'backend.')}`
      }
      return 'https://giotag-backend.onrender.com'
    }
    if (host.includes('.vercel.app') || host.includes('.netlify.app')) {
      return 'https://poultry-project-eggcount-production.up.railway.app'
    }
  }

  // 5. Localhost / same-origin fallback
  return ''
}

export function getTrackerBaseUrl(): string {
  const base = getApiBaseUrl()
  if (!base) {
    return '/api/tracker'
  }
  return `${base}/api/tracker`
}

export function setCustomBackendUrl(url: string | null): void {
  if (typeof window !== 'undefined') {
    const clean = sanitizeBackendUrl(url)
    if (clean) {
      localStorage.setItem('giotag_backend_url', clean)
    } else {
      localStorage.removeItem('giotag_backend_url')
    }
  }
}
