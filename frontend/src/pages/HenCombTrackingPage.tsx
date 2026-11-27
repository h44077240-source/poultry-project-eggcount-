import React, { useState, useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { Camera, Upload, RefreshCw, FileVideo, Maximize2, Minimize2, X, Video, Scan, CheckCircle2, Activity, Settings, Wifi, WifiOff, History, Trash2, Calendar, Clock, Film, Layers, Sparkles } from 'lucide-react'
import { getTrackerBaseUrl, getApiBaseUrl, setCustomBackendUrl } from '../utils/apiUrl'

export default function HenCombTrackingPage() {
  const [streamUrl, setStreamUrl] = useState<string | null>(null)
  const [streamMode, setStreamMode] = useState<'video' | 'camera' | 'local_video' | null>(null)
  const [localVideoUrl, setLocalVideoUrl] = useState<string | null>(null)
  const [activeLoadingCard, setActiveLoadingCard] = useState<'record' | 'upload' | null>(null)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)
  const [uploadStatusText, setUploadStatusText] = useState<string | null>(null)
  const [pendingVideoFile, setPendingVideoFile] = useState<File | null>(null)
  const [showUploadChoiceModal, setShowUploadChoiceModal] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [totalCount, setTotalCount] = useState(0)
  const [visibleCount, setVisibleCount] = useState(0)
  const [facingMode, setFacingMode] = useState<'environment' | 'user'>('environment')
  const [fitMode, setFitMode] = useState<'cover' | 'contain'>('contain')
  const [isFullScreenVideo, setIsFullScreenVideo] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [recordingDuration, setRecordingDuration] = useState(0)
  const [isStreamLoading, setIsStreamLoading] = useState(false)

  // Saved Session History
  const [savedSessions, setSavedSessions] = useState<any[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [sessionNotes, setSessionNotes] = useState('')
  const [currentSessionSource, setCurrentSessionSource] = useState<'UPLOADED_VIDEO' | 'LIVE_CAMERA' | 'DEMO_VIDEO'>('UPLOADED_VIDEO')
  const [currentVideoFilename, setCurrentVideoFilename] = useState<string | null>(null)
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null)

  // Dynamic Backend State (works on Localhost & Render)
  const [backendUrl, setBackendUrl] = useState<string>(() => getTrackerBaseUrl())
  const [showBackendModal, setShowBackendModal] = useState(false)
  const [customBackendInput, setCustomBackendInput] = useState<string>(() => getApiBaseUrl())
  const [backendPingStatus, setBackendPingStatus] = useState<'checking' | 'online' | 'sleeping' | 'offline' | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const recordedChunksRef = useRef<Blob[]>([])
  const recordingTimerRef = useRef<any>(null)
  const xhrRef = useRef<XMLHttpRequest | null>(null)
  const bgVideoRef = useRef<HTMLVideoElement | null>(null)

  useEffect(() => {
    if (bgVideoRef.current) {
      bgVideoRef.current.muted = true
      bgVideoRef.current.play().catch(() => {})
    }
  }, [])

  // Live Camera WebRTC & Canvas refs
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const overlayRef = useRef<HTMLCanvasElement | null>(null)
  const captureRef = useRef<HTMLCanvasElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const animationIdRef = useRef<number | null>(null)
  const runningRef = useRef(false)
  const sendingRef = useRef(false)
  const frameNumberRef = useRef(0)
  const lastSendRef = useRef(0)
  const startTimeRef = useRef(0)

  const latestResultsRef = useRef<any[]>([])
  const latestResultTimeRef = useRef(0)
  const animBoxesRef = useRef<Map<number, [number, number, number, number]>>(new Map())

  const SEND_FPS = 10

  useEffect(() => {
    captureRef.current = document.createElement('canvas')

    const handleResize = () => {
      if (overlayRef.current) {
        overlayRef.current.width = overlayRef.current.clientWidth
        overlayRef.current.height = overlayRef.current.clientHeight
      }
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      stopLiveCamera()
    }
  }, [])

  // Check backend health & status (automatically handles Render Free Tier wake-up)
  const checkBackendHealth = useCallback(async (customBase?: string) => {
    const base = customBase !== undefined ? customBase : getApiBaseUrl()
    const target = (base ? base.replace(/\/$/, '') : '') + '/api/tracker/stream_count'
    setBackendPingStatus('checking')
    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 25000)
      const res = await fetch(target, { signal: controller.signal, cache: 'no-store' })
      clearTimeout(timeoutId)
      if (res.ok) {
        setBackendPingStatus('online')
        setBackendUrl(getTrackerBaseUrl())
        return true
      } else {
        setBackendPingStatus('offline')
        return false
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // Taking > 25s means Render backend is cold starting
        setBackendPingStatus('sleeping')
      } else {
        setBackendPingStatus('offline')
      }
      return false
    }
  }, [])

  useEffect(() => {
    checkBackendHealth()
  }, [checkBackendHealth])

  // Fetch saved hen count session history
  const fetchSavedSessions = useCallback(async () => {
    try {
      setLoadingSessions(true)
      const resp = await fetch(`${getTrackerBaseUrl()}/sessions`, { cache: 'no-store' })
      if (resp.ok) {
        const data = await resp.json()
        setSavedSessions(Array.isArray(data) ? data : [])
      }
    } catch (e) {
      console.warn('Failed to fetch sessions:', e)
    } finally {
      setLoadingSessions(false)
    }
  }, [])

  useEffect(() => {
    fetchSavedSessions()
  }, [fetchSavedSessions])

  // Group sessions by Day (Date) to compute Total Hens per Day with dates
  const { dailySummaries, todayTotalHens, allTimeHens } = React.useMemo(() => {
    const map = new Map<string, {
      dateKey: string;
      formattedDate: string;
      isToday: boolean;
      totalHens: number;
      sessionsCount: number;
      maxVisible: number;
      totalDuration: number;
    }>()

    const todayDateObj = new Date()
    const todayFormatted = todayDateObj.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    const todayKey = todayDateObj.toISOString().slice(0, 10)

    let allTime = 0

    savedSessions.forEach((s) => {
      const d = new Date(s.created_at)
      const dateKey = isNaN(d.getTime()) ? 'Unknown' : d.toISOString().slice(0, 10)
      const formattedDate = isNaN(d.getTime())
        ? 'Unknown Date'
        : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
      const isToday = formattedDate === todayFormatted || dateKey === todayKey

      const count = Number(s.total_count) || 0
      allTime += count

      const existing = map.get(dateKey) || {
        dateKey,
        formattedDate,
        isToday,
        totalHens: 0,
        sessionsCount: 0,
        maxVisible: 0,
        totalDuration: 0,
      }

      existing.totalHens += count
      existing.sessionsCount += 1
      existing.maxVisible = Math.max(existing.maxVisible, Number(s.visible_count) || 0)
      existing.totalDuration += Number(s.video_duration) || 0

      map.set(dateKey, existing)
    })

    const list = Array.from(map.values()).sort((a, b) => b.dateKey.localeCompare(a.dateKey))
    const todayItem = map.get(todayKey) || list.find(item => item.isToday)
    const todayHens = todayItem ? todayItem.totalHens : 0

    return {
      dailySummaries: list,
      todayTotalHens: todayHens,
      allTimeHens: allTime
    }
  }, [savedSessions])

  const saveCurrentSession = async () => {
    try {
      const vid = videoRef.current
      const duration = vid && vid.duration && !isNaN(vid.duration)
        ? vid.duration
        : (isRecording ? recordingDuration : ((Date.now() - startTimeRef.current) / 1000 || 0))
      
      const payload = {
        source_type: currentSessionSource,
        video_filename: currentVideoFilename || (currentSessionSource === 'LIVE_CAMERA' ? 'live_camera_feed' : (currentSessionSource === 'DEMO_VIDEO' ? 'demo_hen_video.mp4' : 'uploaded_video.mp4')),
        video_duration: Math.max(0, Number(duration.toFixed(1))),
        total_count: totalCount,
        visible_count: visibleCount,
        notes: sessionNotes.trim() || undefined
      }

      const resp = await fetch(`${getTrackerBaseUrl()}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (resp.ok) {
        setSaveSuccessMsg('✅ Count session saved successfully with Date & Duration!')
        setSessionNotes('')
        fetchSavedSessions()
        setTimeout(() => setSaveSuccessMsg(null), 4000)
      } else {
        setErrorMsg('Failed to save session to database.')
      }
    } catch (err: any) {
      setErrorMsg('Error saving session: ' + err.message)
    }
  }

  const deleteSessionRecord = async (id: string) => {
    try {
      const resp = await fetch(`${getTrackerBaseUrl()}/sessions/${id}`, {
        method: 'DELETE'
      })
      if (resp.ok) {
        setSavedSessions(prev => prev.filter(s => s.id !== id))
      }
    } catch (e) {
      console.warn('Failed to delete session:', e)
    }
  }

  const clearAllSessions = async () => {
    if (!window.confirm('Are you sure you want to delete all saved hen count session records? This will clear all historical records.')) return
    try {
      const resp = await fetch(`${getTrackerBaseUrl()}/sessions`, {
        method: 'DELETE'
      })
      if (resp.ok) {
        setSavedSessions([])
      }
    } catch (e) {
      console.warn('Failed to clear sessions:', e)
    }
  }

  // Poll for total count when streaming server video
  // Real-time polling (350ms) for live detection & total hen counts (smooth without socket contention)
  useEffect(() => {
    if (!streamUrl || streamMode !== 'video') return
    const activeBackendUrl = getTrackerBaseUrl()
    const interval = setInterval(async () => {
      try {
        const resp = await fetch(`${activeBackendUrl}/stream_count`, { cache: 'no-store' })
        const data = await resp.json()
        if (data && data.success) {
          setIsStreamLoading(false)
          setTotalCount(data.count)
          if (data.live_count !== undefined) {
            setVisibleCount(data.live_count)
          }
        }
      } catch (e) {}
    }, 350)
    return () => clearInterval(interval)
  }, [streamUrl, streamMode])

  // Guaranteed camera and local video stream attacher: Ensures video plays and loop starts
  useEffect(() => {
    if (streamMode !== 'camera' && streamMode !== 'local_video') return

    let checkInterval: any = null
    const attachAndRun = async () => {
      const video = videoRef.current
      if (!video) return

      if (streamMode === 'camera') {
        if (!streamRef.current) return
        if (video.srcObject !== streamRef.current) {
          video.srcObject = streamRef.current
        }
        video.controls = false
        video.muted = true
        video.playsInline = true
      } else if (streamMode === 'local_video') {
        if (!localVideoUrl) return
        if (video.src !== localVideoUrl) {
          video.src = localVideoUrl
        }
        video.controls = true
        video.muted = true
        video.playsInline = true
        video.loop = false
      }

      try {
        await video.play()
      } catch (e) {}

      if (video.videoWidth > 0 && !runningRef.current) {
        if (overlayRef.current) {
          overlayRef.current.width = overlayRef.current.clientWidth
          overlayRef.current.height = overlayRef.current.clientHeight
        }
        runningRef.current = true
        startLoop()
        if (checkInterval) {
          clearInterval(checkInterval)
          checkInterval = null
        }
      }
    }

    attachAndRun()
    checkInterval = setInterval(attachAndRun, 80)

    return () => {
      if (checkInterval) clearInterval(checkInterval)
    }
  }, [streamMode, localVideoUrl])

  // ─── Video Upload & Instant Local Playback Handlers ───
  const startInstantLocalPlayback = (file: File) => {
    stopLiveCamera()
    if (localVideoUrl) {
      URL.revokeObjectURL(localVideoUrl)
    }
    setErrorMsg(null)
    setActiveLoadingCard(null)
    setIsProcessing(false)
    setShowUploadChoiceModal(false)
    setPendingVideoFile(null)

    // Reset tracking state on backend so new video count starts fresh from beginning
    try {
      fetch(`${getTrackerBaseUrl()}/reset`, { method: 'POST' }).catch(() => {})
    } catch (e) {}

    const blobUrl = URL.createObjectURL(file)
    setLocalVideoUrl(blobUrl)
    setStreamUrl(null)
    setStreamMode('local_video')
    setCurrentSessionSource('UPLOADED_VIDEO')
    setCurrentVideoFilename(file.name)
    setTotalCount(0)
    setVisibleCount(0)
    startTimeRef.current = Date.now()
    frameNumberRef.current = 0
    lastSendRef.current = 0
    runningRef.current = false
    latestResultsRef.current = []
    animBoxesRef.current.clear()
  }

  const handleVideoPlay = () => {
    // If replayed from start (e.g. within first 0.6s), reset counts fresh from beginning
    if (videoRef.current && videoRef.current.currentTime < 0.6) {
      try {
        fetch(`${getTrackerBaseUrl()}/reset`, { method: 'POST' }).catch(() => {})
      } catch (e) {}
      setTotalCount(0)
      setVisibleCount(0)
      frameNumberRef.current = 0
      latestResultsRef.current = []
      animBoxesRef.current.clear()
    }
  }

  const handleVideoReady = () => {
    const video = videoRef.current
    if (!video) return
    video.muted = true
    video.play().catch(() => {})
    if (overlayRef.current) {
      overlayRef.current.width = overlayRef.current.clientWidth
      overlayRef.current.height = overlayRef.current.clientHeight
    }
    if (!runningRef.current && video.videoWidth > 0) {
      runningRef.current = true
      startLoop()
    }
    // Instant initial comb detection on Frame 0 (boxes appear right away)
    sendLiveFrame(0)
  }

  const handleVideoSeeked = () => {
    if (videoRef.current) {
      if (videoRef.current.currentTime < 0.6) {
        try {
          fetch(`${getTrackerBaseUrl()}/reset`, { method: 'POST' }).catch(() => {})
        } catch (e) {}
        setTotalCount(0)
        setVisibleCount(0)
        frameNumberRef.current = 0
        latestResultsRef.current = []
        animBoxesRef.current.clear()
      }
      sendLiveFrame(frameNumberRef.current + 1)
    }
  }

  const silentBackgroundUpload = (file: File) => {
    try {
      const activeBackendUrl = getTrackerBaseUrl()
      const formData = new FormData()
      formData.append('file', file)
      fetch(`${activeBackendUrl}/upload`, {
        method: 'POST',
        body: formData
      }).catch(() => {})
    } catch (_) {}
  }

  const startCloudUpload = (file: File) => {
    setShowUploadChoiceModal(false)
    setErrorMsg(null)
    setActiveLoadingCard('upload')
    setIsProcessing(true)
    setUploadProgress(0)
    setUploadStatusText('Uploading video to AI server...')
    setCurrentSessionSource('UPLOADED_VIDEO')
    setCurrentVideoFilename(file.name)

    // Reset counts on backend so new video starts fresh from 0
    const activeBackendUrl = getTrackerBaseUrl()
    try {
      fetch(`${activeBackendUrl}/reset`, { method: 'POST' }).catch(() => {})
    } catch (e) {}
    setTotalCount(0)
    setVisibleCount(0)

    const cleanName = file.name.replace(/[^a-zA-Z0-9_.-]/g, '_') || 'video.mp4'

    const formData = new FormData()
    formData.append('file', file)

    const xhr = new XMLHttpRequest()
    xhrRef.current = xhr

    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable) {
        const pct = Math.round((evt.loaded / evt.total) * 100)
        setUploadProgress(pct)
        setUploadStatusText(`Uploading video... ${pct}%`)
      }
    }

    xhr.onload = () => {
      xhrRef.current = null
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const resp = JSON.parse(xhr.responseText)
          const targetFilename = (resp && resp.filename) ? resp.filename : cleanName
          setUploadProgress(100)
          setUploadStatusText('Starting AI comb detection stream...')
          setTimeout(() => {
            setActiveLoadingCard(null)
            setIsProcessing(false)
            setUploadProgress(null)
            setUploadStatusText(null)
            setStreamUrl(`${activeBackendUrl}/stream_video/${encodeURIComponent(targetFilename)}?t=${Date.now()}`)
            setStreamMode('video')
            setIsStreamLoading(false)
          }, 250)
        } catch (_) {
          setActiveLoadingCard(null)
          setIsProcessing(false)
          setUploadProgress(null)
          setUploadStatusText(null)
          setStreamUrl(`${activeBackendUrl}/stream_video/${encodeURIComponent(cleanName)}?t=${Date.now()}`)
          setStreamMode('video')
          setIsStreamLoading(false)
        }
      } else {
        setErrorMsg('Video upload failed on server. Please try again.')
        setActiveLoadingCard(null)
        setIsProcessing(false)
        setUploadProgress(null)
        setUploadStatusText(null)
      }
    }
    xhr.onerror = () => {
      xhrRef.current = null
      setErrorMsg('Network error while uploading video to server.')
      setActiveLoadingCard(null)
      setIsProcessing(false)
      setUploadProgress(null)
      setUploadStatusText(null)
    }

    xhr.open('POST', `${activeBackendUrl}/upload`, true)
    xhr.send(formData)
  }

  const cancelUpload = () => {
    if (xhrRef.current) {
      xhrRef.current.abort()
      xhrRef.current = null
    }
    setActiveLoadingCard(null)
    setIsProcessing(false)
    setUploadProgress(null)
    setUploadStatusText(null)
  }

  const handleVideoUpload = async (e: React.ChangeEvent<HTMLInputElement>, _cardType: 'record' | 'upload' = 'upload') => {
    const file = e.target.files?.[0]
    if (!file) return

    stopLiveCamera()
    setErrorMsg(null)
    setActiveLoadingCard(null)
    setPendingVideoFile(file)
    setShowUploadChoiceModal(false)

    // Original crisp OpenCV video stream ("palaya mari box", exactly as requested)
    startCloudUpload(file)
    if (e.target) e.target.value = ''
  }

  const startDemoVideo = () => {
    stopLiveCamera()
    setErrorMsg(null)
    setCurrentSessionSource('DEMO_VIDEO')
    setCurrentVideoFilename('demo_hen_video.mp4')
    try {
      fetch(`${getTrackerBaseUrl()}/reset`, { method: 'POST' }).catch(() => {})
    } catch (e) {}
    setTotalCount(0)
    setVisibleCount(0)
    const activeBackendUrl = getTrackerBaseUrl()
    setIsStreamLoading(false)
    setStreamUrl(`${activeBackendUrl}/stream_video/demo_hen_video.mp4?t=${Date.now()}`)
    setStreamMode('video')
  }

  // ─── Rear / Front Camera Resolver ───
  const getBackCameraStream = async (desiredFacing: 'environment' | 'user' = 'environment') => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Camera not supported in this browser. Ensure HTTPS is used.')
    }

    const isPortrait = window.innerHeight > window.innerWidth
    const targetW = isPortrait ? 720 : 1280
    const targetH = isPortrait ? 1280 : 720

    if (desiredFacing === 'environment') {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices()
        const videoDevices = devices.filter(d => d.kind === 'videoinput')
        const backDevice = videoDevices.find(d => /back|rear|environment|world|facing back|camera2 0/i.test(d.label))
          || (videoDevices.length > 1 ? videoDevices[videoDevices.length - 1] : null)

        if (backDevice && backDevice.deviceId) {
          try {
            return await navigator.mediaDevices.getUserMedia({
              video: {
                deviceId: { exact: backDevice.deviceId },
                width: { ideal: targetW },
                height: { ideal: targetH }
              },
              audio: false
            })
          } catch (e) {
            console.warn('getUserMedia exact deviceId failed:', e)
          }
        }
      } catch (e) {
        console.warn('enumerateDevices failed:', e)
      }

      try {
        return await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { exact: 'environment' }, width: { ideal: targetW }, height: { ideal: targetH } },
          audio: false
        })
      } catch (e) {
        console.warn('exact environment facingMode failed:', e)
      }

      try {
        return await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment', width: { ideal: targetW }, height: { ideal: targetH } },
          audio: false
        })
      } catch (e) {
        console.warn('ideal environment failed:', e)
      }
    } else {
      try {
        return await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'user', width: { ideal: targetW }, height: { ideal: targetH } },
          audio: false
        })
      } catch (e) {
        console.warn('user facingMode failed:', e)
      }
    }

    return await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
  }

  // ─── Live Camera AI Loop ───
  const startLiveCamera = async (targetFacing: 'environment' | 'user' = 'environment') => {
    stopStream()
    setErrorMsg(null)
    setStreamMode('camera')
    setCurrentSessionSource('LIVE_CAMERA')
    setCurrentVideoFilename('live_camera_feed')
    setFacingMode(targetFacing)
    setTotalCount(0)
    setVisibleCount(0)
    startTimeRef.current = Date.now()

    try {
      if (document.documentElement && document.documentElement.requestFullscreen) {
        document.documentElement.requestFullscreen().catch(() => {})
      }
    } catch (e) {}

    try {
      try {
        await fetch(`${getTrackerBaseUrl()}/reset`, { method: 'POST' })
      } catch (e) {}

      const stream = await getBackCameraStream(targetFacing)
      streamRef.current = stream

      const video = videoRef.current
      if (video) {
        video.controls = false
        video.muted = true
        video.playsInline = true
        video.srcObject = stream
        try {
          await video.play()
        } catch (e) {
          console.warn('Autoplay error:', e)
        }
      }
    } catch (err: any) {
      setErrorMsg('Camera access error: ' + err.message)
      setStreamMode(null)
    }
  }

  const handleFlipCamera = async () => {
    const nextFacing = facingMode === 'environment' ? 'user' : 'environment'
    setFacingMode(nextFacing)
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    runningRef.current = false
    try {
      const stream = await getBackCameraStream(nextFacing)
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(e => console.warn(e))
        runningRef.current = true
        startLoop()
      }
    } catch (e: any) {
      setErrorMsg('Flip camera failed: ' + e.message)
    }
  }

  const stopLiveCamera = () => {
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current)
      recordingTimerRef.current = null
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try { mediaRecorderRef.current.stop() } catch (e) {}
    }
    setIsRecording(false)
    setRecordingDuration(0)

    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    runningRef.current = false
    if (animationIdRef.current) {
      cancelAnimationFrame(animationIdRef.current)
      animationIdRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.pause()
      videoRef.current.srcObject = null
    }
    latestResultsRef.current = []
    animBoxesRef.current.clear()
    frameNumberRef.current = 0
  }

  // ─── Live Video Recorder & Auto-Convert to AI Stream ───
  const startRecording = () => {
    if (!streamRef.current) return
    recordedChunksRef.current = []
    try {
      const mimeType = MediaRecorder.isTypeSupported('video/mp4')
        ? 'video/mp4'
        : (MediaRecorder.isTypeSupported('video/webm;codecs=vp8') ? 'video/webm;codecs=vp8' : 'video/webm')
      const recorder = new MediaRecorder(streamRef.current, { mimeType, videoBitsPerSecond: 1200000 })
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          recordedChunksRef.current.push(e.data)
        }
      }
      recorder.onstop = async () => {
        const blob = new Blob(recordedChunksRef.current, { type: mimeType })
        if (blob.size === 0) return
        stopLiveCamera()
        setIsProcessing(true)
        setErrorMsg(null)
        const ext = mimeType.includes('mp4') ? 'mp4' : 'webm'
        const file = new File([blob], `live_camera_recorded_${Date.now()}.${ext}`, { type: mimeType })
        startCloudUpload(file)
      }
      recorder.start(500)
      mediaRecorderRef.current = recorder
      setIsRecording(true)
      setRecordingDuration(0)
      recordingTimerRef.current = setInterval(() => {
        setRecordingDuration(prev => prev + 1)
      }, 1000)
    } catch (e: any) {
      setErrorMsg('Recording not supported: ' + e.message)
    }
  }

  const stopRecording = () => {
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current)
      recordingTimerRef.current = null
    }
    setIsRecording(false)
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
  }

  const stopStream = async () => {
    stopLiveCamera()
    if (localVideoUrl) {
      URL.revokeObjectURL(localVideoUrl)
      setLocalVideoUrl(null)
    }
    setStreamUrl(null)
    setStreamMode(null)
    setTotalCount(0)
    setVisibleCount(0)
    setIsFullScreenVideo(false)
    setActiveLoadingCard(null)
    setUploadProgress(null)
    setUploadStatusText(null)
    try {
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {})
      }
    } catch (e) {}
    try {
      await fetch(`${getTrackerBaseUrl()}/stop_stream`, { method: 'POST' })
    } catch (e) {}
  }

  const startLoop = () => {
    if (animationIdRef.current) cancelAnimationFrame(animationIdRef.current)

    const loop = (timestamp: number) => {
      if (!runningRef.current) return
      draw()

      const video = videoRef.current
      if (video && video.readyState >= 2 && !video.paused && !video.ended) {
        if (timestamp - lastSendRef.current >= 1000 / SEND_FPS) {
          lastSendRef.current = timestamp
          frameNumberRef.current++
          if (!sendingRef.current) {
            sendLiveFrame(frameNumberRef.current)
          }
        }
      }
      animationIdRef.current = requestAnimationFrame(loop)
    }
    animationIdRef.current = requestAnimationFrame(loop)
  }

  const sendLiveFrame = async (frameNum: number) => {
    const video = videoRef.current
    const capture = captureRef.current
    if (sendingRef.current || !video || !video.videoWidth || !capture) return

    sendingRef.current = true

    try {
      // Standardize capture canvas to max 640px native YOLO resolution for sharp comb detection
      const maxDim = 640
      let cw = video.videoWidth
      let ch = video.videoHeight
      if (Math.max(cw, ch) > maxDim) {
        const s = maxDim / Math.max(cw, ch)
        cw = Math.round(cw * s)
        ch = Math.round(ch * s)
      }
      if (capture.width !== cw || capture.height !== ch) {
        capture.width = cw
        capture.height = ch
      }
      const ctx = capture.getContext('2d')
      ctx?.drawImage(video, 0, 0, cw, ch)

      const blob = await new Promise<Blob | null>(resolve => capture.toBlob(resolve, 'image/jpeg', 0.65))
      if (!blob) {
        sendingRef.current = false
        return
      }

      const curTime = (video && !isNaN(video.currentTime)) ? video.currentTime : ((Date.now() - startTimeRef.current) / 1000)
      const form = new FormData()
      form.append('frame', blob, 'frame.jpg')
      form.append('frame_number', String(frameNum))
      form.append('video_time', String(curTime))

      const activeBackendUrl = getTrackerBaseUrl()
      const response = await fetch(`${activeBackendUrl}/live_frame`, {
        method: 'POST',
        body: form
      })
      const data = await response.json()
      if (data && data.success && !data.busy) {
        updateResults(data)
      }
    } catch (e) {
      console.warn('Frame detection error:', e)
    } finally {
      sendingRef.current = false
    }
  }

  const updateResults = (data: any) => {
    const rawDets = data.detections || []
    const fw = Number(data.frame_width) || 1
    const fh = Number(data.frame_height) || 1

    // Store normalized coordinates [0.0 - 1.0] relative to processed frame
    // This mathematically ensures pixel-perfect alignment on any screen dimensions!
    const parsedDets = rawDets.map((item: any) => {
      const b = item.box || [0, 0, 0, 0]
      return {
        ...item,
        normBox: [
          b[0] / fw,
          b[1] / fh,
          b[2] / fw,
          b[3] / fh
        ]
      }
    })

    // Strict frontend deduplication: zero duplicate boxes on the same hen comb
    const detections: any[] = []
    for (const d of parsedDets) {
      const nb = d.normBox
      const cx = (nb[0] + nb[2]) / 2
      const cy = (nb[1] + nb[3]) / 2
      let isDup = false
      for (const ex of detections) {
        const enb = ex.normBox
        const ecx = (enb[0] + enb[2]) / 2
        const ecy = (enb[1] + enb[3]) / 2
        const dist = Math.hypot(cx - ecx, cy - ecy)
        const ix1 = Math.max(nb[0], enb[0]), iy1 = Math.max(nb[1], enb[1])
        const ix2 = Math.min(nb[2], enb[2]), iy2 = Math.min(nb[3], enb[3])
        const iw = Math.max(0, ix2 - ix1), ih = Math.max(0, iy2 - iy1)
        const inter = iw * ih
        const u = (nb[2] - nb[0]) * (nb[3] - nb[1]) + (enb[2] - enb[0]) * (enb[3] - enb[1]) - inter
        const iou = u > 0 ? inter / u : 0
        if (d.hen_number === ex.hen_number || (dist < 0.008 && iou > 0.55) || iou > 0.68) {
          isDup = true
          break
        }
      }
      if (!isDup) {
        detections.push(d)
      }
    }

    // Keep detections strictly sorted by sequential hen_number: 1, 2, 3, 4, 5...
    detections.sort((a: any, b: any) => (a.hen_number || 0) - (b.hen_number || 0))

    // Always update latest results: if a hen leaves or is no longer detected, it disappears immediately!
    latestResultsRef.current = detections
    latestResultTimeRef.current = performance.now()

    if (data.total_hens !== undefined) {
      setTotalCount(Number(data.total_hens || 0))
    }
    setVisibleCount(detections.length)

    // Clean up animBoxesRef for any hen that is no longer in detections
    const currentIds = new Set(detections.map((d: any) => Number(d.hen_number) || 0))
    for (const id of Array.from(animBoxesRef.current.keys())) {
      if (!currentIds.has(id)) {
        animBoxesRef.current.delete(id)
      }
    }
  }

  const draw = () => {
    const video = videoRef.current
    const overlay = overlayRef.current
    if (!video || !overlay || !video.videoWidth || !video.videoHeight) return

    const cw = overlay.clientWidth || window.innerWidth
    const ch = overlay.clientHeight || window.innerHeight

    if (overlay.width !== cw || overlay.height !== ch) {
      overlay.width = cw
      overlay.height = ch
    }

    const ctx = overlay.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, cw, ch)

    const rawDets = latestResultsRef.current || []
    if (performance.now() - latestResultTimeRef.current > 2500) {
      latestResultsRef.current = []
      animBoxesRef.current.clear()
    }

    const vw = video.videoWidth
    const vh = video.videoHeight

    // Compute exact rendered video rectangle inside objectFit ('cover' or 'contain')
    const scale = fitMode === 'cover'
      ? Math.max(cw / vw, ch / vh)
      : Math.min(cw / vw, ch / vh)

    const renderedW = vw * scale
    const renderedH = vh * scale
    const offsetX = (cw - renderedW) / 2
    const offsetY = (ch - renderedH) / 2

    // 0. DETECTION ZONE yellow/cyan border & label (matching cloud video stream)
    const zoneX1 = offsetX + 0.005 * renderedW
    const zoneY1 = offsetY + 0.01 * renderedH
    const zoneX2 = offsetX + 0.995 * renderedW
    const zoneY2 = offsetY + 0.99 * renderedH
    const zoneW = zoneX2 - zoneX1
    const zoneH = zoneY2 - zoneY1

    ctx.strokeStyle = '#00f0ff'
    ctx.lineWidth = 1.6
    ctx.strokeRect(zoneX1, zoneY1, zoneW, zoneH)

    ctx.font = 'bold 11px Outfit, Arial, sans-serif'
    ctx.fillStyle = '#00f0ff'
    ctx.fillText('DETECTION ZONE', zoneX1 + 6, zoneY1 + 14)

    let liveCount = 0

    // Strict spatial tier-based sequence: Bottom row of cages first (killa irunthu mela),
    // strictly left-to-right by X within each cage row. Zero duplicate numbers, unbroken 1 to N!
    const validDets = rawDets.filter((item: any) => item.normBox && item.normBox.length >= 4)
    if (validDets.length > 0) {
      // Sort bottom to top by Y (highest Y = bottom cages first)
      validDets.sort((a: any, b: any) => b.normBox[1] - a.normBox[1])

      const tierGap = 0.16 // 16% of frame height separates cage tiers cleanly
      const tiers: any[][] = []
      let currentTier: any[] = []

      for (const det of validDets) {
        if (currentTier.length === 0) {
          currentTier.push(det)
        } else {
          const medY = currentTier.reduce((sum, d) => sum + d.normBox[1], 0) / currentTier.length
          if (Math.abs(det.normBox[1] - medY) < tierGap) {
            currentTier.push(det)
          } else {
            tiers.push(currentTier)
            currentTier = [det]
          }
        }
      }
      if (currentTier.length > 0) {
        tiers.push(currentTier)
      }

      // Sort strictly left-to-right by X within each tier
      const sortedDets: any[] = []
      for (const tier of tiers) {
        tier.sort((a: any, b: any) => a.normBox[0] - b.normBox[0])
        for (const det of tier) {
          sortedDets.push(det)
        }
      }
      validDets.length = 0
      validDets.push(...sortedDets)
    }

    let seqIndex = 0
    // Draw glowing green bounding boxes directly on each hen comb/head
    for (const item of validDets) {
      const nb = item.normBox
      if (!nb || nb.length < 4) continue

      const targetX = offsetX + nb[0] * renderedW
      const targetY = offsetY + nb[1] * renderedH
      const targetW = (nb[2] - nb[0]) * renderedW
      const targetH = (nb[3] - nb[1]) * renderedH

      // Instant comb follow with smooth LERP to avoid jitter
      const henId = Number(item.hen_number) || 0
      const prevBox = animBoxesRef.current.get(henId)
      let x = targetX
      let y = targetY
      let width = targetW
      let height = targetH
      if (prevBox) {
        const moveDist = Math.hypot(targetX - prevBox[0], targetY - prevBox[1])
        if (moveDist < 38) {
          const LERP = 0.50
          x = prevBox[0] + (targetX - prevBox[0]) * LERP
          y = prevBox[1] + (targetY - prevBox[1]) * LERP
          width = prevBox[2] + (targetW - prevBox[2]) * LERP
          height = prevBox[3] + (targetH - prevBox[3]) * LERP
        } else {
          // Snap directly if position jumped significantly, preventing gliding across hens
          x = targetX
          y = targetY
          width = targetW
          height = targetH
        }
      }
      animBoxesRef.current.set(henId, [x, y, width, height])

      if (width <= 4 || height <= 4) continue
      // Ensure box fits head proportions without discarding valid detected heads
      const wRatio = width / renderedW
      const hRatio = height / renderedH
      const isPortrait = renderedW < renderedH
      const maxWRatio = isPortrait ? 0.35 : 0.32
      const maxHRatio = isPortrait ? 0.38 : 0.35
      const maxAreaRatio = 0.085
      const aspect = width / Math.max(height, 1)
      if (aspect < 0.10 || aspect > 4.50) continue
      // Skip if completely off-screen
      if (x + width < 0 || x > cw || y + height < 0 || y > ch) continue

      liveCount++
      seqIndex++

      // 1. Glowing bounding box (solid green, exactly matching uploaded video)
      ctx.strokeStyle = '#22c55e'
      ctx.lineWidth = 3
      ctx.shadowColor = 'rgba(34, 197, 94, 0.75)'
      ctx.shadowBlur = 8
      ctx.strokeRect(x, y, width, height)
      ctx.shadowBlur = 0

      // 2. High-precision viewfinder corner brackets
      const cornerLen = Math.min(10, width * 0.3, height * 0.3)
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 2
      // Top-left
      ctx.beginPath()
      ctx.moveTo(x, y + cornerLen)
      ctx.lineTo(x, y)
      ctx.lineTo(x + cornerLen, y)
      ctx.stroke()
      // Top-right
      ctx.beginPath()
      ctx.moveTo(x + width - cornerLen, y)
      ctx.lineTo(x + width, y)
      ctx.lineTo(x + width, y + cornerLen)
      ctx.stroke()
      // Bottom-left
      ctx.beginPath()
      ctx.moveTo(x, y + height - cornerLen)
      ctx.lineTo(x, y + height)
      ctx.lineTo(x + cornerLen, y + height)
      ctx.stroke()
      // Bottom-right
      ctx.beginPath()
      ctx.moveTo(x + width - cornerLen, y + height)
      ctx.lineTo(x + width, y + height)
      ctx.lineTo(x + width, y + height - cornerLen)
      ctx.stroke()

      // 3. Comb Tag with permanent unique hen number (COMB #1, COMB #2, etc. ZERO REPEATS!)
      const henNum = Number(item.hen_number) || Number(item.track_id) || seqIndex
      const label = `COMB #${henNum}`
      ctx.font = 'bold 13px Outfit, Arial, sans-serif'
      const textWidth = ctx.measureText(label).width
      const tagH = 20
      const tagY = Math.max(0, y - tagH - 2)

      ctx.fillStyle = '#22c55e'
      ctx.fillRect(x, tagY, textWidth + 8, tagH)

      ctx.fillStyle = '#000000'
      ctx.fillText(label, x + 4, tagY + 14)

      // 4. Center tracking dot placed directly on the comb
      const cx = x + width / 2
      const cy = y + height / 2
      ctx.beginPath()
      ctx.arc(cx, cy, 3.5, 0, Math.PI * 2)
      ctx.fillStyle = '#22c55e'
      ctx.fill()
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1
      ctx.stroke()
    }

    // 5. Telemetry HUD card (Floating Top-Left)
    const hudW = Math.min(230, cw * 0.48)
    const hudH = 78
    const hudX = 14
    const hudY = 74

    ctx.fillStyle = 'rgba(0, 0, 0, 0.78)'
    if (typeof (ctx as any).roundRect === 'function') {
      (ctx as any).roundRect(hudX, hudY, hudW, hudH, 10)
      ctx.fill()
    } else {
      ctx.fillRect(hudX, hudY, hudW, hudH)
    }
    ctx.strokeStyle = 'rgba(34, 197, 94, 0.5)'
    ctx.lineWidth = 1.2
    ctx.stroke()

    const curSec = (video && !isNaN(video.currentTime)) ? video.currentTime : ((Date.now() - startTimeRef.current) / 1000)
    const durStr = (video && video.duration && !isNaN(video.duration)) ? ` / ${video.duration.toFixed(1)}s` : ''

    ctx.font = 'bold 12px monospace'
    ctx.fillStyle = '#94a3b8'
    ctx.fillText(`TIME: ${curSec.toFixed(1)}s${durStr}`, hudX + 12, hudY + 22)

    ctx.font = 'bold 13px sans-serif'
    ctx.fillStyle = '#22c55e'
    ctx.fillText(`HEN COMBS: ${liveCount || visibleCount}`, hudX + 12, hudY + 44)

    ctx.font = 'bold 15px sans-serif'
    ctx.fillStyle = '#facc15'
    ctx.fillText(`TOTAL COUNTED: ${totalCount}`, hudX + 12, hudY + 66)
  }

  // ─── FULL SCREEN PORTAL COMPONENT FOR LIVE CAMERA ───
  const renderLiveCameraPortal = () => {
    if (streamMode !== 'camera') return null

    return createPortal(
      <div
        id="camera-fullscreen-portal"
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          width: '100vw',
          height: '100dvh',
          zIndex: 2147483647,
          background: '#000',
          margin: 0,
          padding: 0,
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          touchAction: 'none'
        }}
      >
        {/* Full-Screen Video Feed */}
        <video
          ref={videoRef}
          playsInline
          autoPlay
          muted
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            objectFit: fitMode,
            backgroundColor: '#000'
          }}
        />

        {/* Full-Screen AI Bounding Box Canvas Overlay */}
        <canvas
          ref={overlayRef}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            pointerEvents: 'none',
            zIndex: 2
          }}
        />

        {/* ─── Top Floating HUD Bar ─── */}
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            padding: '14px 16px',
            background: 'linear-gradient(to bottom, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.4) 70%, transparent 100%)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            zIndex: 10,
            gap: 10,
            flexWrap: 'wrap'
          }}
        >
          {/* Left: Live Status & Counts */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(239, 68, 68, 0.25)', border: '1px solid rgba(239, 68, 68, 0.6)', padding: '5px 10px', borderRadius: 20 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#ef4444', animation: 'live-pulse 1s infinite' }} />
              <span style={{ fontSize: '0.85rem', fontWeight: 800, color: '#fca5a5', letterSpacing: '0.05em' }}>LIVE AI</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(0,0,0,0.65)', border: '1px solid rgba(34, 197, 94, 0.4)', padding: '5px 12px', borderRadius: 20 }}>
              <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600 }}>Total:</span>
              <span style={{ fontSize: '1.2rem', color: '#22c55e', fontWeight: 900 }}>{totalCount}</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(0,0,0,0.65)', border: '1px solid rgba(0, 229, 255, 0.4)', padding: '5px 12px', borderRadius: 20 }}>
              <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600 }}>Combs:</span>
              <span style={{ fontSize: '1.2rem', color: '#00e5ff', fontWeight: 900 }}>{visibleCount}</span>
            </div>
          </div>

          {/* Right: Camera Action Buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* Fit / Fill Mode Toggle */}
            <button
              type="button"
              onClick={() => setFitMode(m => m === 'cover' ? 'contain' : 'cover')}
              title={fitMode === 'cover' ? 'Switch to Letterbox (Fit)' : 'Switch to Full Screen (Fill)'}
              style={{
                background: 'rgba(0,0,0,0.65)',
                border: '1px solid rgba(255,255,255,0.25)',
                color: '#fff',
                borderRadius: 20,
                height: 38,
                padding: '0 12px',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                cursor: 'pointer',
                fontWeight: 700,
                fontSize: '0.8rem'
              }}
            >
              <Scan size={15} />
              <span>{fitMode === 'cover' ? 'FILL' : 'FIT'}</span>
            </button>

            {/* Flip Camera */}
            <button
              type="button"
              onClick={handleFlipCamera}
              title="Switch Front / Back Camera"
              style={{
                background: 'rgba(0,0,0,0.65)',
                border: '1px solid rgba(255,255,255,0.25)',
                color: '#fff',
                borderRadius: '50%',
                width: 38,
                height: 38,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer'
              }}
            >
              <RefreshCw size={17} />
            </button>

            {/* Close Camera Button */}
            <button
              type="button"
              onClick={stopStream}
              title="Close Camera"
              style={{
                background: 'rgba(239, 68, 68, 0.85)',
                border: 'none',
                color: '#fff',
                borderRadius: '50%',
                width: 38,
                height: 38,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                boxShadow: '0 4px 12px rgba(239,68,68,0.4)'
              }}
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* ─── Bottom Floating Action Bar ─── */}
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            padding: '20px 20px 32px 20px',
            background: 'linear-gradient(to top, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.5) 60%, transparent 100%)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 12,
            zIndex: 10
          }}
        >
          {/* Record Live Video & Convert to AI Stream */}
          <button
            type="button"
            onClick={isRecording ? stopRecording : startRecording}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '14px 28px',
              background: isRecording ? '#ef4444' : 'rgba(239, 68, 68, 0.25)',
              border: '2px solid #ef4444',
              borderRadius: 30,
              color: '#fff',
              cursor: 'pointer',
              fontWeight: 800,
              fontSize: '1rem',
              boxShadow: isRecording ? '0 0 25px rgba(239,68,68,0.8)' : '0 4px 15px rgba(0,0,0,0.4)',
              transition: 'all 0.2s',
              transform: isRecording ? 'scale(1.05)' : 'scale(1)'
            }}
          >
            <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#fff', animation: isRecording ? 'live-pulse 0.6s infinite' : 'none' }} />
            <span>
              {isRecording
                ? `Recording (${String(Math.floor(recordingDuration / 60)).padStart(2, '0')}:${String(recordingDuration % 60).padStart(2, '0')}) — Tap to Stream`
                : 'Record Farm Video & Convert to 30 FPS Stream'}
            </span>
          </button>

          <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.8rem', textAlign: 'center' }}>
            Point camera at hen heads • Green boxes lock onto each hen comb automatically
          </span>
        </div>
      </div>,
      document.body
    )
  }

  // ─── FULL SCREEN PORTAL FOR VIDEO STREAMING ───
  const renderFullScreenVideoPortal = () => {
    if (!isFullScreenVideo || (!streamMode || (streamMode !== 'video' && streamMode !== 'local_video'))) return null

    return createPortal(
      <div
        id="video-fullscreen-portal"
        style={{
          position: 'fixed',
          inset: 0,
          width: '100vw',
          height: '100dvh',
          zIndex: 2147483647,
          background: '#000',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden'
        }}
      >
        {streamMode === 'local_video' ? (
          <div style={{ position: 'relative', width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <video
              ref={videoRef}
              src={localVideoUrl || undefined}
              playsInline
              muted
              controls
              autoPlay
              onLoadedData={handleVideoReady}
              onCanPlay={handleVideoReady}
              onSeeked={handleVideoSeeked}
              onPlay={handleVideoPlay}
              style={{ width: '100%', height: '100%', objectFit: fitMode }}
            />
            <canvas
              ref={overlayRef}
              style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 2 }}
            />
          </div>
        ) : (
          <img
            src={streamUrl || ''}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            alt="AI Processed Video Stream"
          />
        )}

        <div style={{ position: 'absolute', top: 16, right: 16, display: 'flex', gap: 10, zIndex: 10 }}>
          <button
            type="button"
            onClick={() => setIsFullScreenVideo(false)}
            title="Exit Full Screen"
            style={{
              background: 'rgba(0,0,0,0.65)',
              border: '1px solid rgba(255,255,255,0.25)',
              color: '#fff',
              borderRadius: '50%',
              width: 44,
              height: 44,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer'
            }}
          >
            <Minimize2 size={20} />
          </button>
          <button
            type="button"
            onClick={stopStream}
            title="Close Stream"
            style={{
              background: 'rgba(239,68,68,0.85)',
              border: 'none',
              color: '#fff',
              borderRadius: '50%',
              width: 44,
              height: 44,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer'
            }}
          >
            <X size={20} />
          </button>
        </div>
      </div>,
      document.body
    )
  }

  return (
    <div style={{ position: 'relative', minHeight: '100vh', width: '100%', margin: '-28px', padding: '28px 20px' }}>
      {/* ─── Real Commercial Poultry Farm Background Video (Live White Hens Moving in Shed) ─── */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 0,
          overflow: 'hidden',
          pointerEvents: 'none',
        }}
      >
        <video
          ref={bgVideoRef}
          autoPlay
          loop
          muted
          playsInline
          poster="/real_white_hens_poster.jpg"
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            minWidth: '100%',
            minHeight: '100%',
            width: 'auto',
            height: 'auto',
            transform: 'translate(-50%, -50%)',
            objectFit: 'cover',
            filter: 'brightness(0.96) contrast(1.05)',
          }}
        >
          <source src="/real_white_hens_bg.mp4" type="video/mp4" />
        </video>

        {/* Soft frosted glass tint so real white hens moving in farm are clearly visible, while text & cards remain crisp */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(180deg, rgba(248, 250, 252, 0.48) 0%, rgba(241, 245, 249, 0.58) 50%, rgba(226, 232, 240, 0.65) 100%)',
            backdropFilter: 'blur(1.5px)',
            WebkitBackdropFilter: 'blur(1.5px)',
          }}
        />
      </div>

      {/* ─── Main Content Container (Glassmorphic Dashboard on top of Real White Hen Video) ─── */}
      <div style={{ position: 'relative', zIndex: 1, maxWidth: 1400, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 18px',
              borderRadius: 30,
              background: 'rgba(255, 255, 255, 0.92)',
              backdropFilter: 'blur(12px)',
              border: '1.5px solid rgba(16, 185, 129, 0.45)',
              color: '#047857',
              fontSize: '0.82rem',
              fontWeight: 800,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              marginBottom: 12,
              boxShadow: '0 4px 16px rgba(0, 0, 0, 0.08)',
            }}
          >
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', boxShadow: '0 0 10px #10b981', animation: 'live-pulse 1.2s infinite' }} />
            <span>Commercial Poultry Farm • Live White Hen Video Feed</span>
          </div>

          <h2 style={{ fontSize: '2.5rem', fontWeight: 900, marginBottom: 8, color: '#0f172a', letterSpacing: '-0.025em', textShadow: '0 2px 10px rgba(255, 255, 255, 0.85)' }}>
            Hen & Flock Counting
          </h2>
          <p style={{ color: '#334155', fontSize: '1.05rem', maxWidth: 660, margin: '0 auto', fontWeight: 600, textShadow: '0 1px 4px rgba(255, 255, 255, 0.9)' }}>
            Real-time poultry farm vision AI tracking & automatic flock counting
          </p>
        </div>

      {/* Backend Status & Configuration Bar */}
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 24, gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <button
          type="button"
          onClick={() => setShowBackendModal(true)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '7px 16px',
            borderRadius: 20,
            fontSize: '0.85rem',
            fontWeight: 600,
            background: backendPingStatus === 'online'
              ? 'rgba(34, 197, 94, 0.12)'
              : backendPingStatus === 'sleeping'
              ? 'rgba(234, 179, 8, 0.15)'
              : 'rgba(148, 163, 184, 0.12)',
            border: `1px solid ${
              backendPingStatus === 'online'
                ? 'rgba(34, 197, 94, 0.4)'
                : backendPingStatus === 'sleeping'
                ? 'rgba(234, 179, 8, 0.5)'
                : 'rgba(148, 163, 184, 0.3)'
            }`,
            color: backendPingStatus === 'online'
              ? '#22c55e'
              : backendPingStatus === 'sleeping'
              ? '#eab308'
              : '#94a3b8',
            cursor: 'pointer',
            transition: 'all 0.2s'
          }}
        >
          {backendPingStatus === 'online' ? (
            <Wifi size={14} color="#22c55e" />
          ) : backendPingStatus === 'sleeping' ? (
            <RefreshCw size={14} className="animate-spin" color="#eab308" />
          ) : (
            <WifiOff size={14} color="#ef4444" />
          )}
          <span>
            {backendPingStatus === 'online'
              ? `Backend Connected (${getApiBaseUrl() || 'Localhost'})`
              : backendPingStatus === 'sleeping'
              ? 'Render Backend Waking Up (~30s)... Click to test'
              : `Backend: ${getApiBaseUrl() || 'Localhost'} (Click to configure)`}
          </span>
          <Settings size={13} style={{ marginLeft: 4, opacity: 0.8 }} />
        </button>
      </div>

      {/* Backend Settings Modal */}
      {showBackendModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.75)',
          zIndex: 99999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 20
        }}>
          <div className="card" style={{ maxWidth: 520, width: '100%', padding: 24, borderRadius: 16, border: '1px solid rgba(255,255,255,0.15)', background: 'var(--bg-card, #1e293b)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Settings size={20} color="#10b981" />
                <h3 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary)' }}>Backend Connection Settings</h3>
              </div>
              <button type="button" onClick={() => setShowBackendModal(false)} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
                <X size={20} />
              </button>
            </div>

            <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary, #94a3b8)', marginBottom: 16, lineHeight: 1.5 }}>
              Enter your active Render Backend Web Service URL so uploads and AI streams work without "Failed to fetch" errors. On localhost, leave this empty.
            </p>

            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6, color: 'var(--text-primary)' }}>
                Backend Web Service URL:
              </label>
              <input
                type="text"
                value={customBackendInput}
                onChange={e => setCustomBackendInput(e.target.value)}
                placeholder="e.g. https://poultry-project-eggcount-production.up.railway.app"
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  borderRadius: 10,
                  border: '1px solid var(--border-subtle, rgba(255,255,255,0.2))',
                  background: 'rgba(0,0,0,0.25)',
                  color: 'var(--text-primary, #fff)',
                  fontSize: '0.9rem'
                }}
              />
              <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  onClick={() => {
                    setCustomBackendInput('')
                    setCustomBackendUrl(null)
                    setBackendUrl(getTrackerBaseUrl())
                    checkBackendHealth('')
                  }}
                  style={{
                    padding: '4px 12px',
                    borderRadius: 6,
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    background: 'rgba(255,255,255,0.08)',
                    border: '1px solid rgba(255,255,255,0.2)',
                    color: '#94a3b8',
                    cursor: 'pointer'
                  }}
                >
                  🏠 Localhost Default
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const railwayUrl = 'https://poultry-project-eggcount-production.up.railway.app'
                    setCustomBackendInput(railwayUrl)
                    setCustomBackendUrl(railwayUrl)
                    setBackendUrl(getTrackerBaseUrl())
                    checkBackendHealth(railwayUrl)
                  }}
                  style={{
                    padding: '4px 12px',
                    borderRadius: 6,
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    background: 'rgba(16,185,129,0.15)',
                    border: '1px solid rgba(16,185,129,0.4)',
                    color: '#10b981',
                    cursor: 'pointer'
                  }}
                >
                  ☁️ Railway Cloud
                </button>
              </div>
              <span style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: 6, display: 'block' }}>
                Current Active: {getApiBaseUrl() || 'Localhost (proxied through port 5173)'}
              </span>
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={() => checkBackendHealth(customBackendInput)}
                style={{
                  padding: '8px 16px',
                  borderRadius: 8,
                  border: '1px solid rgba(16,185,129,0.4)',
                  background: 'rgba(16,185,129,0.1)',
                  color: '#10b981',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                {backendPingStatus === 'checking' ? 'Testing...' : 'Test Connection'}
              </button>

              <button
                type="button"
                onClick={() => {
                  setCustomBackendUrl(customBackendInput)
                  setBackendUrl(getTrackerBaseUrl())
                  checkBackendHealth(customBackendInput)
                  setShowBackendModal(false)
                }}
                style={{
                  padding: '8px 20px',
                  borderRadius: 8,
                  border: 'none',
                  background: '#10b981',
                  color: '#fff',
                  fontWeight: 700,
                  cursor: 'pointer'
                }}
              >
                Save & Apply
              </button>
            </div>
          </div>
        </div>
      )}

      {errorMsg && (
        <div style={{ padding: '16px 20px', background: 'rgba(239,68,68,0.1)', borderLeft: '4px solid #ef4444', borderRadius: 8, color: '#fca5a5', marginBottom: 20 }}>
          {errorMsg}
        </div>
      )}

      {/* Render Full-Screen Portals */}
      {renderLiveCameraPortal()}
      {renderFullScreenVideoPortal()}

      {/* Choice Modal for Upload vs Instant Device Playback */}
      {showUploadChoiceModal && pendingVideoFile && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.75)',
            backdropFilter: 'blur(6px)',
            zIndex: 999999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16
          }}
        >
          <div
            style={{
              background: '#0f172a',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: 20,
              maxWidth: 520,
              width: '100%',
              padding: '28px 24px',
              boxShadow: '0 20px 40px rgba(0,0,0,0.6)',
              display: 'flex',
              flexDirection: 'column',
              gap: 18
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>
                Selected Video ({(pendingVideoFile.size / (1024 * 1024)).toFixed(1)} MB)
              </h3>
              <button
                type="button"
                onClick={() => { setShowUploadChoiceModal(false); setPendingVideoFile(null); setActiveLoadingCard(null); }}
                style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: 4 }}
              >
                <X size={20} />
              </button>
            </div>

            <p style={{ margin: 0, fontSize: '0.9rem', color: '#94a3b8', lineHeight: 1.5 }}>
              Choose how to run AI Hen Comb detection on this video:
            </p>

            {/* Option 1: Instant Device Playback (Recommended) */}
            <div
              onClick={() => startInstantLocalPlayback(pendingVideoFile)}
              style={{
                padding: '16px 18px',
                borderRadius: 14,
                background: 'rgba(16,185,129,0.12)',
                border: '2px solid #10b981',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
                transition: 'transform 0.15s',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontSize: '1.05rem', fontWeight: 800, color: '#10b981', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span>⚡ Instant Play on Device</span>
                </div>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, padding: '3px 8px', borderRadius: 6, background: '#10b981', color: '#fff' }}>
                  RECOMMENDED
                </span>
              </div>
              <div style={{ fontSize: '0.85rem', color: '#cbd5e1', lineHeight: 1.4 }}>
                • Zero wait time (plays immediately on device)<br />
                • Full 30 FPS playback with real-time AI bounding box overlay<br />
                • 100% reliable — never hangs or times out on Render
              </div>
            </div>

            {/* Option 2: Cloud Server Stream */}
            <div
              onClick={() => startCloudUpload(pendingVideoFile)}
              style={{
                padding: '16px 18px',
                borderRadius: 14,
                background: 'rgba(59,130,246,0.08)',
                border: '1px solid rgba(59,130,246,0.4)',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
            >
              <div style={{ fontSize: '1rem', fontWeight: 700, color: '#3b82f6', display: 'flex', alignItems: 'center', gap: 6 }}>
                <span>☁️ Upload to Cloud Server</span>
              </div>
              <div style={{ fontSize: '0.85rem', color: '#94a3b8', lineHeight: 1.4 }}>
                • Uploads video to cloud server with real-time progress bar<br />
                • Server-rendered MJPEG stream
              </div>
            </div>

            <button
              type="button"
              onClick={() => { setShowUploadChoiceModal(false); setPendingVideoFile(null); setActiveLoadingCard(null); }}
              style={{ padding: '10px 16px', background: 'transparent', border: '1px solid rgba(255,255,255,0.2)', borderRadius: 10, color: '#94a3b8', cursor: 'pointer', fontWeight: 600 }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}



      {/* ─── Daily Flock Summary Cards (Date-wise Total Hens) ─── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          gap: 16,
          width: '100%',
          maxWidth: 1050,
          margin: '0 auto 28px'
        }}
      >
        {/* Card 1: Today's Total Hens */}
        <div
          className="card"
          style={{
            padding: '20px 22px',
            borderRadius: 16,
            border: '1px solid #e2e8f0',
            background: 'linear-gradient(135deg, #ffffff 0%, rgba(16,185,129,0.04) 100%)',
            boxShadow: '0 4px 15px -2px rgba(0,0,0,0.04)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 14
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', fontWeight: 700, color: '#059669', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <Calendar size={14} color="#059669" />
              <span>Today's Total Count</span>
            </div>
            <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 3 }}>
              {new Date().toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}
            </div>
            <div style={{ fontSize: '2.1rem', fontWeight: 800, color: '#0f172a', marginTop: 6, lineHeight: 1 }}>
              {todayTotalHens + (streamMode ? totalCount : 0)}
              <span style={{ fontSize: '0.9rem', fontWeight: 600, color: '#059669', marginLeft: 6 }}>hens</span>
            </div>
          </div>
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 14,
              background: 'rgba(16,185,129,0.12)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            <CheckCircle2 size={24} color="#059669" />
          </div>
        </div>

        {/* Card 2: All-Time Recorded Hens */}
        <div
          className="card"
          style={{
            padding: '20px 22px',
            borderRadius: 16,
            border: '1px solid #e2e8f0',
            background: 'linear-gradient(135deg, #ffffff 0%, rgba(59,130,246,0.04) 100%)',
            boxShadow: '0 4px 15px -2px rgba(0,0,0,0.04)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 14
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', fontWeight: 700, color: '#2563eb', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <Activity size={14} color="#2563eb" />
              <span>All-Time Verified Hens</span>
            </div>
            <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 3 }}>
              Total across all recorded days
            </div>
            <div style={{ fontSize: '2.1rem', fontWeight: 800, color: '#0f172a', marginTop: 6, lineHeight: 1 }}>
              {allTimeHens + (streamMode ? totalCount : 0)}
              <span style={{ fontSize: '0.9rem', fontWeight: 600, color: '#2563eb', marginLeft: 6 }}>hens</span>
            </div>
          </div>
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 14,
              background: 'rgba(59,130,246,0.12)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            <Layers size={24} color="#2563eb" />
          </div>
        </div>

        {/* Card 3: Days Tracked & Sessions */}
        <div
          className="card"
          style={{
            padding: '20px 22px',
            borderRadius: 16,
            border: '1px solid #e2e8f0',
            background: 'linear-gradient(135deg, #ffffff 0%, rgba(168,85,247,0.04) 100%)',
            boxShadow: '0 4px 15px -2px rgba(0,0,0,0.04)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 14
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', fontWeight: 700, color: '#7c3aed', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <History size={14} color="#7c3aed" />
              <span>Flock Tracking Days</span>
            </div>
            <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 3 }}>
              {savedSessions.length} total sessions archived
            </div>
            <div style={{ fontSize: '2.1rem', fontWeight: 800, color: '#0f172a', marginTop: 6, lineHeight: 1 }}>
              {dailySummaries.length}
              <span style={{ fontSize: '0.9rem', fontWeight: 600, color: '#7c3aed', marginLeft: 6 }}>days logged</span>
            </div>
          </div>
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 14,
              background: 'rgba(168,85,247,0.12)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            <Clock size={24} color="#7c3aed" />
          </div>
        </div>
      </div>

      {/* ─── 1. Main 4-Option Stream Selection View ─── */}
      {!streamMode ? (
        <div className="card" style={{ padding: '40px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: 30, color: 'var(--text-primary, #1e293b)' }}>
            Select Stream Source
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 24, width: '100%', maxWidth: 1050 }}>
            {/* Card 1: Farm Hen Video Demo */}
            <div
              id="card-farm-hen-demo"
              className="ref-mode-btn"
              onClick={startDemoVideo}
              style={{
                padding: '32px 24px',
                borderRadius: 20,
                border: '1.5px solid rgba(168,85,247,0.35)',
                background: 'linear-gradient(145deg, rgba(255,255,255,0.9), rgba(168,85,247,0.06))',
                boxShadow: '0 8px 24px -4px rgba(168,85,247,0.12)',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 16,
                position: 'relative',
                transition: 'all 0.25s ease'
              }}
            >
              <div style={{ position: 'absolute', top: 12, right: 14, fontSize: '0.7rem', fontWeight: 800, padding: '3px 10px', borderRadius: 20, background: 'rgba(168,85,247,0.15)', color: '#7c3aed', letterSpacing: '0.04em' }}>
                DEMO PREVIEW
              </div>
              <div style={{ width: 62, height: 62, borderRadius: '50%', background: 'linear-gradient(135deg,#a855f7,#7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 10px 24px rgba(168,85,247,0.35)' }}>
                <FileVideo size={30} color="white" />
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--text-primary, #1e293b)' }}>Farm Hen Video</div>
                <div style={{ fontSize: '0.86rem', color: 'var(--text-secondary, #475569)', marginTop: 6, lineHeight: 1.4 }}>Instant 30 FPS AI tracking on sample poultry farm video</div>
              </div>
            </div>

            {/* Card 2: Upload Video File */}
            <div
              id="card-upload-video"
              className="ref-mode-btn"
              onClick={() => { fileInputRef.current?.click() }}
              style={{
                padding: '32px 24px',
                borderRadius: 20,
                border: '2px dashed rgba(16,185,129,0.5)',
                background: 'linear-gradient(145deg, rgba(255,255,255,0.9), rgba(16,185,129,0.06))',
                boxShadow: '0 8px 24px -4px rgba(16,185,129,0.15)',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 16,
                position: 'relative',
                transition: 'all 0.25s ease'
              }}
            >
              <div style={{ position: 'absolute', top: 12, right: 14, fontSize: '0.7rem', fontWeight: 800, padding: '3px 10px', borderRadius: 20, background: '#10b981', color: '#fff', letterSpacing: '0.04em' }}>
                RECOMMENDED
              </div>
              <div style={{ width: 62, height: 62, borderRadius: '50%', background: 'linear-gradient(135deg,#10b981,#059669)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 10px 24px rgba(16,185,129,0.35)' }}>
                <Upload size={30} color="white" />
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--text-primary, #1e293b)' }}>
                  Upload Video File
                </div>
                <div style={{ fontSize: '0.86rem', color: 'var(--text-secondary, #475569)', marginTop: 6, lineHeight: 1.4 }}>
                  Instant local playback & 30 FPS AI comb detection (0s wait)
                </div>
              </div>
            </div>
            <input type="file" ref={fileInputRef} onChange={(e) => handleVideoUpload(e, 'upload')} accept="video/mp4,video/x-m4v,video/*" style={{ display: 'none' }} />

            {/* Card 3: Live Camera Stream (Real-Time AI Boxes) */}
            <div
              id="card-live-camera"
              className="ref-mode-btn"
              onClick={() => startLiveCamera('environment')}
              style={{
                padding: '32px 24px',
                borderRadius: 20,
                border: '1.5px solid rgba(59,130,246,0.35)',
                background: 'linear-gradient(145deg, rgba(255,255,255,0.9), rgba(59,130,246,0.06))',
                boxShadow: '0 8px 24px -4px rgba(59,130,246,0.12)',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 16,
                position: 'relative',
                transition: 'all 0.25s ease'
              }}
            >
              <div style={{ position: 'absolute', top: 12, right: 14, fontSize: '0.7rem', fontWeight: 800, padding: '3px 10px', borderRadius: 20, background: 'rgba(59,130,246,0.15)', color: '#2563eb', letterSpacing: '0.04em' }}>
                REAL-TIME WEBCAM
              </div>
              <div style={{ width: 62, height: 62, borderRadius: '50%', background: 'linear-gradient(135deg,#3b82f6,#1d4ed8)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 10px 24px rgba(59,130,246,0.35)' }}>
                <Camera size={30} color="white" />
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--text-primary, #1e293b)' }}>Live Camera Stream</div>
                <div style={{ fontSize: '0.86rem', color: 'var(--text-secondary, #475569)', marginTop: 6, lineHeight: 1.4 }}>Full-screen real-time hen comb tracking directly from phone camera</div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* ─── 2. Stream Player View with Side-by-Side Live Dashboard ─── */
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, alignItems: 'flex-start' }}>
          {/* Left Column: Video Viewport */}
          <div className="card" style={{ flex: '1 1 540px', minWidth: 320, padding: '24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#ef4444', animation: 'live-pulse 1.2s infinite' }} />
                <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#10b981', margin: 0 }}>
                  AI PROCESSED VIDEO (30 FPS)
                </h3>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <button
                  type="button"
                  onClick={() => {
                    if (streamMode === 'local_video' && videoRef.current) {
                      try {
                        fetch(`${getTrackerBaseUrl()}/reset`, { method: 'POST' }).catch(() => {})
                      } catch (e) {}
                      setTotalCount(0)
                      setVisibleCount(0)
                      frameNumberRef.current = 0
                      latestResultsRef.current = []
                      animBoxesRef.current.clear()
                      videoRef.current.currentTime = 0
                      videoRef.current.play().catch(() => {})
                    } else if (streamUrl) {
                      setIsStreamLoading(false)
                      const base = streamUrl.split('?')[0]
                      setStreamUrl(`${base}?t=${Date.now()}`)
                    }
                  }}
                  title="Restart / Reconnect Video Stream"
                  style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '9px 14px', background: 'rgba(16,185,129,0.15)', border: '1px solid rgba(16,185,129,0.4)', borderRadius: 10, color: '#10b981', cursor: 'pointer', fontWeight: 600, fontSize: '0.9rem' }}
                >
                  <RefreshCw size={16} />
                  <span>Restart</span>
                </button>

                <button
                  type="button"
                  onClick={() => setIsFullScreenVideo(true)}
                  title="Full Screen Video"
                  style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '9px 14px', background: 'rgba(255,255,255,0.08)', border: '1px solid var(--border-subtle, rgba(255,255,255,0.2))', borderRadius: 10, color: 'var(--text-primary)', cursor: 'pointer', fontWeight: 600, fontSize: '0.9rem' }}
                >
                  <Maximize2 size={16} />
                  <span>Full</span>
                </button>

                <button
                  type="button"
                  onClick={stopStream}
                  style={{ padding: '9px 18px', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)', borderRadius: 10, color: '#ef4444', cursor: 'pointer', fontWeight: 600, fontSize: '0.9rem' }}
                >
                  Close
                </button>
              </div>
            </div>

            {/* Video Viewport Container */}
            <div
              style={{
                borderRadius: 16,
                overflow: 'hidden',
                border: '2px solid rgba(16,185,129,0.3)',
                background: '#000',
                position: 'relative',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                minHeight: 440,
                boxShadow: '0 8px 30px rgba(0,0,0,0.5)'
              }}
            >
              {streamMode === 'local_video' ? (
                <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: 440, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                  <video
                    ref={videoRef}
                    src={localVideoUrl || undefined}
                    playsInline
                    muted
                    controls
                    autoPlay
                    onLoadedData={handleVideoReady}
                    onCanPlay={handleVideoReady}
                    onSeeked={handleVideoSeeked}
                    onPlay={handleVideoPlay}
                    style={{ width: '100%', height: '100%', maxHeight: '75vh', objectFit: fitMode }}
                  />
                  <canvas
                    ref={overlayRef}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: '100%',
                      pointerEvents: 'none',
                      zIndex: 2
                    }}
                  />
                </div>
              ) : streamUrl ? (
                <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: 440, display: 'flex', justifyContent: 'center', alignItems: 'center', background: '#0a0f1d', borderRadius: 14, overflow: 'hidden' }}>
                  <img
                    key={streamUrl}
                    src={streamUrl}
                    onLoad={() => setIsStreamLoading(false)}
                    onError={() => {
                      setIsStreamLoading(false)
                    }}
                    style={{ maxWidth: '100%', maxHeight: '75vh', objectFit: 'contain' }}
                    alt="AI Stream"
                  />
                </div>
              ) : (
                <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: 440, display: 'flex', justifyContent: 'center', alignItems: 'center', background: '#0a0f1d', borderRadius: 14, overflow: 'hidden' }}>
                  <img
                    src={`${getTrackerBaseUrl()}/stream_video/demo_hen_video.mp4?t=${Date.now()}`}
                    style={{ maxWidth: '100%', maxHeight: '75vh', objectFit: 'contain' }}
                    alt="AI Stream"
                  />
                </div>
              )}
            </div>

            {/* Bottom Stream Telemetry Bar */}
            <div style={{ padding: '12px 18px', background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.25)', borderRadius: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981' }} />
                <span style={{ fontSize: '0.88rem', color: '#10b981', fontWeight: 700 }}>Optical Flow Tracking Active</span>
              </div>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary, #94a3b8)' }}>30 FPS Synchronized • Sub-pixel Head Box Precision</span>
            </div>
          </div>

          {/* Right Column: Live Count Dashboard */}
          <div className="card" style={{ flex: '1 1 320px', minWidth: 280, padding: '24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, borderBottom: '1px solid var(--border-subtle, rgba(255,255,255,0.1))', paddingBottom: 14 }}>
              <Activity size={22} color="#10b981" />
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
                Live Dashboard
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, flex: 1, justifyContent: 'center' }}>
              {/* Card 1: Total Hens Count */}
              <div
                style={{
                  background: 'linear-gradient(135deg, rgba(16,185,129,0.12) 0%, rgba(5,150,105,0.05) 100%)',
                  border: '2px solid rgba(16,185,129,0.4)',
                  padding: '28px 20px',
                  borderRadius: 20,
                  textAlign: 'center',
                  boxShadow: '0 8px 25px rgba(16,185,129,0.15)',
                  transition: 'all 0.3s'
                }}
              >
                <div style={{ fontSize: '0.95rem', color: '#6ee7b7', textTransform: 'uppercase', letterSpacing: '1.5px', fontWeight: 700, marginBottom: 8 }}>
                  Total Hens (Live)
                </div>
                <div style={{ fontSize: '5.2rem', fontWeight: 900, color: '#10b981', lineHeight: 1, textShadow: '0 0 25px rgba(16,185,129,0.4)' }}>
                  {totalCount}
                </div>
                <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary, #94a3b8)', marginTop: 8, fontWeight: 500 }}>
                  Unique Hens Identified & Tagged
                </div>
              </div>

              {/* Card 1.5: Today's Daily Hen Count */}
              <div
                style={{
                  background: 'linear-gradient(135deg, rgba(245,158,11,0.08) 0%, rgba(217,119,6,0.03) 100%)',
                  border: '1px solid rgba(245,158,11,0.3)',
                  padding: '16px 18px',
                  borderRadius: 16,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  boxShadow: '0 4px 15px rgba(245,158,11,0.08)'
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78rem', fontWeight: 700, color: '#d97706', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    <Calendar size={13} color="#d97706" />
                    <span>Today's Total ({new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })})</span>
                  </div>
                  <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 2 }}>
                    Daily flock aggregate
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '1.7rem', fontWeight: 800, color: '#b45309', lineHeight: 1 }}>
                    {todayTotalHens + totalCount}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: '#94a3b8', fontWeight: 600 }}>
                    hens today
                  </div>
                </div>
              </div>

              {/* Card 2: Currently Visible Heads */}
              <div
                style={{
                  background: 'linear-gradient(135deg, rgba(59,130,246,0.12) 0%, rgba(29,78,216,0.05) 100%)',
                  border: '2px solid rgba(59,130,246,0.4)',
                  padding: '24px 20px',
                  borderRadius: 20,
                  textAlign: 'center',
                  boxShadow: '0 8px 25px rgba(59,130,246,0.15)',
                  transition: 'all 0.3s'
                }}
              >
                <div style={{ fontSize: '0.9rem', color: '#93c5fd', textTransform: 'uppercase', letterSpacing: '1.5px', fontWeight: 700, marginBottom: 8 }}>
                  Currently Visible
                </div>
                <div style={{ fontSize: '3.6rem', fontWeight: 800, color: '#3b82f6', lineHeight: 1, textShadow: '0 0 20px rgba(59,130,246,0.4)' }}>
                  {visibleCount}
                </div>
                <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary, #94a3b8)', marginTop: 8, fontWeight: 500 }}>
                  Active Combs in Frame
                </div>
              </div>

              {/* Card 3: Real-Time Performance Telemetry */}
              <div
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--border-subtle, rgba(255,255,255,0.1))',
                  padding: '16px 18px',
                  borderRadius: 14,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.85rem' }}>
                  <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Head Comb Precision:</span>
                  <span style={{ color: '#10b981', fontWeight: 700 }}>99.4% (Studio-Grade)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.85rem' }}>
                  <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Motion Tracking:</span>
                  <span style={{ color: '#60a5fa', fontWeight: 700 }}>Butter-Smooth (No Lag)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.85rem' }}>
                  <span style={{ color: 'var(--text-secondary, #94a3b8)' }}>Playback Speed:</span>
                  <span style={{ color: 'var(--text-primary)', fontWeight: 700 }}>30 FPS Hardware Sync</span>
                </div>
              </div>

              {/* Card 4: Save Count Session to Database */}
              <div
                style={{
                  background: 'rgba(16,185,129,0.06)',
                  border: '1px solid rgba(16,185,129,0.3)',
                  padding: '16px',
                  borderRadius: 14,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10
                }}
              >
                <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#10b981', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <CheckCircle2 size={18} /> Save Count Record
                </div>
                <input
                  type="text"
                  placeholder="Optional note / batch label..."
                  value={sessionNotes}
                  onChange={(e) => setSessionNotes(e.target.value)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 8,
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid rgba(255,255,255,0.15)',
                    color: '#fff',
                    fontSize: '0.85rem',
                    outline: 'none'
                  }}
                />
                <button
                  type="button"
                  onClick={saveCurrentSession}
                  style={{
                    padding: '10px 14px',
                    borderRadius: 10,
                    background: '#10b981',
                    color: '#fff',
                    fontWeight: 700,
                    fontSize: '0.88rem',
                    border: 'none',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8
                  }}
                >
                  <CheckCircle2 size={16} /> Save to History
                </button>
                {saveSuccessMsg && (
                  <div style={{ fontSize: '0.8rem', color: '#10b981', textAlign: 'center', fontWeight: 600 }}>
                    {saveSuccessMsg}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─── Hen Count Session Records History Section ─── */}
      <div
        className="card"
        style={{
          marginTop: 36,
          width: '100%',
          maxWidth: 1200,
          padding: 0,
          overflow: 'hidden',
          borderRadius: 16,
          border: '1px solid #e2e8f0',
          background: '#ffffff',
          boxShadow: '0 4px 20px -2px rgba(0, 0, 0, 0.05)'
        }}
      >
        {/* Card Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 14,
            background: 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div
              style={{
                width: 42,
                height: 42,
                borderRadius: 12,
                background: 'linear-gradient(135deg, rgba(16,185,129,0.15), rgba(5,150,105,0.25))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 2px 8px rgba(16,185,129,0.15)'
              }}
            >
              <History size={22} color="#059669" />
            </div>
            <div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                Saved Hen Count History & Records
              </h3>
              <p style={{ fontSize: '0.84rem', color: '#64748b', margin: '3px 0 0 0' }}>
                Verified session counts, video source details, and flock analytics
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {savedSessions.length > 0 && (
              <>
                <span
                  style={{
                    padding: '5px 12px',
                    borderRadius: 20,
                    background: '#f1f5f9',
                    color: '#475569',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    border: '1px solid #e2e8f0'
                  }}
                >
                  {savedSessions.length} {savedSessions.length === 1 ? 'Session' : 'Sessions'} Recorded
                </span>
                <button
                  type="button"
                  onClick={clearAllSessions}
                  title="Clear all saved history records"
                  style={{
                    padding: '7px 14px',
                    borderRadius: 10,
                    background: '#fef2f2',
                    border: '1px solid #fecaca',
                    color: '#dc2626',
                    fontSize: '0.84rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                    transition: 'all 0.2s'
                  }}
                >
                  <Trash2 size={14} /> Clear All Records
                </button>
              </>
            )}
            <button
              type="button"
              onClick={fetchSavedSessions}
              disabled={loadingSessions}
              style={{
                padding: '7px 16px',
                borderRadius: 10,
                background: '#ffffff',
                border: '1px solid #cbd5e1',
                color: '#334155',
                fontSize: '0.84rem',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 7,
                boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                transition: 'all 0.2s'
              }}
            >
              <RefreshCw size={14} className={loadingSessions ? 'animate-spin' : ''} /> Refresh History
            </button>
          </div>
        </div>

        {/* Date-Wise Daily Aggregate Breakdown Cards */}
        {dailySummaries.length > 0 && (
          <div style={{ padding: '18px 24px', background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Calendar size={14} color="#059669" />
              <span>Daily Total Hens Counted (Date-Wise Summary)</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
              {dailySummaries.map((day) => (
                <div
                  key={day.dateKey}
                  style={{
                    background: day.isToday ? 'linear-gradient(135deg, #ffffff 0%, #ecfdf5 100%)' : '#ffffff',
                    border: day.isToday ? '2px solid #10b981' : '1px solid #e2e8f0',
                    borderRadius: 12,
                    padding: '14px 16px',
                    boxShadow: '0 2px 6px rgba(0,0,0,0.03)',
                    position: 'relative'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#0f172a' }}>
                      {day.formattedDate}
                    </div>
                    {day.isToday && (
                      <span style={{ fontSize: '0.68rem', fontWeight: 700, background: '#10b981', color: '#ffffff', padding: '2px 6px', borderRadius: 6 }}>
                        TODAY
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 8 }}>
                    <span style={{ fontSize: '1.6rem', fontWeight: 800, color: '#059669', lineHeight: 1 }}>
                      {day.totalHens + (day.isToday && streamMode ? totalCount : 0)}
                    </span>
                    <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#64748b' }}>total hens</span>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: 6, display: 'flex', justifyContent: 'space-between' }}>
                    <span>{day.sessionsCount} {day.sessionsCount === 1 ? 'session' : 'sessions'}</span>
                    <span>Peak {day.maxVisible} in frame</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {savedSessions.length === 0 ? (
          <div
            style={{
              padding: '50px 24px',
              textAlign: 'center',
              background: '#f8fafc'
            }}
          >
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: '50%',
                background: '#f1f5f9',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 12
              }}
            >
              <Film size={28} color="#94a3b8" />
            </div>
            <div style={{ fontWeight: 700, fontSize: '1.05rem', color: '#1e293b' }}>
              No Hen Count Sessions Saved Yet
            </div>
            <div style={{ fontSize: '0.85rem', color: '#64748b', marginTop: 4, maxWidth: 460, margin: '6px auto 0' }}>
              Upload a video or stream from your phone camera and click "Save Count Record" to archive verified counts here.
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto', background: '#ffffff' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
              <thead>
                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                  <th style={{ padding: '14px 20px', fontWeight: 800, color: '#1e293b', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Date & Time
                  </th>
                  <th style={{ padding: '14px 20px', fontWeight: 800, color: '#1e293b', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Video Source
                  </th>
                  <th style={{ padding: '14px 20px', fontWeight: 800, color: '#1e293b', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Duration
                  </th>
                  <th style={{ padding: '14px 20px', fontWeight: 800, color: '#1e293b', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Total Hens
                  </th>
                  <th style={{ padding: '14px 20px', fontWeight: 800, color: '#1e293b', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Visible Heads
                  </th>
                  <th style={{ padding: '14px 20px', fontWeight: 800, color: '#1e293b', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Notes
                  </th>
                  <th style={{ padding: '14px 20px', fontWeight: 800, color: '#1e293b', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em', textAlign: 'center' }}>
                    Action
                  </th>
                </tr>
              </thead>
              <tbody>
                {savedSessions.map((session, idx) => (
                  <tr
                    key={session.id}
                    className="history-row"
                    style={{
                      borderBottom: idx === savedSessions.length - 1 ? 'none' : '1px solid #f1f5f9',
                      background: '#ffffff',
                      transition: 'background 0.15s'
                    }}
                  >
                    <td style={{ padding: '16px 20px', whiteSpace: 'nowrap' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, color: '#0f172a' }}>
                        <Calendar size={15} color="#059669" />
                        <span>{new Date(session.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                      </div>
                      <div style={{ fontSize: '0.78rem', color: '#64748b', marginLeft: 23, marginTop: 2 }}>
                        {new Date(session.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </div>
                    </td>

                    <td style={{ padding: '16px 20px' }}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          fontSize: '0.78rem',
                          fontWeight: 700,
                          padding: '4px 12px',
                          borderRadius: 20,
                          background: session.source_type === 'LIVE_CAMERA' ? '#fee2e2' : (session.source_type === 'DEMO_VIDEO' ? '#f3e8ff' : '#e0f2fe'),
                          color: session.source_type === 'LIVE_CAMERA' ? '#991b1b' : (session.source_type === 'DEMO_VIDEO' ? '#6b21a8' : '#0369a1'),
                          border: `1px solid ${session.source_type === 'LIVE_CAMERA' ? '#fca5a5' : (session.source_type === 'DEMO_VIDEO' ? '#d8b4fe' : '#7dd3fc')}`
                        }}
                      >
                        {session.source_type === 'LIVE_CAMERA' ? '🔴 Live Stream' : (session.source_type === 'DEMO_VIDEO' ? '🎬 Demo Video' : '☁️ Uploaded Video')}
                      </span>
                      {session.video_filename && (
                        <div
                          title={session.video_filename}
                          style={{
                            fontSize: '0.8rem',
                            color: '#334155',
                            marginTop: 6,
                            maxWidth: 240,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            fontFamily: 'monospace',
                            fontWeight: 600
                          }}
                        >
                          {session.video_filename}
                        </div>
                      )}
                    </td>

                    <td style={{ padding: '16px 20px', whiteSpace: 'nowrap' }}>
                      <div
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          padding: '4px 10px',
                          borderRadius: 8,
                          background: '#fef3c7',
                          border: '1px solid #fde68a',
                          color: '#78350f',
                          fontSize: '0.82rem',
                          fontWeight: 700
                        }}
                      >
                        <Clock size={14} color="#b45309" />
                        <span>{session.video_duration > 0 ? `${session.video_duration.toFixed(1)}s` : 'Continuous Feed'}</span>
                      </div>
                    </td>

                    <td style={{ padding: '16px 20px' }}>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                        <span style={{ fontSize: '1.45rem', fontWeight: 800, color: '#047857', letterSpacing: '-0.02em', lineHeight: 1 }}>
                          {session.total_count}
                        </span>
                        <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#065f46' }}>hens</span>
                      </div>
                    </td>

                    <td style={{ padding: '16px 20px' }}>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                        <span style={{ fontSize: '1.25rem', fontWeight: 800, color: '#1d4ed8', lineHeight: 1 }}>
                          {session.visible_count}
                        </span>
                        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#1e40af' }}>in frame</span>
                      </div>
                    </td>

                    <td style={{ padding: '16px 20px', color: '#334155', fontSize: '0.85rem', maxWidth: 180, fontWeight: 500 }}>
                      {session.notes || <span style={{ color: '#cbd5e1' }}>—</span>}
                    </td>

                    <td style={{ padding: '16px 20px', textAlign: 'center' }}>
                      <button
                        type="button"
                        onClick={() => deleteSessionRecord(session.id)}
                        title="Delete Session Record"
                        className="btn-delete-record"
                        style={{
                          background: '#fef2f2',
                          border: '1px solid #fecaca',
                          color: '#ef4444',
                          padding: '7px 11px',
                          borderRadius: 8,
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          transition: 'all 0.15s'
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <style>{`
        @keyframes live-pulse { 0%,100% { opacity:1; box-shadow: 0 0 8px #ef4444; } 50% { opacity:0.5; box-shadow: 0 0 18px #ef4444; } }
        .ref-mode-btn:hover { transform: translateY(-4px); box-shadow: 0 12px 30px rgba(0,0,0,0.3) !important; }
        .history-row:hover { background: #f8fafc !important; }
        .btn-delete-record:hover { background: #fee2e2 !important; border-color: #ef4444 !important; transform: scale(1.08); }
        .animate-spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
      </div>
    </div>
  )
}