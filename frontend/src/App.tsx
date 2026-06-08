import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Bot, Send, Upload, Database, Wrench, Activity, ChevronDown,
  ChevronRight, FileText, Zap, Shield, Check, X, Loader2,
  Github, MessageSquare, Search, BarChart2, AlertTriangle
} from 'lucide-react'
import { chatRequest, getHealth, getRAGStats, ingestFile, listTools, runTool, ingestText } from './utils/api'

// ─── Types ──────────────────────────────────────────────────────────────────

type Mode = 'auto' | 'rag' | 'agent' | 'chat'

interface AgentStep {
  agent: string
  status: string
  output: string
  duration_ms: number
}

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  mode?: string
  sources?: string[]
  steps?: AgentStep[]
  grounded?: boolean
  relevance_score?: number
  duration_ms?: number
  error?: boolean
  timestamp: number
}

interface HealthData {
  status: string
  providers: string[]
  knowledge_base: { chunks: number; sources: number }
  token_usage: { total_tokens: number; total_requests: number }
}

// ─── Styles ─────────────────────────────────────────────────────────────────

const S: Record<string, React.CSSProperties> = {
  app: {
    display: 'grid',
    gridTemplateColumns: '240px 1fr 280px',
    gridTemplateRows: '48px 1fr',
    height: '100vh',
    background: 'var(--bg)',
    overflow: 'hidden',
  },
  topbar: {
    gridColumn: '1 / -1',
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '0 20px',
    background: 'var(--bg-panel)',
    borderBottom: '1px solid var(--border)',
    zIndex: 10,
  },
  sidebar: {
    background: 'var(--bg-panel)',
    borderRight: '1px solid var(--border)',
    padding: '16px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    overflowY: 'auto',
  },
  main: {
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  rightPanel: {
    background: 'var(--bg-panel)',
    borderLeft: '1px solid var(--border)',
    padding: 16,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
  messages: {
    flex: 1,
    overflowY: 'auto',
    padding: '20px 24px',
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
  inputRow: {
    padding: '12px 20px',
    borderTop: '1px solid var(--border)',
    background: 'var(--bg-panel)',
    display: 'flex',
    gap: 10,
    alignItems: 'flex-end',
  },
}

// ─── Small Components ────────────────────────────────────────────────────────

function Badge({ label, color = 'var(--text-dim)', bg = 'var(--bg-card)' }: { label: string; color?: string; bg?: string }) {
  return (
    <span style={{
      fontSize: 10, fontFamily: 'var(--font-mono)', padding: '2px 6px',
      borderRadius: 4, background: bg, color, fontWeight: 600, textTransform: 'uppercase',
    }}>
      {label}
    </span>
  )
}

function StatusDot({ ok }: { ok: boolean }) {
  return <span style={{ width: 7, height: 7, borderRadius: '50%', background: ok ? 'var(--green)' : 'var(--red)', display: 'inline-block' }} />
}

function NavBtn({ icon: Icon, label, active, onClick }: { icon: React.ElementType; label: string; active?: boolean; onClick?: () => void }) {
  return (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px',
      borderRadius: 6, background: active ? 'var(--accent-glow)' : 'transparent',
      border: active ? '1px solid var(--accent-dim)' : '1px solid transparent',
      color: active ? 'var(--accent)' : 'var(--text-dim)', cursor: 'pointer', width: '100%', textAlign: 'left',
      fontSize: 13, transition: 'all 0.15s',
    }}>
      <Icon size={14} /> {label}
    </button>
  )
}

function SectionLabel({ label }: { label: string }) {
  return (
    <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', padding: '10px 10px 4px', }}>
      {label}
    </div>
  )
}

// ─── Agent Steps Viewer ──────────────────────────────────────────────────────

function AgentStepsViewer({ steps }: { steps: AgentStep[] }) {
  const [openIdx, setOpenIdx] = useState<number | null>(null)
  const colors: Record<string, string> = {
    Planner: 'var(--purple)', Research: 'var(--accent)', Analysis: 'var(--amber)',
    QA: 'var(--green)', Summary: 'var(--red)',
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, margin: '10px 0' }}>
      <div style={{ fontSize: 11, color: 'var(--text-dim)', fontWeight: 600, marginBottom: 4 }}>AGENT PIPELINE</div>
      {steps.map((step, i) => (
        <div key={i} style={{
          background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden',
          borderLeft: `3px solid ${colors[step.agent] || 'var(--border-bright)'}`,
        }}>
          <button
            onClick={() => setOpenIdx(openIdx === i ? null : i)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', width: '100%',
              background: 'transparent', border: 'none', color: 'var(--text)', cursor: 'pointer',
            }}
          >
            {openIdx === i ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            <span style={{ fontWeight: 600, color: colors[step.agent] || 'var(--text)' }}>{step.agent}</span>
            <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-dim)' }}>{step.duration_ms}ms</span>
            {step.status === 'done' ? <Check size={11} color="var(--green)" /> : <X size={11} color="var(--red)" />}
          </button>
          {openIdx === i && (
            <div style={{ padding: '0 12px 12px', fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', maxHeight: 200, overflowY: 'auto' }}>
              {step.output || '(no output)'}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ─── Message Bubble ──────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user'
  const modeColors: Record<string, string> = {
    agent: 'var(--purple)', rag: 'var(--green)', chat: 'var(--accent)',
  }

  return (
    <div style={{
      display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', gap: 10,
      animation: 'fadeIn 0.2s ease',
    }}>
      <div style={{
        width: 28, height: 28, borderRadius: 6, flexShrink: 0, marginTop: 2,
        background: isUser ? 'var(--accent-dim)' : 'var(--bg-card)',
        border: '1px solid var(--border-bright)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {isUser ? <span style={{ fontSize: 12 }}>U</span> : <Bot size={13} color="var(--accent)" />}
      </div>

      <div style={{ maxWidth: '72%', display: 'flex', flexDirection: 'column', gap: 6, alignItems: isUser ? 'flex-end' : 'flex-start' }}>
        {msg.mode && (
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <Badge label={msg.mode} color={modeColors[msg.mode] || 'var(--text-dim)'} />
            {msg.grounded === false && <Badge label="LOW CONTEXT" color="var(--amber)" bg="var(--amber-dim)" />}
            {msg.relevance_score !== undefined && (
              <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                relevance: {msg.relevance_score.toFixed(2)}
              </span>
            )}
          </div>
        )}

        <div style={{
          background: isUser ? 'var(--accent-dim)' : 'var(--bg-card)',
          border: `1px solid ${msg.error ? 'var(--red-dim)' : 'var(--border)'}`,
          borderRadius: isUser ? '12px 4px 12px 12px' : '4px 12px 12px 12px',
          padding: '10px 14px',
          color: msg.error ? 'var(--red)' : 'var(--text)',
        }}>
          {isUser ? (
            <p style={{ fontSize: 14 }}>{msg.content}</p>
          ) : (
            <div className="markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
          )}
        </div>

        {msg.steps && msg.steps.length > 0 && <AgentStepsViewer steps={msg.steps} />}

        {msg.sources && msg.sources.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Sources:</span>
            {msg.sources.map((s, i) => (
              <Badge key={i} label={s} color="var(--accent)" bg="var(--accent-dim)" />
            ))}
          </div>
        )}

        {msg.duration_ms && (
          <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
            {msg.duration_ms}ms
          </span>
        )}
      </div>
    </div>
  )
}

// Very simple markdown renderer (no deps needed)
function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[hupol]|<li|<pre|<block)(.+)$/gm, '<p>$1</p>')
}

// ─── Right Panel ─────────────────────────────────────────────────────────────

function RightPanel({ health, ragStats, onIngestFile }: {
  health: HealthData | null
  ragStats: { total_chunks: number; sources: string[] } | null
  onIngestFile: (f: File) => void
}) {
  const fileRef = useRef<HTMLInputElement>(null)

  return (
    <>
      {/* System Status */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 10 }}>System Status</div>
        {health ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {health.providers.map(p => (
              <div key={p} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                <StatusDot ok={true} />
                <span style={{ color: 'var(--text-muted)', textTransform: 'capitalize' }}>{p}</span>
              </div>
            ))}
            {health.providers.length === 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                <StatusDot ok={false} />
                <span style={{ color: 'var(--amber)' }}>No providers (mock mode)</span>
              </div>
            )}
          </div>
        ) : (
          <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>Connecting...</div>
        )}
      </div>

      {/* Knowledge Base */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 10 }}>Knowledge Base</div>
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6, padding: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 8 }}>
            <span style={{ color: 'var(--text-dim)' }}>Chunks</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{ragStats?.total_chunks ?? '—'}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
            <span style={{ color: 'var(--text-dim)' }}>Documents</span>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{ragStats?.sources.length ?? '—'}</span>
          </div>
        </div>

        <button
          onClick={() => fileRef.current?.click()}
          style={{
            marginTop: 8, width: '100%', padding: '8px 12px', borderRadius: 6,
            background: 'transparent', border: '1px dashed var(--border-bright)',
            color: 'var(--text-dim)', cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center',
          }}
        >
          <Upload size={13} /> Upload Document
        </button>
        <input ref={fileRef} type="file" accept=".pdf,.md,.txt,.html" style={{ display: 'none' }}
          onChange={e => { const f = e.target.files?.[0]; if (f) onIngestFile(f); e.target.value = '' }} />
      </div>

      {/* Token Usage */}
      {health?.token_usage && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 10 }}>Token Usage</div>
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6, padding: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 6 }}>
              <span style={{ color: 'var(--text-dim)' }}>Total Tokens</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                {health.token_usage.total_tokens.toLocaleString()}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: 'var(--text-dim)' }}>Requests</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{health.token_usage.total_requests}</span>
            </div>
          </div>
        </div>
      )}

      {/* Security Indicators */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 10 }}>Security</div>
        {[
          { label: 'Prompt Injection Guard', ok: true },
          { label: 'Input Sanitization', ok: true },
          { label: 'Tool Sandboxing', ok: true },
          { label: 'Secret Scrubbing', ok: true },
        ].map(item => (
          <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, marginBottom: 6 }}>
            <Check size={12} color="var(--green)" />
            <span style={{ color: 'var(--text-dim)' }}>{item.label}</span>
          </div>
        ))}
      </div>
    </>
  )
}

// ─── Sample Prompts ──────────────────────────────────────────────────────────

const SAMPLE_PROMPTS = [
  { label: 'Auth Issues', query: 'Find all authentication-related GitHub issues opened in the last 30 days and summarize recurring failures.', mode: 'agent' as Mode },
  { label: 'Login Analysis', query: 'Analyze our failing login flow and suggest possible fixes.', mode: 'agent' as Mode },
  { label: 'JWT Docs', query: 'What is our authentication flow and how do JWT tokens expire?', mode: 'rag' as Mode },
  { label: 'Rate Limits', query: 'What are our API rate limiting rules?', mode: 'rag' as Mode },
  { label: 'Incident Search', query: 'Find recent Slack messages about auth service outages and incidents.', mode: 'agent' as Mode },
]

// ─── Main App ────────────────────────────────────────────────────────────────

type Tab = 'chat' | 'tools' | 'observe'

export default function App() {
  const [messages, setMessages] = useState<Message[]>([{
    id: 'welcome',
    role: 'assistant',
    content: `## Engineering AI Assistant Ready

I can help you:
- **Answer questions** from your internal documentation (RAG mode)
- **Investigate issues** by querying GitHub, Slack, and databases (Agent mode)
- **Analyze** root causes and generate engineering recommendations

Try one of the sample prompts on the left, or type your question below.`,
    timestamp: Date.now(),
  }])
  const [input, setInput] = useState('')
  const [mode, setMode] = useState<Mode>('auto')
  const [loading, setLoading] = useState(false)
  const [health, setHealth] = useState<HealthData | null>(null)
  const [ragStats, setRagStats] = useState<{ total_chunks: number; sources: string[] } | null>(null)
  const [tab, setTab] = useState<Tab>('chat')
  type Tool = {
  name: string
  description: string
}
  const [tools, setTools] = useState<Tool[]>([])
  const [toolResult, setToolResult] = useState<unknown>(null)
  const [ingestStatus, setIngestStatus] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    getHealth().then(setHealth).catch(console.error)
    getRAGStats().then(setRagStats).catch(console.error)
    listTools().then(setTools).catch(console.error)
    const interval = setInterval(() => {
      getHealth().then(setHealth).catch(() => {})
      getRAGStats().then(setRagStats).catch(() => {})
    }, 15000)
    return () => clearInterval(interval)
  }, [])

  const sendMessage = useCallback(async (text?: string, overrideMode?: Mode) => {
    const query = text || input.trim()
    if (!query || loading) return
    setInput('')
    setLoading(true)

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: query, timestamp: Date.now() }
    setMessages(prev => [...prev, userMsg])

    try {
      const data = await chatRequest(query, overrideMode || mode)
      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.answer || data.content || '',
        mode: data.mode,
        sources: data.sources,
        steps: data.steps,
        grounded: data.grounded,
        relevance_score: data.relevance_score,
        duration_ms: data.duration_ms,
        timestamp: Date.now(),
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err: unknown) {
      const error = err instanceof Error ? err.message : 'Unknown error'
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Error: ${error}. Make sure the backend is running on port 8000.`,
        error: true,
        timestamp: Date.now(),
      }])
    } finally {
      setLoading(false)
      getHealth().then(setHealth).catch(() => {})
      getRAGStats().then(setRagStats).catch(() => {})
    }
  }, [input, loading, mode])

  const handleIngestFile = async (file: File) => {
    setIngestStatus(`Ingesting ${file.name}...`)
    try {
      const result = await ingestFile(file)
      setIngestStatus(`✓ ${file.name}: ${result.chunks_created} chunks`)
      getRAGStats().then(setRagStats).catch(() => {})
    } catch {
      setIngestStatus(`✗ Failed to ingest ${file.name}`)
    }
    setTimeout(() => setIngestStatus(''), 4000)
  }

  return (
    <div style={S.app}>
      {/* Topbar */}
      <div style={S.topbar}>
        <Bot size={18} color="var(--accent)" />
        <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: '-0.02em' }}>Engineering AI</span>
        <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>Intelligence Assistant</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <StatusDot ok={!!health} />
          <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{health ? 'Backend connected' : 'Connecting...'}</span>
          {ingestStatus && <Badge label={ingestStatus} color="var(--green)" bg="var(--green-dim)" />}
        </div>
      </div>

      {/* Sidebar */}
      <div style={S.sidebar}>
        <SectionLabel label="Navigation" />
        <NavBtn icon={MessageSquare} label="Chat" active={tab === 'chat'} onClick={() => setTab('chat')} />
        <NavBtn icon={Wrench} label="Tools" active={tab === 'tools'} onClick={() => setTab('tools')} />
        <NavBtn icon={Activity} label="Observability" active={tab === 'observe'} onClick={() => setTab('observe')} />

        <SectionLabel label="Mode" />
        {(['auto', 'rag', 'agent', 'chat'] as Mode[]).map(m => (
          <NavBtn key={m} icon={
            m === 'auto' ? Zap : m === 'rag' ? Search : m === 'agent' ? Bot : MessageSquare
          } label={m === 'auto' ? 'Auto Detect' : m === 'rag' ? 'RAG Only' : m === 'agent' ? 'Agent Mode' : 'Direct Chat'} active={mode === m} onClick={() => setMode(m)} />
        ))}

        <SectionLabel label="Quick Prompts" />
        {SAMPLE_PROMPTS.map((p, i) => (
          <button key={i} onClick={() => sendMessage(p.query, p.mode)}
            style={{
              textAlign: 'left', padding: '7px 10px', borderRadius: 6,
              background: 'transparent', border: '1px solid var(--border)',
              color: 'var(--text-dim)', cursor: 'pointer', fontSize: 12, lineHeight: 1.4,
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => { (e.target as HTMLElement).style.borderColor = 'var(--accent)'; (e.target as HTMLElement).style.color = 'var(--text)' }}
            onMouseLeave={e => { (e.target as HTMLElement).style.borderColor = 'var(--border)'; (e.target as HTMLElement).style.color = 'var(--text-dim)' }}
          >
            <Badge label={p.mode} color={p.mode === 'agent' ? 'var(--purple)' : 'var(--green)'} />
            <span style={{ display: 'block', marginTop: 4 }}>{p.label}</span>
          </button>
        ))}
      </div>

      {/* Main content */}
      <div style={S.main}>
        {tab === 'chat' && (
          <>
            <div style={S.messages}>
              {messages.map(m => <MessageBubble key={m.id} msg={m} />)}
              {loading && (
                <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', animation: 'fadeIn 0.2s' }}>
                  <div style={{ width: 28, height: 28, borderRadius: 6, background: 'var(--bg-card)', border: '1px solid var(--border-bright)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Loader2 size={13} color="var(--accent)" style={{ animation: 'spin 1s linear infinite' }} />
                  </div>
                  <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '4px 12px 12px 12px', padding: '10px 14px', color: 'var(--text-dim)', fontSize: 13 }}>
                    {mode === 'agent' || mode === 'auto' ? 'Running agent pipeline...' : 'Thinking...'}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <div style={S.inputRow}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <Badge label={mode} color={mode === 'agent' ? 'var(--purple)' : mode === 'rag' ? 'var(--green)' : 'var(--accent)'} />
              </div>
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
                placeholder="Ask an engineering question... (Enter to send, Shift+Enter for newline)"
                style={{
                  flex: 1, background: 'var(--bg-card)', border: '1px solid var(--border-bright)',
                  borderRadius: 8, padding: '10px 14px', color: 'var(--text)', resize: 'none',
                  fontFamily: 'var(--font-sans)', fontSize: 14, outline: 'none', minHeight: 44, maxHeight: 120,
                }}
              />
              <button
                onClick={() => sendMessage()}
                disabled={!input.trim() || loading}
                style={{
                  padding: '10px 16px', borderRadius: 8, background: 'var(--accent)',
                  border: 'none', cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.6 : 1,
                  display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-sans)',
                  fontSize: 13, fontWeight: 600, color: '#fff',
                }}
              >
                <Send size={14} /> Send
              </button>
            </div>
          </>
        )}

        {tab === 'tools' && <ToolsPanel tools={tools} onRun={(name, params) => runTool(name, params).then(setToolResult)} result={toolResult} />}
        {tab === 'observe' && <ObservabilityPanel health={health} />}
      </div>

      {/* Right panel */}
      <div style={S.rightPanel}>
        <RightPanel health={health} ragStats={ragStats} onIngestFile={handleIngestFile} />
      </div>
    </div>
  )
}

// ─── Tools Panel ─────────────────────────────────────────────────────────────
function ToolsPanel({
  tools,
  onRun,
  result
}: {
  tools: Tool[]
  onRun: (name: string, params: Record<string, unknown>) => Promise<unknown>
  result: unknown
}){
  const [selected, setSelected] = useState<string>('github')
  const [params, setParams] = useState('{\n  "action": "search_issues",\n  "query": "authentication",\n  "days": 30\n}')
  const [running, setRunning] = useState(false)

  const run = async () => {
    setRunning(true)
    try {
      const p = JSON.parse(params)
      await onRun(selected, p)
    } catch (e) {
      console.error(e)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div style={{ padding: 24, flex: 1, overflowY: 'auto' }}>
      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Tool Registry</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {tools.map((t) => (
            <button key={t.name} onClick={() => setSelected(t.name)}
              style={{
                padding: '10px 12px', borderRadius: 8, textAlign: 'left', cursor: 'pointer',
                background: selected === t.name ? 'var(--accent-glow)' : 'var(--bg-card)',
                border: `1px solid ${selected === t.name ? 'var(--accent-dim)' : 'var(--border)'}`,
                color: selected === t.name ? 'var(--accent)' : 'var(--text-muted)',
              }}>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{t.name}</div>
              <div style={{ fontSize: 11, marginTop: 3, color: 'var(--text-dim)' }}>{t.description?.slice(0, 60)}...</div>
            </button>
          ))}
        </div>
        <div>
          <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 6 }}>Parameters (JSON)</div>
          <textarea
            value={params}
            onChange={e => setParams(e.target.value)}
            style={{
              width: '100%', height: 160, background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 8, padding: 12, color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: 12, resize: 'vertical',
            }}
          />
          <button onClick={run} disabled={running}
            style={{ marginTop: 8, padding: '8px 20px', borderRadius: 6, background: 'var(--accent)', border: 'none', color: '#fff', cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>
            {running ? 'Running...' : 'Run Tool'}
          </button>
          {result && (
            <pre style={{ marginTop: 12, background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, padding: 12, overflow: 'auto', maxHeight: 300, fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              {JSON.stringify(result, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Observability Panel ─────────────────────────────────────────────────────

function ObservabilityPanel({ health }: { health: HealthData | null }) {
  return (
    <div style={{ padding: 24, flex: 1, overflowY: 'auto' }}>
      <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Observability</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: 'Total Requests', value: health?.token_usage?.total_requests ?? 0, color: 'var(--accent)' },
          { label: 'Total Tokens', value: (health?.token_usage?.total_tokens ?? 0).toLocaleString(), color: 'var(--green)' },
          { label: 'Active Providers', value: health?.providers?.length ?? 0, color: 'var(--purple)' },
        ].map(stat => (
          <div key={stat.label} style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, padding: '16px 20px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{stat.label}</div>
            <div style={{ fontSize: 28, fontWeight: 700, color: stat.color, fontFamily: 'var(--font-mono)', marginTop: 8 }}>{stat.value}</div>
          </div>
        ))}
      </div>
      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, padding: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-dim)', marginBottom: 12 }}>ARCHITECTURE COMPONENTS</div>
        {[
          { name: 'Prompt Injection Guard', status: 'active', desc: 'Pattern-based detection on all inputs' },
          { name: 'LLM Router', status: 'active', desc: `Primary: ${health?.providers?.[0] || 'none'}, Fallback chain enabled` },
          { name: 'Vector Store (ChromaDB)', status: 'active', desc: `${health?.knowledge_base?.chunks ?? 0} chunks indexed` },
          { name: 'Tool Registry', status: 'active', desc: 'github, slack, database, filesystem' },
          { name: 'Agent Pipeline', status: 'active', desc: 'Planner → Research → Analysis → QA → Summary' },
          { name: 'Retry Strategy', status: 'active', desc: 'Exponential backoff, max 3 attempts per provider' },
        ].map(c => (
          <div key={c.name} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
            <Check size={14} color="var(--green)" style={{ marginTop: 2, flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{c.name}</div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>{c.desc}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
