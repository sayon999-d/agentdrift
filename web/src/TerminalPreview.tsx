import { useEffect, useState } from 'react'
import { Activity, AlertTriangle, Circle, Copy, Terminal } from 'lucide-react'

type View = 'watch' | 'mcp'

const watchLines = [
  { time: '11:02:46', tone: 'normal', text: 'claude-code:edit  →  {"file":"auth.py","op":"retry_patch"}' },
  { time: '11:02:47', tone: 'muted', text: 'claude-code:test  →  {"exit_code":1,"error":"SyntaxError"}' },
  { time: '11:02:48', tone: 'alert', text: '🚨 [PING-PONG LOOP DETECTED] session_id=live-01 similarity=0.9988' },
  { time: '11:02:48', tone: 'stop', text: '[CIRCUIT BREAKER] Interrupted turn 4. Halting spiral.' },
]

const mcpLines = [
  { time: '11:02:45', tone: 'muted', text: 'mcp:tools/list  →  3 tools ready · stdio · local' },
  { time: '11:02:46', tone: 'normal', text: 'log_agent_turn  →  session=live-01 sequence=03' },
  { time: '11:02:48', tone: 'alert', text: '🚨 [PING-PONG LOOP DETECTED] similarity=0.9988' },
  { time: '11:02:48', tone: 'stop', text: 'check_drift_status  →  STOP / new action required' },
]

const waveform = [18, 24, 21, 30, 25, 28, 39, 33, 42, 37, 45, 39, 60, 46, 55, 47, 74, 61, 83, 67, 97, 76, 91, 69, 88, 63, 70, 53, 64, 48, 54, 37, 46, 29, 39, 24, 32, 19, 27, 14]

export default function TerminalPreview() {
  const [view, setView] = useState<View>('watch')
  const [pulse, setPulse] = useState(0)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const timer = window.setInterval(() => setPulse((value) => (value + 1) % 4), 850)
    return () => window.clearInterval(timer)
  }, [])

  const copy = async () => {
    await navigator.clipboard?.writeText('agentdrift watch --threshold 0.92')
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  const lines = view === 'watch' ? watchLines : mcpLines

  return (
    <div className="terminal-shell">
      <div className="terminal-topbar">
        <div className="window-dots" aria-hidden="true"><i /><i /><i /></div>
        <div className="terminal-title"><Terminal size={13} /> agentdrift / sentinel</div>
        <span className="terminal-live"><span className="live-dot" /> LIVE</span>
      </div>
      <div className="terminal-toolbar">
        <div className="terminal-tabs" role="tablist" aria-label="Terminal view">
          <button className={view === 'watch' ? 'active' : ''} onClick={() => setView('watch')} role="tab" aria-selected={view === 'watch'}>watch</button>
          <button className={view === 'mcp' ? 'active' : ''} onClick={() => setView('mcp')} role="tab" aria-selected={view === 'mcp'}>mcp</button>
        </div>
        <button className="icon-button" aria-label="Copy watch command" onClick={copy}><Copy size={13} /> {copied ? 'COPIED' : 'COPY CMD'}</button>
      </div>
      <div className="terminal-content" aria-live="polite">
        <div className="command-line"><span className="prompt">❯</span> agentdrift {view}<span className="cursor" /></div>
        <div className="log-stack">
          {lines.map((line, index) => (
            <div className={`log-line ${line.tone}`} key={`${view}-${line.time}-${index}`}>
              <span className="log-time">[{line.time}]</span><span>{line.text}</span>
            </div>
          ))}
        </div>
        <div className="wave-panel">
          <div className="wave-heading"><span><Activity size={12} /> STATE SIMILARITY</span><span className="threshold-label">TRIP LINE 0.92</span></div>
          <div className="wave-chart" role="img" aria-label="Similarity graph, signal rises above the 0.92 circuit breaker threshold">
            <div className="threshold-rule"><span>0.92</span></div>
            {waveform.map((height, index) => <i key={index} className={height > 73 ? 'hot' : ''} style={{ height: `${height}%`, opacity: index === 20 && pulse === 0 ? 0.35 : 0.9 }} />)}
            <div className="trip-marker"><AlertTriangle size={10} /> TRIP</div>
          </div>
          <div className="wave-labels"><span>t−12s</span><span>latest turn</span></div>
        </div>
      </div>
      <div className="terminal-footer"><span><Circle size={7} fill="currentColor" /> STORE: LOCAL SQLITE + LANCEDB</span><span>LATENCY <b>0.8ms</b></span></div>
    </div>
  )
}
