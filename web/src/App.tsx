import { useState } from 'react'
import {
  ArrowDownRight, ArrowRight, AudioLines, Check, ChevronDown, Cloud,
  Command, Cpu, Github, Layers3, LockKeyhole, Radio, ShieldAlert,
  TerminalSquare, Zap,
} from 'lucide-react'
import HeroAsciiFlower from './HeroAsciiFlower'
import TerminalPreview from './TerminalPreview'

type InstallTab = 'cli' | 'claude' | 'cloud'
type Architecture = 'local' | 'cloud'

const installCommands: Record<InstallTab, string> = {
  cli: 'pip install agentdrift && agentdrift watch',
  claude: 'claude mcp add agentdrift -- uvx agentdrift mcp',
  cloud: 'https://mcp.agentdrift.dev/sse',
}

const featureCards = [
  { num: '01', icon: <Layers3 />, title: 'Sub-millisecond\nlocal store', body: 'SQLite + LanceDB live in ~/.agentdrift. Every turn is indexed on-device. No account, no network, no waiting.', tag: '100% OFFLINE' },
  { num: '02', icon: <ShieldAlert />, title: 'Zero-token\ncircuit breaker', body: 'Catch the loop before the next model call. Stop retry storms in Claude Code, Cline, OpenCode, and Codex.', tag: 'STOP BEFORE SPEND' },
  { num: '03', icon: <Radio />, title: 'Dual ingestion', body: 'Observe from a native terminal hook or connect a remote Cloud MCP over SSE / Streamable HTTP.', tag: 'STDIO ↔ CLOUD' },
  { num: '04', icon: <Cpu />, title: 'Gate 1 + Gate 2 NLI', body: 'Check structural envelopes first. Then verify the action still aligns with the agent’s original goal.', tag: 'STRUCTURE + INTENT' },
]

function copyText(value: string, buttonId: string, setCopied: (id: string) => void) {
  navigator.clipboard?.writeText(value).then(() => {
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

  const activeCommand = installCommands[installTab]

  return (
    <main id="top">
      <div className="page-grid" aria-hidden="true" />
      <header className="site-header wrap">
        <BrandMark />
        <nav className="top-nav" aria-label="Main navigation">
          <a href="#signal">SYSTEM</a><a href="#features">CAPABILITIES</a><a href="#setup">QUICK START</a>
        </nav>
        <a className="nav-github" href="https://github.com/search?q=agentdrift&type=repositories" target="_blank" rel="noreferrer"><Github size={15} /> SOURCE <ArrowRight size={13} /></a>
      </header>

      <section className="hero wrap" aria-labelledby="hero-title">
        <div className="hero-copy">
          <div className="eyebrow"><span className="eyebrow-mark">✳</span> LOCAL-FIRST AGENT SUPERVISION <span className="eyebrow-rule" /></div>
          <div className="ascii-heading" aria-label="AgentDrift">
            <pre>{`╔═╗╔═╗╔═╗╔╗╔╔╦╗╔╦╗╦═╗
╠═╣║ ╦║╣ ║║║ ║  ║║╠╦╝
╩ ╩╚═╝╚═╝╝╚╝ ╩ ═╩╝╩╚═`}</pre>
            <span className="ascii-edge">AGENT / 00</span>
          </div>
          <h1 id="hero-title">Stop the<br /><span>spiral.</span></h1>
          <p className="hero-subtitle">The runtime supervisor and circuit breaker for autonomous coding agents. Catch the loop while it’s still one tool call away.</p>
          <div className="hero-actions">
            <a className="button-primary" href="#setup"><span>Install AgentDrift</span><ArrowRight size={16} /></a>
            <a className="button-quiet" href="#signal"><span className="play-symbol">▶</span> SEE IT TRIP <ArrowDownRight size={14} /></a>
          </div>
          <div className="hero-proof"><span><i className="proof-dot" /> CLAUDE CODE</span><span>CLINE</span><span>OPENCODE</span><span>CODEX</span></div>
        </div>
        <div className="hero-art-wrap">
          <div className="art-corner art-corner-tl" /><div className="art-corner art-corner-br" />
          <HeroAsciiFlower />
          <div className="art-caption"><span>FIG 01 / ITERATION FLOWER</span><span className="caption-blue">SIGNAL ALIVE <i /></span></div>
        </div>
        <div className="hero-footnote"><span>RUNTIME OBSERVABILITY FOR AGENTS</span><span>LOCAL BY DEFAULT <b>·</b> CLOUD WHEN READY</span></div>
      </section>

      <section className="signal-section wrap" id="signal">
        <div className="section-label"><span>01 — SIGNAL TRACE</span><span>WATCH THE LOOP BREAK</span></div>
        <div className="signal-layout">
          <div className="signal-copy">
            <div className="micro-label"><span className="signal-square" /> LIVE SESSION / SIMULATED</div>
            <h2>Same error.<br /><em>New attempt.</em><br />Same result.</h2>
            <p>Agents don’t know they’re stuck. AgentDrift compares the state they just reached with the state they reached a moment ago—and cuts the loop before the token meter keeps climbing.</p>
            <a href="#features" className="text-link">HOW THE SENTINEL WORKS <ArrowRight size={14} /></a>
            <div className="signal-number"><span>0.92</span><small>SIMILARITY TRIP THRESHOLD</small></div>
          </div>
          <TerminalPreview />
        </div>
      </section>

      <section className="feature-section wrap" id="features">
        <div className="section-label"><span>02 — FIELD NOTES</span><span>FOUR LAYERS OF CONTROL</span></div>
        <div className="feature-heading"><h2>Keep the work<br />moving <span>forward.</span></h2><p>A small runtime layer between an agent’s intent and its next action. No orchestration platform required.</p></div>
        <div className="feature-grid">
          {featureCards.map((feature) => <article className="feature-card" key={feature.num}>
            <div className="feature-card-top"><span className="feature-num">{feature.num} / 04</span><span className="feature-icon">{feature.icon}</span></div>
            <h3>{feature.title.split('\n').map((line, index) => <span key={line}>{index > 0 && <br />}{line}</span>)}</h3>
            <p>{feature.body}</p>
            <div className="feature-card-foot"><span>{feature.tag}</span><span className="feature-plus">↗</span></div>
          </article>)}
        </div>
      </section>

      <section className="architecture-section wrap" id="architecture">
        <div className="section-label"><span>03 — DEPLOYMENT SHAPE</span><span>ONE SENTINEL / TWO MODES</span></div>
        <div className="architecture-head"><div><div className="micro-label">CHOOSE YOUR TERRAIN</div><h2>Stay close.<br /><span>Or go wide.</span></h2></div><p>Start with a local process. Add a shared cloud endpoint when your team needs a common memory.</p></div>
        <div className="architecture-switch" role="tablist" aria-label="Choose deployment mode">
          <button className={architecture === 'local' ? 'selected' : ''} onClick={() => setArchitecture('local')} role="tab" aria-selected={architecture === 'local'}><TerminalSquare size={16} /> LOCAL FIRST <span>A</span></button>
          <button className={architecture === 'cloud' ? 'selected' : ''} onClick={() => setArchitecture('cloud')} role="tab" aria-selected={architecture === 'cloud'}><Cloud size={16} /> CLOUD SCALE <span>B</span></button>
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

      <section className="install-section wrap" id="setup">
        <div className="section-label"><span>04 — FIRST CONTACT</span><span>THREE WAYS IN</span></div>
        <div className="install-layout">
          <div className="install-copy"><div className="micro-label">BOOT SEQUENCE / 30 SECONDS</div><h2>Give your agent<br />a <span>way out.</span></h2><p>Pick a surface. Keep your current workflow. AgentDrift watches the space between turns.</p>
            <div className="install-note"><span className="note-glyph">✳</span><span>Local-first. No API keys.<br /><b>Cloud is an opt-in.</b></span></div>
          </div>
          <div className="install-widget">
            <div className="install-tabs" role="tablist" aria-label="Install method">
              <button className={installTab === 'cli' ? 'selected' : ''} onClick={() => setInstallTab('cli')} role="tab" aria-selected={installTab === 'cli'}>CLI <span>01</span></button>
              <button className={installTab === 'claude' ? 'selected' : ''} onClick={() => setInstallTab('claude')} role="tab" aria-selected={installTab === 'claude'}>CLAUDE MCP <span>02</span></button>
              <button className={installTab === 'cloud' ? 'selected' : ''} onClick={() => setInstallTab('cloud')} role="tab" aria-selected={installTab === 'cloud'}>CLOUD <span>03</span></button>
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
    </main>
  )
}
