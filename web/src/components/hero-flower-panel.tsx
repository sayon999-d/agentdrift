import { AsciiArt } from "@/components/ui/ascii-flower"
import { TelemetryTicker } from "@/components/telemetry-ticker"
import { cn } from "@/lib/utils"

/**
 * Centerpiece hero panel: pre-rendered animated ASCII flower video,
 * layered with terminal overlays (scanlines, corners, FIG stamps)
 * and a live circuit-breaker telemetry strip. Monochrome.
 */
export function HeroFlowerPanel({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "relative border border-white/10 bg-black/40 p-2.5 font-mono backdrop-blur-md",
        className
      )}
    >
      {/* corner brackets */}
      <div className="absolute -left-px -top-px z-[4] h-[22px] w-[22px] border-l border-t border-white/60" />
      <div className="absolute -bottom-px -right-px z-[4] h-[22px] w-[22px] border-b border-r border-white/60" />

      {/* video stage */}
      <div className="relative overflow-hidden bg-black">
        <AsciiArt className="block aspect-square w-full object-cover opacity-90 grayscale contrast-125 md:aspect-[4/3]" />

        {/* scanline / signal overlays — grayscale only */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 z-[2] opacity-55 animate-[signal-drift_7s_linear_infinite]"
          style={{
            background:
              "repeating-linear-gradient(0deg, rgba(0,0,0,.25) 0 1px, transparent 1px 4px), repeating-linear-gradient(90deg, rgba(255,255,255,.03) 0 1px, transparent 1px 3px, transparent 3px 6px)",
          }}
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 z-[3]"
          style={{
            background: "radial-gradient(ellipse at center, transparent 48%, rgba(0,0,0,.7) 100%)",
            boxShadow: "inset 0 0 35px #000",
          }}
        />

        {/* FIG stamps */}
        <div className="absolute left-3.5 right-3.5 top-3.5 z-[4] flex justify-between font-mono text-[8px] tracking-[0.1em] text-zinc-400">
          <span>FIG. 01</span>
          <span>STATE / BLOOM</span>
          <span>384D</span>
        </div>
        <div className="absolute bottom-[45%] left-3 z-[4] font-mono text-[7px] leading-[1.8] text-zinc-500">
          37° 46&apos; 49.3&quot; N<br />
          122° 25&apos; 09.1&quot; W
        </div>
        <span className="absolute right-2 top-[40%] z-[4] rotate-180 font-mono text-[7px] tracking-[0.1em] text-zinc-500 [writing-mode:vertical-rl]">
          RUNTIME BOTANY — LIVE SIGNAL
        </span>
      </div>

      {/* terminal overlay: live telemetry */}
      <div className="px-1.5 pb-1 pt-2">
        <TelemetryTicker />
      </div>

      <div className="flex justify-between px-1.5 pb-1 pt-1 font-mono text-[8px] tracking-[0.1em] text-zinc-500">
        <span>FIG 01 / ITERATION FLOWER</span>
        <span className="inline-flex items-center gap-2 text-white">
          SIGNAL ALIVE
          <i className="inline-block h-[5px] w-[5px] rounded-full bg-white animate-blink" />
        </span>
      </div>
    </div>
  )
}
