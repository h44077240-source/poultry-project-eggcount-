import React, { useEffect, useRef, useState } from 'react'
import { Play, Pause, Sparkles } from 'lucide-react'

interface Chicken {
  id: number
  x: number
  y: number // relative to grass base (0 to 1)
  speed: number
  direction: 1 | -1 // 1: left to right, -1: right to left
  scale: number
  colorType: 'rhode_island' | 'white_leghorn' | 'golden_buff' | 'chick'
  legPhase: number
  headPhase: number
  wingPhase: number
  isPecking: boolean
  peckDuration: number
  peckTimer: number
  dustTimer: number
}

interface DustParticle {
  x: number
  y: number
  radius: number
  opacity: number
  vx: number
  vy: number
}

export default function HenFlockBackground() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [isRunning, setIsRunning] = useState(true)
  const isRunningRef = useRef(true)
  const chickensRef = useRef<Chicken[]>([])
  const dustRef = useRef<DustParticle[]>([])
  const animFrameIdRef = useRef<number | null>(null)

  useEffect(() => {
    isRunningRef.current = isRunning
  }, [isRunning])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let width = (canvas.width = canvas.parentElement?.clientWidth || window.innerWidth)
    let height = (canvas.height = canvas.parentElement?.clientHeight || 600)

    const handleResize = () => {
      if (!canvas || !canvas.parentElement) return
      width = canvas.width = canvas.parentElement.clientWidth
      height = canvas.height = Math.max(canvas.parentElement.clientHeight, 620)
    }
    window.addEventListener('resize', handleResize)

    // Initialize flock of chickens with varied sizes, speeds, and breeds
    const flockCount = Math.min(14, Math.max(8, Math.floor(width / 110)))
    const colors: Array<Chicken['colorType']> = [
      'rhode_island',
      'white_leghorn',
      'golden_buff',
      'rhode_island',
      'chick',
      'golden_buff',
      'white_leghorn',
      'chick',
    ]

    const chickens: Chicken[] = []
    for (let i = 0; i < flockCount; i++) {
      const dir: 1 | -1 = Math.random() > 0.4 ? 1 : -1
      const isChick = i % 5 === 0
      const color = isChick ? 'chick' : colors[i % colors.length]
      const scale = isChick ? 0.35 + Math.random() * 0.15 : 0.65 + Math.random() * 0.4
      chickens.push({
        id: i,
        x: Math.random() * width,
        y: 0.15 + Math.random() * 0.75, // position vertically on the grass meadow
        speed: (isChick ? 2.4 : 1.8 + Math.random() * 1.6) * (0.8 + scale * 0.4),
        direction: dir,
        scale,
        colorType: color,
        legPhase: Math.random() * Math.PI * 2,
        headPhase: Math.random() * Math.PI * 2,
        wingPhase: Math.random() * Math.PI * 2,
        isPecking: false,
        peckDuration: 0,
        peckTimer: 80 + Math.random() * 200,
        dustTimer: 0,
      })
    }
    chickensRef.current = chickens

    // Sort by y so lower chickens draw on top for natural depth
    chickens.sort((a, b) => a.y - b.y)

    // Render loop
    let lastTime = performance.now()
    const render = (currentTime: number) => {
      const dt = Math.min((currentTime - lastTime) / 1000, 0.1)
      lastTime = currentTime

      ctx.clearRect(0, 0, width, height)

      // ─── 1. Background Farm Landscape ───
      // Sky gradient (soft dawn/morning farm atmosphere)
      const skyGrad = ctx.createLinearGradient(0, 0, 0, height * 0.6)
      skyGrad.addColorStop(0, '#e0f2fe') // light sky blue
      skyGrad.addColorStop(0.5, '#fef3c7') // golden warmth
      skyGrad.addColorStop(1, '#ecfdf5') // soft pasture mist
      ctx.fillStyle = skyGrad
      ctx.fillRect(0, 0, width, height)

      // Soft sun with gentle glow
      ctx.save()
      const sunGrad = ctx.createRadialGradient(width * 0.85, height * 0.18, 10, width * 0.85, height * 0.18, 90)
      sunGrad.addColorStop(0, 'rgba(254, 240, 138, 0.85)')
      sunGrad.addColorStop(0.4, 'rgba(253, 230, 138, 0.4)')
      sunGrad.addColorStop(1, 'rgba(254, 240, 138, 0)')
      ctx.fillStyle = sunGrad
      ctx.beginPath()
      ctx.arc(width * 0.85, height * 0.18, 90, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()

      // Distant rolling green hills (Layer 1)
      ctx.save()
      ctx.fillStyle = '#bbf7d0'
      ctx.beginPath()
      ctx.moveTo(0, height * 0.42)
      ctx.bezierCurveTo(width * 0.25, height * 0.35, width * 0.45, height * 0.44, width * 0.7, height * 0.38)
      ctx.bezierCurveTo(width * 0.88, height * 0.33, width * 0.95, height * 0.37, width, height * 0.39)
      ctx.lineTo(width, height)
      ctx.lineTo(0, height)
      ctx.closePath()
      ctx.fill()
      ctx.restore()

      // Mid-distance rolling meadow (Layer 2)
      ctx.save()
      ctx.fillStyle = '#86efac'
      ctx.beginPath()
      ctx.moveTo(0, height * 0.5)
      ctx.bezierCurveTo(width * 0.2, height * 0.54, width * 0.55, height * 0.46, width * 0.8, height * 0.52)
      ctx.bezierCurveTo(width * 0.92, height * 0.55, width * 0.98, height * 0.5, width, height * 0.51)
      ctx.lineTo(width, height)
      ctx.lineTo(0, height)
      ctx.closePath()
      ctx.fill()
      ctx.restore()

      // Wooden farm fence posts along the horizon
      ctx.save()
      ctx.strokeStyle = 'rgba(161, 98, 7, 0.35)'
      ctx.lineWidth = 3
      ctx.beginPath()
      const fenceY = height * 0.52
      ctx.moveTo(0, fenceY - 6)
      ctx.lineTo(width, fenceY - 6)
      ctx.moveTo(0, fenceY + 6)
      ctx.lineTo(width, fenceY + 6)
      ctx.stroke()

      // Fence vertical posts
      ctx.fillStyle = 'rgba(161, 98, 7, 0.45)'
      const postSpacing = 90
      for (let px = 20; px < width; px += postSpacing) {
        ctx.fillRect(px, fenceY - 18, 6, 32)
      }
      ctx.restore()

      // Main active grassy pasture (Foreground where chickens run)
      const grassBaseY = height * 0.55
      const pastureHeight = height - grassBaseY

      const grassGrad = ctx.createLinearGradient(0, grassBaseY, 0, height)
      grassGrad.addColorStop(0, '#4ade80')
      grassGrad.addColorStop(0.4, '#22c55e')
      grassGrad.addColorStop(1, '#16a34a')
      ctx.fillStyle = grassGrad
      ctx.fillRect(0, grassBaseY, width, pastureHeight)

      // Decorative grass tufts along pasture
      ctx.save()
      ctx.strokeStyle = '#15803d'
      ctx.lineWidth = 2
      for (let gx = 15; gx < width; gx += 65) {
        const gy = grassBaseY + ((gx * 7) % Math.max(20, pastureHeight - 30))
        ctx.beginPath()
        ctx.moveTo(gx, gy)
        ctx.lineTo(gx - 4, gy - 10)
        ctx.moveTo(gx, gy)
        ctx.lineTo(gx + 1, gy - 12)
        ctx.moveTo(gx, gy)
        ctx.lineTo(gx + 5, gy - 9)
        ctx.stroke()
      }
      ctx.restore()

      // ─── 2. Update & Draw Dust Particles ───
      const activeDust: DustParticle[] = []
      for (const d of dustRef.current) {
        d.x += d.vx
        d.y += d.vy
        d.radius += 0.2
        d.opacity -= 0.02
        if (d.opacity > 0) {
          ctx.save()
          ctx.fillStyle = `rgba(217, 249, 157, ${Math.max(0, d.opacity * 0.6)})`
          ctx.beginPath()
          ctx.arc(d.x, d.y, d.radius, 0, Math.PI * 2)
          ctx.fill()
          ctx.restore()
          activeDust.push(d)
        }
      }
      dustRef.current = activeDust

      // ─── 3. Update & Draw Running Hens ───
      const chickens = chickensRef.current
      if (isRunningRef.current) {
        for (const hen of chickens) {
          // Check pecking state
          if (hen.isPecking) {
            hen.peckDuration -= dt
            hen.headPhase += dt * 12
            if (hen.peckDuration <= 0) {
              hen.isPecking = false
              hen.peckTimer = 120 + Math.random() * 250
            }
          } else {
            // Running forward
            hen.x += hen.speed * hen.direction
            hen.legPhase += dt * 14 * (hen.speed / 2.2)
            hen.headPhase += dt * 8
            hen.wingPhase += dt * 12

            // Spawn dust when running
            hen.dustTimer += dt * 30
            if (hen.dustTimer > 3) {
              hen.dustTimer = 0
              const hy = grassBaseY + hen.y * (pastureHeight - 40)
              dustRef.current.push({
                x: hen.x - hen.direction * 12 * hen.scale,
                y: hy + 8 * hen.scale,
                radius: 2 + Math.random() * 2,
                opacity: 0.5,
                vx: -hen.direction * (0.4 + Math.random() * 0.4),
                vy: -0.2 - Math.random() * 0.3,
              })
            }

            // Periodic pecking stop
            hen.peckTimer -= dt * 30
            if (hen.peckTimer <= 0 && Math.random() < 0.25) {
              hen.isPecking = true
              hen.peckDuration = 1.2 + Math.random() * 1.5
            }

            // Wrap around screen boundaries with margin
            const margin = 80
            if (hen.direction === 1 && hen.x > width + margin) {
              hen.x = -margin
              hen.y = 0.1 + Math.random() * 0.8
              hen.speed = 1.8 + Math.random() * 1.8
            } else if (hen.direction === -1 && hen.x < -margin) {
              hen.x = width + margin
              hen.y = 0.1 + Math.random() * 0.8
              hen.speed = 1.8 + Math.random() * 1.8
            }
          }
        }
      }

      // Draw all chickens sorted by y
      for (const hen of chickens) {
        const henY = grassBaseY + hen.y * (pastureHeight - 35)
        drawChicken(ctx, hen.x, henY, hen)
      }

      animFrameIdRef.current = requestAnimationFrame(render)
    }

    animFrameIdRef.current = requestAnimationFrame(render)

    return () => {
      window.removeEventListener('resize', handleResize)
      if (animFrameIdRef.current) cancelAnimationFrame(animFrameIdRef.current)
    }
  }, [])

  // ─── Procedural Chicken Drawing Function ───
  const drawChicken = (ctx: CanvasRenderingContext2D, x: number, y: number, hen: Chicken) => {
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(hen.scale * hen.direction, hen.scale)

    const isRunningNow = !hen.isPecking && isRunningRef.current
    const leg1Angle = isRunningNow ? Math.sin(hen.legPhase) * 0.55 : 0
    const leg2Angle = isRunningNow ? Math.sin(hen.legPhase + Math.PI) * 0.55 : 0
    const headBob = hen.isPecking
      ? Math.sin(hen.headPhase) * 12 + 10 // pecking down towards grass
      : Math.sin(hen.headPhase) * 3

    // Color definitions
    let bodyColor = '#b45309' // Rhode Island Amber/Red
    let wingColor = '#92400e'
    let combColor = '#dc2626' // Bright red comb
    let beakColor = '#f59e0b'
    let legColor = '#d97706'

    if (hen.colorType === 'white_leghorn') {
      bodyColor = '#f8fafc'
      wingColor = '#e2e8f0'
    } else if (hen.colorType === 'golden_buff') {
      bodyColor = '#f59e0b'
      wingColor = '#d97706'
    } else if (hen.colorType === 'chick') {
      bodyColor = '#fde047'
      wingColor = '#facc15'
      combColor = '#fbbf24'
    }

    // ─── Shadow on the ground ───
    ctx.save()
    ctx.fillStyle = 'rgba(0, 0, 0, 0.16)'
    ctx.beginPath()
    ctx.ellipse(0, 16, 16, 5, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()

    // ─── Back Leg ───
    ctx.save()
    ctx.translate(-4, 6)
    ctx.rotate(leg2Angle)
    ctx.strokeStyle = legColor
    ctx.lineWidth = 3
    ctx.beginPath()
    ctx.moveTo(0, 0)
    ctx.lineTo(2, 9)
    ctx.lineTo(6, 12) // little foot/toes
    ctx.stroke()
    ctx.restore()

    // ─── Tail Feathers ───
    ctx.save()
    ctx.fillStyle = wingColor
    ctx.beginPath()
    ctx.moveTo(-12, -2)
    ctx.lineTo(-24, -14)
    ctx.lineTo(-16, 2)
    ctx.closePath()
    ctx.fill()

    ctx.beginPath()
    ctx.moveTo(-10, 0)
    ctx.lineTo(-22, -8)
    ctx.lineTo(-12, 6)
    ctx.closePath()
    ctx.fill()
    ctx.restore()

    // ─── Main Body (Oval Plump Hen Body) ───
    ctx.save()
    ctx.fillStyle = bodyColor
    ctx.beginPath()
    ctx.ellipse(0, 0, 18, 14, 0.05, 0, Math.PI * 2)
    ctx.fill()

    // Subtle feather shadow/depth
    ctx.fillStyle = 'rgba(0, 0, 0, 0.06)'
    ctx.beginPath()
    ctx.arc(2, 4, 12, 0, Math.PI * 0.8)
    ctx.fill()
    ctx.restore()

    // ─── Wing (animated flapping or tucked) ───
    ctx.save()
    const wingAngle = isRunningNow ? Math.sin(hen.wingPhase) * 0.2 : 0
    ctx.translate(-2, 0)
    ctx.rotate(wingAngle)
    ctx.fillStyle = wingColor
    ctx.beginPath()
    ctx.ellipse(0, 0, 12, 8, -0.2, 0, Math.PI * 2)
    ctx.fill()
    ctx.restore()

    // ─── Front Leg ───
    ctx.save()
    ctx.translate(4, 6)
    ctx.rotate(leg1Angle)
    ctx.strokeStyle = legColor
    ctx.lineWidth = 3
    ctx.beginPath()
    ctx.moveTo(0, 0)
    ctx.lineTo(3, 9)
    ctx.lineTo(8, 12)
    ctx.stroke()
    ctx.restore()

    // ─── Neck & Head ───
    ctx.save()
    ctx.translate(14, -10 + headBob)

    // Neck base
    ctx.fillStyle = bodyColor
    ctx.beginPath()
    ctx.moveTo(-6, 8)
    ctx.lineTo(4, 8)
    ctx.lineTo(2, -6)
    ctx.lineTo(-6, -4)
    ctx.closePath()
    ctx.fill()

    // Head circle
    ctx.beginPath()
    ctx.arc(0, -6, 8, 0, Math.PI * 2)
    ctx.fill()

    // Crown / Comb on top of head
    if (hen.colorType !== 'chick') {
      ctx.fillStyle = combColor
      ctx.beginPath()
      ctx.arc(-2, -14, 3.5, 0, Math.PI * 2)
      ctx.arc(2, -15, 4, 0, Math.PI * 2)
      ctx.arc(6, -13, 3, 0, Math.PI * 2)
      ctx.fill()

      // Wattle under beak
      ctx.beginPath()
      ctx.ellipse(5, 0, 3, 4.5, 0.3, 0, Math.PI * 2)
      ctx.fill()
    }

    // Beak
    ctx.fillStyle = beakColor
    ctx.beginPath()
    ctx.moveTo(6, -6)
    ctx.lineTo(13, -4)
    ctx.lineTo(6, -2)
    ctx.closePath()
    ctx.fill()

    // Eye
    ctx.fillStyle = '#1e293b'
    ctx.beginPath()
    ctx.arc(3, -7, 1.8, 0, Math.PI * 2)
    ctx.fill()

    // Eye glint
    ctx.fillStyle = '#ffffff'
    ctx.beginPath()
    ctx.arc(3.6, -7.5, 0.6, 0, Math.PI * 2)
    ctx.fill()

    ctx.restore()

    ctx.restore()
  }

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        minHeight: '260px',
        maxHeight: '380px',
        borderRadius: 20,
        overflow: 'hidden',
        boxShadow: '0 8px 32px rgba(16, 185, 129, 0.15)',
        border: '1px solid rgba(16, 185, 129, 0.25)',
        marginBottom: 24,
      }}
    >
      <canvas
        ref={canvasRef}
        style={{
          display: 'block',
          width: '100%',
          height: '100%',
          minHeight: '260px',
          maxHeight: '380px',
        }}
      />

      {/* Modern Glassmorphic Overlay Banner with Flock Info & Controls */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          pointerEvents: 'none',
          background: 'linear-gradient(180deg, rgba(15, 23, 42, 0.25) 0%, rgba(15, 23, 42, 0.05) 40%, rgba(15, 23, 42, 0.65) 100%)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: '16px 20px',
        }}
      >
        {/* Top Header Pills */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pointerEvents: 'auto' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 14px',
              borderRadius: 30,
              background: 'rgba(15, 23, 42, 0.75)',
              backdropFilter: 'blur(10px)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              color: '#ffffff',
              fontSize: '0.85rem',
              fontWeight: 700,
              boxShadow: '0 4px 15px rgba(0, 0, 0, 0.2)',
            }}
          >
            <span style={{ fontSize: '1.1rem' }}>🐓</span>
            <span style={{ color: '#86efac' }}>AI POULTRY FLOCK ENVIRONMENT</span>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#22c55e', animation: 'live-pulse 1.2s infinite' }} />
          </div>

          <button
            type="button"
            onClick={() => setIsRunning(!isRunning)}
            title={isRunning ? 'Pause flock animation' : 'Resume flock animation'}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '6px 12px',
              borderRadius: 20,
              background: 'rgba(15, 23, 42, 0.75)',
              backdropFilter: 'blur(10px)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              color: '#f8fafc',
              fontSize: '0.78rem',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
          >
            {isRunning ? <Pause size={13} color="#86efac" /> : <Play size={13} color="#f59e0b" />}
            <span>{isRunning ? 'Flock Active' : 'Flock Paused'}</span>
          </button>
        </div>

        {/* Bottom Banner Info */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-end',
            flexWrap: 'wrap',
            gap: 12,
            pointerEvents: 'auto',
          }}
        >
          <div
            style={{
              background: 'rgba(15, 23, 42, 0.8)',
              backdropFilter: 'blur(12px)',
              padding: '12px 18px',
              borderRadius: 14,
              border: '1px solid rgba(255, 255, 255, 0.15)',
              color: '#ffffff',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', color: '#86efac', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <Sparkles size={14} color="#86efac" />
              <span>Free-Range Vision & Tracking</span>
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: 2, color: '#f8fafc' }}>
              Real-time Flock AI Tracking & Head/Comb Detection
            </div>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              background: 'rgba(15, 23, 42, 0.8)',
              backdropFilter: 'blur(12px)',
              padding: '8px 16px',
              borderRadius: 14,
              border: '1px solid rgba(255, 255, 255, 0.15)',
              color: '#cbd5e1',
              fontSize: '0.8rem',
              fontWeight: 600,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#b45309' }} />
              <span>Rhode Island</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#f8fafc' }} />
              <span>Leghorn</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#f59e0b' }} />
              <span>Golden Buff</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
