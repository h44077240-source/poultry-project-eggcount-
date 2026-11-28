import React, { useState, useRef, useEffect } from 'react'
import { aiApi } from '../services/api'
import {
  Send,
  Paperclip,
  X,
  Loader,
  Bot,
  User as UserIcon,
  Image as ImageIcon,
  Camera,
  History,
  Calendar,
  Trash2,
  Clock,
  RefreshCw,
  MessageSquare,
  Sparkles,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface TrayTypes {
  green_plastic: number
  paper_cardboard: number
  other: number
  unknown: number
}

interface AnalysisData {
  success: boolean
  egg_count: number
  tray_count: number
  tray_types: TrayTypes
  confidence: 'high' | 'medium' | 'low'
  image_quality: 'good' | 'fair' | 'poor'
  notes: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  imagePreview?: string   // blob URL for user messages
  analysis?: AnalysisData // structured result from assistant
  loading?: boolean
}

interface HistoryConversation {
  id: string
  created_at: string
  time: string
  user_name: string
  user_message: string
  assistant_reply: string
  has_image: boolean
  image_filename?: string
  structured_data?: string
}

interface DailyChatSummary {
  date: string
  formatted_date: string
  total_messages: number
  conversations: HistoryConversation[]
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const confidenceColor = (c: string) => {
  if (c === 'high') return '#10b981'
  if (c === 'medium') return '#f59e0b'
  return '#ef4444'
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

const uid = () => Math.random().toString(36).slice(2)

/**
 * Format message cleanly without raw asterisks or markdown clutter.
 * Converts **bold text** to styled <strong> tags and renders bullets elegantly.
 */
function renderFormattedMessage(text: string, isUser = false) {
  if (!text) return null
  if (isUser) return text

  const lines = text.split('\n')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {lines.map((line, idx) => {
        const trimmed = line.trim()
        if (!trimmed) {
          return <div key={idx} style={{ height: 6 }} />
        }

        const isBullet = trimmed.startsWith('•') || trimmed.startsWith('- ') || trimmed.startsWith('* ')
        const cleanContent = isBullet ? trimmed.replace(/^[•\-\*]\s*/, '') : trimmed

        // Parse **bold text** into strong tags without asterisks
        const parts = cleanContent.split(/(\*\*[^*]+\*\*)/g)
        const renderedParts = parts.map((part, pIdx) => {
          if (part.startsWith('**') && part.endsWith('**')) {
            const boldText = part.slice(2, -2).trim()
            return (
              <strong key={pIdx} style={{ color: 'var(--brand-400, #38bdf8)', fontWeight: 700 }}>
                {boldText}
              </strong>
            )
          }
          return part.replace(/\*{1,3}/g, '')
        })

        if (isBullet) {
          return (
            <div
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
                paddingLeft: 4,
                lineHeight: 1.5,
              }}
            >
              <span style={{ color: 'var(--brand-400, #38bdf8)', fontSize: '1rem', lineHeight: '1.4' }}>•</span>
              <span style={{ flex: 1 }}>{renderedParts}</span>
            </div>
          )
        }

        return (
          <div key={idx} style={{ lineHeight: 1.55 }}>
            {renderedParts}
          </div>
        )
      })}
    </div>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function EggAIChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: uid(),
      role: 'assistant',
      text:
        '👋 Hello! I am your KR Poultry Farm & Evidence AI Assistant.\n\nFeel free to ask me anything about our live farm data, counts, and reports:\n• "What is today\'s egg and tray count?"\n• "What is today\'s total hen count?"\n• "Who uploaded suspicious evidence?"\n• "Show me the 27 Nov egg and tray report"\n• "Give me the complete farm summary report"\n\nYou can also upload or capture egg tray or hen photos, and I will detect and count them live for you! 🥚🐔📊',
    },
  ])

  // The currently attached image — persists across messages in the same session
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const [attachedPreview, setAttachedPreview] = useState<string | null>(null)
  // The last image sent — re-used for follow-up questions
  const [sessionImageFile, setSessionImageFile] = useState<File | null>(null)

  const [inputText, setInputText] = useState('')
  const [sending, setSending] = useState(false)

  // Chat History Drawer State
  const [showHistory, setShowHistory] = useState(false)
  const [dailyHistory, setDailyHistory] = useState<DailyChatSummary[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Fetch daily chat history from database
  const fetchChatHistory = async () => {
    try {
      setLoadingHistory(true)
      const res = await aiApi.getChatHistoryDaily()
      if (Array.isArray(res.data)) {
        setDailyHistory(res.data)
      }
    } catch (err) {
      console.error('Error fetching chat history:', err)
    } finally {
      setLoadingHistory(false)
    }
  }

  useEffect(() => {
    fetchChatHistory()
  }, [])

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleAttach = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setAttachedFile(file)
    setAttachedPreview(URL.createObjectURL(file))
    // Reset the input so the same file can be re-selected
    e.target.value = ''
  }

  const removeAttachment = () => {
    setAttachedFile(null)
    setAttachedPreview(null)
  }

  const clearSession = () => {
    setSessionImageFile(null)
    setAttachedFile(null)
    setAttachedPreview(null)
    setMessages([
      {
        id: uid(),
        role: 'assistant',
        text: '🔄 Session cleared. Upload a new image or ask a question to start fresh.',
      },
    ])
  }

  const handleDeleteHistoryItem = async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    try {
      await aiApi.deleteChatHistory(id)
      setDailyHistory((prev) =>
        prev
          .map((d) => ({
            ...d,
            conversations: d.conversations.filter((c) => c.id !== id),
            total_messages: d.conversations.filter((c) => c.id !== id).length,
          }))
          .filter((d) => d.total_messages > 0)
      )
    } catch (err) {
      console.error('Failed to delete history item:', err)
    }
  }

  const handleClearAllHistory = async () => {
    if (!window.confirm('Are you sure you want to clear all saved chat history?')) return
    try {
      await aiApi.clearChatHistory()
      setDailyHistory([])
    } catch (err) {
      console.error('Failed to clear chat history:', err)
    }
  }

  const handleLoadConversation = (conv: HistoryConversation) => {
    setMessages((prev) => [
      ...prev,
      {
        id: uid(),
        role: 'user',
        text: conv.user_message,
      },
      {
        id: uid(),
        role: 'assistant',
        text: conv.assistant_reply,
      },
    ])
    setShowHistory(false)
  }

  const sendCustomPrompt = async (textToSend: string) => {
    const text = textToSend.trim()
    if (!text && !attachedFile) return

    // Determine which image to use: newly attached > session image > none
    const imageToSend = attachedFile || sessionImageFile

    // Build user message
    const userMsg: ChatMessage = {
      id: uid(),
      role: 'user',
      text: text || '(image attached)',
      imagePreview: attachedPreview || undefined,
    }

    // Placeholder for assistant reply
    const loadingMsg: ChatMessage = {
      id: uid(),
      role: 'assistant',
      text: '',
      loading: true,
    }

    setMessages((prev) => [...prev, userMsg, loadingMsg])
    setInputText('')
    setSending(true)

    // Save image to session state
    if (attachedFile) {
      setSessionImageFile(attachedFile)
    }
    setAttachedFile(null)
    setAttachedPreview(null)

    try {
      const formData = new FormData()
      formData.append('message', text || 'Please analyze this image.')
      if (imageToSend) {
        formData.append('image', imageToSend)
      }

      const response = await aiApi.chatAnalyze(formData)
      const { reply, analysis } = response.data

      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingMsg.id
            ? { ...m, text: reply, analysis: analysis || undefined, loading: false }
            : m
        )
      )

      // Refresh chat history in background so today's history is up to date
      fetchChatHistory()
    } catch (err: any) {
      const detail =
        err.response?.data?.detail ||
        'Unable to process your request. Please try again.'

      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingMsg.id
            ? {
                ...m,
                text: `❌ ${detail}`,
                loading: false,
              }
            : m
        )
      )
    } finally {
      setSending(false)
    }
  }

  const handleSend = () => {
    sendCustomPrompt(inputText)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="page-container page-with-bg" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 80px)', position: 'relative' }}>
      {/* ─── Header ──────────────────────────────────────────────────── */}
      <header className="page-header" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1 }}>
          <div className="page-icon-wrapper" style={{ background: 'var(--brand-500)' }}>
            <Bot size={20} color="white" />
          </div>
          <div>
            <h1 className="page-title">AI Vision Chat</h1>
            <p className="page-subtitle">
              Ask questions about daily egg counts, hen flock tracking, suspicious evidence, date-wise reports, or upload photos!
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* History Button */}
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setShowHistory(true)
              fetchChatHistory()
            }}
            title="View saved day-by-day chat history"
            style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600 }}
          >
            <History size={15} color="var(--brand-400, #38bdf8)" />
            <span>Chat History</span>
            {dailyHistory.length > 0 && (
              <span
                style={{
                  background: 'var(--brand-500)',
                  color: 'white',
                  borderRadius: 10,
                  padding: '1px 6px',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                }}
              >
                {dailyHistory.reduce((acc, d) => acc + d.total_messages, 0)}
              </span>
            )}
          </button>

          {sessionImageFile && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '4px 10px',
                background: 'rgba(59,130,246,0.12)',
                borderRadius: 6,
                fontSize: '0.78rem',
                color: 'var(--brand-400)',
                border: '1px solid rgba(59,130,246,0.25)',
              }}
            >
              <ImageIcon size={12} />
              Image loaded
            </div>
          )}
          <button
            className="btn btn-secondary btn-sm"
            onClick={clearSession}
            title="Clear current screen messages"
          >
            Clear Screen
          </button>
        </div>
      </header>

      {/* ─── Chat Messages ───────────────────────────────────────────── */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '8px 0 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
            }}
          >
            {/* Avatar */}
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: '50%',
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background:
                  msg.role === 'assistant'
                    ? 'linear-gradient(135deg, var(--brand-500), var(--brand-700))'
                    : 'var(--bg-elevated)',
                border: msg.role === 'user' ? '1px solid var(--border-subtle)' : 'none',
              }}
            >
              {msg.role === 'assistant' ? (
                <Bot size={18} color="white" />
              ) : (
                <UserIcon size={18} color="var(--text-secondary)" />
              )}
            </div>

            {/* Bubble */}
            <div
              style={{
                maxWidth: '75%',
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
                alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}
            >
              {/* User image attachment preview */}
              {msg.imagePreview && (
                <img
                  src={msg.imagePreview}
                  alt="Attached"
                  style={{
                    maxWidth: 200,
                    maxHeight: 160,
                    objectFit: 'cover',
                    borderRadius: 10,
                    border: '1px solid var(--border-subtle)',
                  }}
                />
              )}

              {/* Message text bubble */}
              <div
                style={{
                  padding: '12px 16px',
                  borderRadius:
                    msg.role === 'user'
                      ? '16px 16px 4px 16px'
                      : '16px 16px 16px 4px',
                  background:
                    msg.role === 'user'
                      ? 'var(--brand-500)'
                      : 'var(--bg-elevated)',
                  color: msg.role === 'user' ? '#fff' : 'var(--text-primary)',
                  border:
                    msg.role === 'assistant'
                      ? '1px solid var(--border-subtle)'
                      : 'none',
                  fontSize: '0.9rem',
                  lineHeight: 1.6,
                  wordBreak: 'break-word',
                  minWidth: 60,
                }}
              >
                {msg.loading ? (
                  <span
                    style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}
                  >
                    <Loader size={14} className="spinner" />
                    Analyzing…
                  </span>
                ) : (
                  renderFormattedMessage(msg.text, msg.role === 'user')
                )}
              </div>

              {/* Structured analysis panel (assistant only) */}
              {msg.analysis && !msg.loading && (
                <div
                  style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 12,
                    padding: 14,
                    width: '100%',
                    maxWidth: 340,
                  }}
                >
                  <div
                    style={{
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      color: 'var(--text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.6px',
                      marginBottom: 10,
                    }}
                  >
                    AI Analysis Result
                  </div>

                  {/* Egg count / Tray count stat cards */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
                    <div
                      style={{
                        background: 'rgba(59,130,246,0.1)',
                        border: '1px solid rgba(59,130,246,0.2)',
                        borderRadius: 8,
                        padding: '8px 12px',
                        textAlign: 'center',
                      }}
                    >
                      <div style={{ fontSize: '0.7rem', color: 'var(--brand-400)', fontWeight: 600, marginBottom: 2 }}>
                        EGGS
                      </div>
                      <div style={{ fontSize: '1.6rem', fontWeight: 'bold', color: 'var(--text-primary)', lineHeight: 1 }}>
                        {msg.analysis.egg_count}
                      </div>
                    </div>

                    <div
                      style={{
                        background: 'rgba(16,185,129,0.1)',
                        border: '1px solid rgba(16,185,129,0.2)',
                        borderRadius: 8,
                        padding: '8px 12px',
                        textAlign: 'center',
                      }}
                    >
                      <div style={{ fontSize: '0.7rem', color: '#10b981', fontWeight: 600, marginBottom: 2 }}>
                        TRAYS
                      </div>
                      <div style={{ fontSize: '1.6rem', fontWeight: 'bold', color: 'var(--text-primary)', lineHeight: 1 }}>
                        {msg.analysis.tray_count}
                      </div>
                    </div>
                  </div>

                  {/* Tray types */}
                  {msg.analysis.tray_count > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      {[
                        { label: '🟢 Green Plastic', key: 'green_plastic' },
                        { label: '📦 Paper/Cardboard', key: 'paper_cardboard' },
                        { label: '🔵 Other', key: 'other' },
                        { label: '❓ Unknown', key: 'unknown' },
                      ].map(({ label, key }) => {
                        const count = msg.analysis!.tray_types[key as keyof TrayTypes]
                        if (count === 0) return null
                        return (
                          <div
                            key={key}
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              fontSize: '0.8rem',
                              padding: '3px 0',
                              color: 'var(--text-secondary)',
                            }}
                          >
                            <span>{label}</span>
                            <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{count}</span>
                          </div>
                        )
                      })}
                    </div>
                  )}

                  {/* Confidence badge */}
                  <span
                    style={{
                      background: `${confidenceColor(msg.analysis.confidence)}20`,
                      color: confidenceColor(msg.analysis.confidence),
                      border: `1px solid ${confidenceColor(msg.analysis.confidence)}40`,
                      borderRadius: 5,
                      padding: '3px 8px',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                    }}
                  >
                    Confidence: {cap(msg.analysis.confidence)}
                  </span>

                  {/* Notes */}
                  {msg.analysis.notes && (
                    <div
                      style={{
                        marginTop: 8,
                        fontSize: '0.78rem',
                        color: 'var(--text-muted)',
                        lineHeight: 1.5,
                        borderLeft: '2px solid var(--brand-500)',
                        paddingLeft: 8,
                      }}
                    >
                      {msg.analysis.notes}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* ─── Input area ──────────────────────────────────────────────── */}
      <div
        style={{
          flexShrink: 0,
          borderTop: '1px solid var(--border-subtle)',
          paddingTop: 14,
        }}
      >
        {/* Quick prompt suggestions */}
        <div
          style={{
            display: 'flex',
            gap: 8,
            overflowX: 'auto',
            paddingBottom: 10,
            scrollbarWidth: 'none',
            msOverflowStyle: 'none',
          }}
        >
          {[
            { label: '🥚 Today Egg Count', query: "What is today's total egg and tray count?" },
            { label: '🐔 Today Hen Count', query: "What is today's hen tracking count?" },
            { label: '⚠️ Suspicious Evidence', query: 'Who uploaded suspicious evidence images and what was flagged?' },
            { label: '📊 All Reports Summary', query: 'Give me a complete farm report summary' },
            { label: '📅 27 Nov Report', query: 'What was the egg and hen count on 27 Nov?' },
          ].map((chip) => (
            <button
              key={chip.label}
              type="button"
              disabled={sending}
              onClick={() => sendCustomPrompt(chip.query)}
              style={{
                whiteSpace: 'nowrap',
                padding: '6px 14px',
                borderRadius: 20,
                border: '1px solid var(--border-subtle, rgba(255,255,255,0.15))',
                background: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.2s',
                flexShrink: 0,
              }}
            >
              {chip.label}
            </button>
          ))}
        </div>

        {/* Attachment preview bar */}
        {attachedPreview && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '6px 12px',
              background: 'var(--bg-elevated)',
              borderRadius: 8,
              marginBottom: 8,
              border: '1px solid var(--border-subtle)',
              width: 'fit-content',
            }}
          >
            <img
              src={attachedPreview}
              alt="Preview"
              style={{ width: 36, height: 36, objectFit: 'cover', borderRadius: 4 }}
            />
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              {attachedFile?.name}
            </span>
            <button
              type="button"
              onClick={removeAttachment}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--text-muted)',
                display: 'flex',
                alignItems: 'center',
                padding: 2,
              }}
            >
              <X size={14} />
            </button>
          </div>
        )}

        {/* Textbox + action buttons */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          {/* File attach button */}
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={sending}
            title="Attach an image from files"
            style={{ padding: '10px 12px', flexShrink: 0 }}
          >
            <Paperclip size={18} />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/jpg"
            onChange={handleAttach}
            style={{ display: 'none' }}
          />

          {/* Camera capture button (mobile) */}
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => cameraInputRef.current?.click()}
            disabled={sending}
            title="Take a photo with camera"
            style={{ padding: '10px 12px', flexShrink: 0 }}
          >
            <Camera size={18} />
          </button>
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleAttach}
            style={{ display: 'none' }}
          />

          {/* Text input */}
          <textarea
            ref={textareaRef}
            id="chat-message-input"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              sessionImageFile || attachedFile
                ? 'Ask about the image… (Enter to send)'
                : 'Ask anything about eggs, hens, reports, or attach an image…'
            }
            disabled={sending}
            rows={1}
            style={{
              flex: 1,
              resize: 'none',
              borderRadius: 10,
              border: '1px solid var(--border-color)',
              background: 'var(--bg-elevated)',
              color: 'var(--text-primary)',
              padding: '10px 14px',
              fontSize: '0.9rem',
              outline: 'none',
              lineHeight: 1.5,
              minHeight: 42,
              maxHeight: 120,
              overflowY: 'auto',
            }}
          />

          {/* Send button */}
          <button
            id="chat-send-button"
            className="btn btn-primary"
            onClick={handleSend}
            disabled={sending || (!inputText.trim() && !attachedFile)}
            style={{ padding: '10px 16px', flexShrink: 0 }}
            title="Send message"
          >
            {sending ? <Loader size={16} className="spinner" /> : <Send size={16} />}
          </button>
        </div>
      </div>

      {/* ─── Chat History Drawer (Day-by-Day Saved Queries) ───────────── */}
      {showHistory && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            zIndex: 999,
            display: 'flex',
            justifyContent: 'flex-end',
            background: 'rgba(0, 0, 0, 0.65)',
            backdropFilter: 'blur(3px)',
          }}
          onClick={() => setShowHistory(false)}
        >
          <div
            style={{
              width: 'min(500px, 94vw)',
              height: '100%',
              background: 'var(--bg-surface, #0f172a)',
              borderLeft: '1px solid var(--border-subtle, rgba(255,255,255,0.1))',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '-8px 0 32px rgba(0,0,0,0.5)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Drawer Header */}
            <div
              style={{
                padding: '18px 20px',
                borderBottom: '1px solid var(--border-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: 'var(--bg-elevated, #1e293b)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <History size={20} color="var(--brand-400, #38bdf8)" />
                <div>
                  <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    AI Chat History
                  </h3>
                  <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Saved questions & reports day-by-day
                  </p>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button
                  type="button"
                  onClick={fetchChatHistory}
                  disabled={loadingHistory}
                  title="Refresh history"
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--text-secondary)',
                    padding: 6,
                    borderRadius: 6,
                  }}
                >
                  <RefreshCw size={16} className={loadingHistory ? 'spinner' : ''} />
                </button>
                {dailyHistory.length > 0 && (
                  <button
                    type="button"
                    onClick={handleClearAllHistory}
                    title="Clear all chat history"
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: '#ef4444',
                      padding: 6,
                      borderRadius: 6,
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowHistory(false)}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--text-primary)',
                    padding: 6,
                    borderRadius: 6,
                  }}
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* Drawer Body: Day-by-Day List */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 18 }}>
              {dailyHistory.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '50px 20px', color: 'var(--text-muted)' }}>
                  <MessageSquare size={44} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
                  <div style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>
                    No Saved History Yet
                  </div>
                  <div style={{ fontSize: '0.85rem' }}>
                    Ask questions or request farm counts in the chat, and your queries will be automatically saved here grouped by date!
                  </div>
                </div>
              ) : (
                dailyHistory.map((day) => (
                  <div
                    key={day.date}
                    style={{
                      background: 'var(--bg-elevated, #1e293b)',
                      borderRadius: 12,
                      border: '1px solid var(--border-subtle)',
                      overflow: 'hidden',
                    }}
                  >
                    {/* Day Date Header */}
                    <div
                      style={{
                        padding: '10px 14px',
                        background: 'rgba(59,130,246,0.08)',
                        borderBottom: '1px solid var(--border-subtle)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.85rem', fontWeight: 700, color: 'var(--brand-400)' }}>
                        <Calendar size={14} />
                        <span>{day.formatted_date}</span>
                      </div>
                      <span
                        style={{
                          fontSize: '0.72rem',
                          background: 'rgba(255,255,255,0.1)',
                          padding: '2px 8px',
                          borderRadius: 10,
                          color: 'var(--text-secondary)',
                          fontWeight: 600,
                        }}
                      >
                        {day.total_messages} query(ies)
                      </span>
                    </div>

                    {/* Conversations under this day */}
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      {day.conversations.map((conv) => (
                        <div
                          key={conv.id}
                          style={{
                            padding: '12px 14px',
                            borderBottom: '1px solid var(--border-subtle)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 8,
                          }}
                        >
                          {/* Top row: Time + Delete */}
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                              <Clock size={12} />
                              <span>{conv.time}</span>
                              {conv.has_image && (
                                <span
                                  style={{
                                    background: 'rgba(59,130,246,0.15)',
                                    color: 'var(--brand-400)',
                                    borderRadius: 4,
                                    padding: '1px 5px',
                                    fontSize: '0.68rem',
                                  }}
                                >
                                  📷 Image
                                </span>
                              )}
                            </div>

                            <button
                              type="button"
                              onClick={(e) => handleDeleteHistoryItem(conv.id, e)}
                              title="Delete this query from history"
                              style={{
                                background: 'none',
                                border: 'none',
                                cursor: 'pointer',
                                color: 'var(--text-muted)',
                                padding: 2,
                              }}
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>

                          {/* Question */}
                          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', gap: 6 }}>
                            <span style={{ color: 'var(--brand-400)' }}>Q:</span>
                            <span>{conv.user_message}</span>
                          </div>

                          {/* Answer Snippet */}
                          <div
                            style={{
                              fontSize: '0.8rem',
                              color: 'var(--text-secondary)',
                              background: 'var(--bg-surface, #0f172a)',
                              padding: '8px 10px',
                              borderRadius: 8,
                              maxHeight: 140,
                              overflowY: 'auto',
                              lineHeight: 1.5,
                            }}
                          >
                            {renderFormattedMessage(conv.assistant_reply)}
                          </div>

                          {/* Load into Chat action */}
                          <button
                            type="button"
                            onClick={() => handleLoadConversation(conv)}
                            style={{
                              alignSelf: 'flex-start',
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              color: 'var(--brand-400)',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              padding: '2px 0',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 4,
                            }}
                          >
                            <Sparkles size={12} />
                            Load into chat view
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
