import { useEffect, useRef, useState } from 'react'
import botanyVideo from './assets/botany-loop.mp4'
import {
  ArrowRight, Check, ChevronDown, Cloud,
  Command, Copy, Cpu, Github, Layers3, LockKeyhole, Radio, ShieldAlert,
  TerminalSquare, Zap,
} from 'lucide-react'
import TerminalPreview from './TerminalPreview'

type InstallTab = 'cli' | 'claude' | 'cloud'
type Architecture = 'local' | 'cloud'

const installCommands: Record<InstallTab, string> = {
  cli: 'pip install agentdrift && agentdrift watch',
  claude: 'claude mcp add agentdrift -- uvx agentdrift mcp',
  cloud: 'https://mcp.agentdrift.dev/sse',
}

const HERO_INSTALL_CMD = 'uvx agentdrift mcp'

const featureCards = [
  { num: '01', icon: <Layers3 size={18} strokeWidth={1.5} className="text-white" />, title: 'Sub-millisecond\nlocal store', body: 'SQLite + LanceDB live in ~/.agentdrift. Every turn is indexed on-device. No account, no network, no waiting.', tag: '100% OFFLINE' },
  { num: '02', icon: <ShieldAlert size={18} strokeWidth={1.5} className="text-white" />, title: 'Zero-token\ncircuit breaker', body: 'Catch the loop before the next model call. Stop retry storms in Claude Code, Cline, OpenCode, and Codex.', tag: 'STOP BEFORE SPEND' },
  { num: '03', icon: <Radio size={18} strokeWidth={1.5} className="text-white" />, title: 'Dual ingestion', body: 'Observe from a native terminal hook or connect a remote Cloud MCP over SSE / Streamable HTTP.', tag: 'STDIO ↔ CLOUD' },
  { num: '04', icon: <Cpu size={18} strokeWidth={1.5} className="text-white" />, title: 'Gate 1 + Gate 2 NLI', body: 'Check structural envelopes first. Then verify the action still aligns with the agent’s original goal.', tag: 'STRUCTURE + INTENT' },
]

function copyText(value: string, buttonId: string, setCopied: (id: string) => void) {
  navigator.clipboard?.writeText(value).then(() => {
    setCopied(buttonId)
    window.setTimeout(() => setCopied(''), 1600)
  }).catch(() => {
    setCopied(buttonId)
    window.setTimeout(() => setCopied(''), 1600)
  })
}

function BrandMark() {
  return <a className="brand" href="#top" aria-label="AgentDrift home"><span className="brand-glyph">A<span>/</span>D</span><span>AGENTDRIFT</span></a>
}

export default function App() {
  const [installTab, setInstallTab] = useState<InstallTab>('cli')
  const [architecture, setArchitecture] = useState<Architecture>('local')
  const [copied, setCopied] = useState('')
  const videoRef = useRef<HTMLVideoElement>(null)

  const activeCommand = installCommands[installTab]

  // Safari/WebKit autoplay fix: force DOM muted state, attempt silent
  // autoplay, then register one-time passive gesture listeners so the
  // video starts on the first touch/click/scroll if the policy blocked it.
  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    // Enforce WebKit muted properties directly on DOM node
    video.muted = true
    video.defaultMuted = true

    // Try initial silent autoplay without throwing errors
    const startPlay = () => {
      video.play().catch(() => {
        // Autoplay policy blocked; waiting for user gesture
      })
    }

    startPlay()

    // Unlock on any first user gesture (touch, trackpad swipe, wheel, click)
    const unlockAutoplay = () => {
      if (video.paused) {
        video.play().catch(() => {})
      }
      cleanup()
    }

    const cleanup = () => {
      window.removeEventListener('pointerdown', unlockAutoplay)
      window.removeEventListener('touchstart', unlockAutoplay)
      window.removeEventListener('scroll', unlockAutoplay)
      window.removeEventListener('wheel', unlockAutoplay)
    }

    window.addEventListener('pointerdown', unlockAutoplay, { passive: true })
    window.addEventListener('touchstart', unlockAutoplay, { passive: true })
    window.addEventListener('scroll', unlockAutoplay, { passive: true })
    window.addEventListener('wheel', unlockAutoplay, { passive: true })

    return cleanup
  }, [])

  return (
    <div className="relative min-h-screen w-full bg-[#040608] text-white selection:bg-white selection:text-black font-sans antialiased overflow-x-hidden">

      {/* ================= GLOBAL FIXED BACKGROUND VIDEO ================= */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden bg-[#040608]">
        <video
          ref={videoRef}
          src={botanyVideo}
          autoPlay
          loop
          muted
          playsInline
          // @ts-ignore — webkit-playsinline is a non-standard WebKit attribute
          webkit-playsinline="true"
          preload="auto"
          className="w-full h-full object-contain object-right opacity-80 contrast-115 brightness-110"
        />
        {/* Left side scrim to keep hero text readable */}
        <div className="absolute inset-0 bg-gradient-to-r from-[#040608] via-[#040608]/70 to-transparent w-full md:w-3/5" />
      </div>
      {/* ================================================================= */}

      {/* ================= FOREGROUND CONTENT ================= */}
      {/* Interactive UI Container — max-width 1280px page container, centered */}
      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-[1280px] flex-col px-6 md:px-12 py-6">
      <header className="site-header wrap">
        <BrandMark />
        <nav className="top-nav" aria-label="Main navigation">
          <a href="#signal">SYSTEM</a><a href="#features">CAPABILITIES</a><a href="#setup">QUICK START</a>
        </nav>
        <a className="nav-github" href="https://github.com/search?q=agentdrift&type=repositories" target="_blank" rel="noreferrer"><Github size={15} /> SOURCE <ArrowRight size={13} /></a>
      </header>

      <section className="hero hero-terminal wrap zone-left" aria-labelledby="hero-title">
        <div className="hero-copy">
          <div className="hero-pill font-mono text-[11px] tracking-widest uppercase">[ FIG. 01 // RUNTIME SUPERVISOR ]</div>
          <h1 id="hero-title" className="text-5xl md:text-7xl font-sans font-bold tracking-tight leading-[0.92] text-white">Stop the<br />spiral.</h1>
          <p className="hero-subtitle">The runtime supervisor and circuit breaker for autonomous coding agents. Catch the loop while it’s still one tool call away.</p>
          <div className="hero-install" role="group" aria-label="Copy install command">
            <div className="flex min-w-0 items-center gap-3">
              <span className="font-mono text-sm text-zinc-500">$</span>
              <code className="font-mono text-[13px] text-white">{HERO_INSTALL_CMD}</code>
            </div>
            <button onClick={() => copyText(HERO_INSTALL_CMD, 'hero', setCopied)} aria-label="Copy install command">
              {copied === 'hero' ? <Check size={14} /> : <Copy size={14} />}
              <span className="font-mono text-[10px] tracking-widest">{copied === 'hero' ? 'COPIED' : 'COPY'}</span>
            </button>
          </div>
          <div className="hero-actions">
            <a className="bg-white text-black font-mono font-medium hover:bg-zinc-200 transition-colors h-12 inline-flex items-center justify-between gap-7 px-4 text-xs" href="#setup"><span>Install AgentDrift</span><ArrowRight size={16} /></a>
            <a className="border border-zinc-700 text-white hover:bg-zinc-900 transition-colors inline-flex gap-2.5 items-center px-4 py-3.5 font-mono text-[10px] tracking-widest" href="#setup"><span>Quickstart</span><ArrowRight size={14} /></a>
          </div>
          <div className="hero-proof font-mono"><span>CLAUDE CODE • CLINE • OPENCODE • CODEX</span></div>
        </div>
      </section>

      <section className="signal-section wrap zone-left" id="signal">
        <div className="section-label"><span>01 — SIGNAL TRACE</span><span>WATCH THE LOOP BREAK</span></div>
        <div className="signal-layout">
          <div className="signal-copy">
            <div className="font-mono text-[11px] tracking-widest text-zinc-400 uppercase flex items-center gap-2"><span className="signal-square" /> LIVE SESSION / SIMULATED</div>
            <h2 className="text-white font-bold tracking-tight leading-[0.92]">Same error.<br /><em>New attempt.</em><br />Same result.</h2>
            <p>Agents don’t know they’re stuck. AgentDrift compares the state they just reached with the state they reached a moment ago—and cuts the loop before the token meter keeps climbing.</p>
            <a href="#features" className="text-link">HOW THE SENTINEL WORKS <ArrowRight size={14} /></a>
            <div className="signal-number"><span>0.92</span><small>SIMILARITY TRIP THRESHOLD</small></div>
          </div>
          <TerminalPreview />
        </div>
      </section>

      <section className="feature-section wrap zone-left" id="features">
        <div className="section-label"><span>02 — FIELD NOTES</span><span>FOUR LAYERS OF CONTROL</span></div>
        <div className="feature-heading"><h2 className="text-white font-bold tracking-tight leading-[0.92]">Keep the work<br />moving <span>forward.</span></h2><p>A small runtime layer between an agent’s intent and its next action. No orchestration platform required.</p></div>
        <div className="feature-grid">
          {featureCards.map((feature) => <article className="border border-white/10 bg-black/40 backdrop-blur-md p-6 hover:border-white/20 transition-all" key={feature.num}>
            <div className="feature-card-top"><span className="feature-num">{feature.num} / 04</span><span className="feature-icon">{feature.icon}</span></div>
            <h3>{feature.title.split('\n').map((line, index) => <span key={line}>{index > 0 && <br />}{line}</span>)}</h3>
            <p>{feature.body}</p>
            <div className="feature-card-foot"><span>{feature.tag}</span><span className="feature-plus">↗</span></div>
          </article>)}
        </div>
      </section>

      <section className="architecture-section wrap zone-left" id="architecture">
        <div className="section-label"><span>03 — DEPLOYMENT SHAPE</span><span>ONE SENTINEL / TWO MODES</span></div>
        <div className="architecture-head"><div><div className="font-mono text-[11px] tracking-widest text-zinc-400 uppercase">CHOOSE YOUR TERRAIN</div><h2 className="text-white font-bold tracking-tight leading-[0.92]">Stay close.<br /><span>Or go wide.</span></h2></div><p>Start with a local process. Add a shared cloud endpoint when your team needs a common memory.</p></div>
        <div className="architecture-switch" role="tablist" aria-label="Choose deployment mode">
          <button className={architecture === 'local' ? 'selected bg-white text-black font-mono text-xs' : 'text-zinc-400 hover:text-white font-mono text-xs'} onClick={() => setArchitecture('local')} role="tab" aria-selected={architecture === 'local'}><TerminalSquare size={16} /> LOCAL FIRST <span>A</span></button>
          <button className={architecture === 'cloud' ? 'selected bg-white text-black font-mono text-xs' : 'text-zinc-400 hover:text-white font-mono text-xs'} onClick={() => setArchitecture('cloud')} role="tab" aria-selected={architecture === 'cloud'}><Cloud size={16} /> CLOUD SCALE <span>B</span></button>
        </div>
        <div className="architecture-panel">
          <div className="arch-diagram">
            {architecture === 'local' ? <>
              <div className="diagram-node agent-node"><span className="node-icon"><Command size={17} /></span><b>CODING AGENT</b><small>Claude · Cline · OpenCode</small></div>
              <div className="diagram-line"><i /><span>stdio / tool call</span><i /></div>
              <div className="diagram-node sentinel-node"><span className="node-icon"><Zap size={17} /></span><b>AGENTDRIFT</b><small>local MCP + loop sentinel</small></div>
              <div className="diagram-line"><i /><span>embedded · zero network</span><i /></div>
              <div className="diagram-node storage-node"><span className="node-icon"><Layers3 size={17} /></span><b>SQLITE + LANCEDB</b><small>~/.agentdrift / on device</small></div>
            </> : <>
              <div className="diagram-node agent-node"><span className="node-icon"><Command size={17} /></span><b>TEAM AGENTS</b><small>multiple clients / identities</small></div>
              <div className="diagram-line"><i /><span>Streamable HTTP / SSE</span><i /></div>
              <div className="diagram-node sentinel-node"><span className="node-icon"><Zap size={17} /></span><b>CLOUD MCP</b><small>FastMCP / authenticated</small></div>
              <div className="diagram-line"><i /><span>RLS · user scoped</span><i /></div>
              <div className="diagram-node storage-node"><span className="node-icon"><LockKeyhole size={17} /></span><b>SUPABASE</b><small>Postgres + pgvector</small></div>
            </>}
          </div>
          <div className="architecture-details">
            <span className="arch-kicker">MODE {architecture === 'local' ? 'A / LOCAL' : 'B / CLOUD'}</span>
            <h3>{architecture === 'local' ? 'Your machine. Your memory.' : 'One signal across the team.'}</h3>
            <p>{architecture === 'local'
              ? 'Run the sentinel beside the agent. Turns are stored locally and compared before another action is taken. Works offline from the first command.'
              : 'Deploy the Python MCP server behind your own domain. Supabase Auth scopes sessions to each user; pgvector keeps similarity checks close to the data.'}</p>
            <code>{architecture === 'local' ? 'uvx agentdrift mcp' : 'python -m agentdrift.mcp.cloud_server --transport sse'}</code>
            <span className="arch-note"><i /> {architecture === 'local' ? 'NO CLOUD ACCOUNT REQUIRED' : 'YOUR DATABASE · YOUR AUTH · YOUR RULES'}</span>
          </div>
        </div>
      </section>

      <section className="install-section wrap zone-left" id="setup">
        <div className="section-label"><span>04 — FIRST CONTACT</span><span>THREE WAYS IN</span></div>
        <div className="install-layout">
          <div className="install-copy"><div className="font-mono text-[11px] tracking-widest text-zinc-400 uppercase">BOOT SEQUENCE / 30 SECONDS</div><h2 className="text-white font-bold tracking-tight leading-[0.92]">Give your agent<br />a <span>way out.</span></h2><p>Pick a surface. Keep your current workflow. AgentDrift watches the space between turns.</p>
            <div className="install-note"><span className="note-glyph">✳</span><span>Local-first. No API keys.<br /><b>Cloud is an opt-in.</b></span></div>
          </div>
          <div className="install-widget">
            <div className="install-tabs" role="tablist" aria-label="Install method">
              <button className={installTab === 'cli' ? 'selected bg-white text-black font-mono text-xs' : 'text-zinc-400 hover:text-white font-mono text-xs'} onClick={() => setInstallTab('cli')} role="tab" aria-selected={installTab === 'cli'}>CLI <span>01</span></button>
              <button className={installTab === 'claude' ? 'selected bg-white text-black font-mono text-xs' : 'text-zinc-400 hover:text-white font-mono text-xs'} onClick={() => setInstallTab('claude')} role="tab" aria-selected={installTab === 'claude'}>CLAUDE MCP <span>02</span></button>
              <button className={installTab === 'cloud' ? 'selected bg-white text-black font-mono text-xs' : 'text-zinc-400 hover:text-white font-mono text-xs'} onClick={() => setInstallTab('cloud')} role="tab" aria-selected={installTab === 'cloud'}>CLOUD <span>03</span></button>
            </div>
            <div className="install-code"><div><span className="install-prompt">$</span><code key={installTab}>{activeCommand}</code></div><button onClick={() => copyText(activeCommand, 'install', setCopied)} aria-label="Copy install command">{copied === 'install' ? <Check size={17} /> : <span className="copy-word">COPY</span>}</button></div>
            <div className="install-description">{installTab === 'cli' && 'Install the CLI and stream a local session. No daemon to configure.'}{installTab === 'claude' && 'Register AgentDrift as a local stdio MCP server for Claude Code.'}{installTab === 'cloud' && 'Remote endpoint example. Deploy your own Cloud MCP before connecting.'}</div>
            <div className="install-bottom"><span><i /> READY TO RUN</span><a href="https://pypi.org/project/agentdrift/" target="_blank" rel="noreferrer">VIEW PACKAGE <ArrowRight size={13} /></a></div>
          </div>
        </div>
      </section>

      <footer className="site-footer wrap">
        <div className="footer-bloom" aria-hidden="true"><span>✳</span><span>✳</span><span>✳</span><span>✳</span><span>✳</span></div>
        <div className="footer-main"><div><BrandMark /><p>Keep the agent curious.<br />Keep the loop short.</p></div><div className="footer-links"><a href="https://github.com/search?q=agentdrift&type=repositories" target="_blank" rel="noreferrer"><Github size={14} /> GITHUB</a><a href="https://pypi.org/project/agentdrift/" target="_blank" rel="noreferrer"><Command size={14} /> PYPI PACKAGE</a><a href="#setup">DOCUMENTATION <ChevronDown size={13} /></a></div></div>
        <div className="footer-bottom"><span>© AGENTDRIFT / BUILT FOR THE MOMENT BEFORE RETRY</span><span>LOCAL SIGNAL <b>✳</b> CLEAR INTENT</span></div>
      </footer>
      </div>
    </div>
  )
}
