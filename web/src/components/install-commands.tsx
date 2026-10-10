import { useState } from "react"
import { Check } from "lucide-react"
import { cn } from "@/lib/utils"

type InstallTab = "cli" | "claude" | "cloud"

export const INSTALL_COMMANDS: Record<InstallTab, { cmd: string; hint: string }> = {
  cli: { cmd: "pip install agentdrift && agentdrift watch", hint: "Install the CLI and stream a local session. No daemon to configure." },
  claude: { cmd: "claude mcp add agentdrift -- uvx agentdrift mcp", hint: "Register AgentDrift as a local stdio MCP server for Claude Code." },
  cloud: { cmd: "https://mcp.agentdrift.dev/sse", hint: "Remote endpoint example. Deploy your own Cloud MCP before connecting." },
}

const TABS: { id: InstallTab; label: string; num: string }[] = [
  { id: "cli", label: "CLI", num: "01" },
  { id: "claude", label: "CLAUDE MCP", num: "02" },
  { id: "cloud", label: "CLOUD", num: "03" },
]

/** Quick installation commands widget — monochrome: black + white + zinc. */
export function InstallCommands({ className }: { className?: string }) {
  const [tab, setTab] = useState<InstallTab>("cli")
  const [copied, setCopied] = useState(false)
  const active = INSTALL_COMMANDS[tab]

  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(active.cmd)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div className={cn("border border-white/10 bg-black/70 backdrop-blur-md", className)}>
      <div className="grid grid-cols-3 border-b border-white/10" role="tablist" aria-label="Install method">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "flex items-center justify-between border-r border-white/10 bg-transparent px-3.5 py-3.5 font-mono text-xs tracking-[0.06em] last:border-r-0",
              tab === t.id ? "bg-white text-black font-medium" : "text-zinc-400 hover:text-white"
            )}
          >
            {t.label} <span className="text-[7px] opacity-60">{t.num}</span>
          </button>
        ))}
      </div>
      <div className="flex min-h-[112px] items-center justify-between gap-3.5 p-[22px]">
        <div className="flex min-w-0 items-start gap-3">
          <span className="font-mono text-base text-white">$</span>
          <code key={tab} className="font-mono text-[11px] leading-[1.8] text-white break-all">
            {active.cmd}
          </code>
        </div>
        <button
          onClick={copy}
          aria-label="Copy install command"
          className="grid h-[33px] min-w-[46px] flex-none place-items-center border border-zinc-700 bg-transparent font-mono text-[7px] text-white hover:bg-zinc-900"
        >
          {copied ? <Check size={15} /> : "COPY"}
        </button>
      </div>
      <div className="min-h-[44px] border-t border-white/10 px-[22px] py-3 font-mono text-[8px] leading-relaxed text-zinc-500">
        {active.hint}
      </div>
    </div>
  )
}
