import { useEffect, useState } from "react"
import { AlertTriangle } from "lucide-react"
import { cn } from "@/lib/utils"

const WAVEFORM = [18, 24, 21, 30, 25, 28, 39, 33, 42, 37, 45, 39, 60, 46, 55, 47, 74, 61, 83, 67, 97, 76, 91, 69, 88, 63, 70, 53, 64, 48, 54, 37, 46, 29, 39, 24, 32, 19, 27, 14]

const HOT_STYLE = "bg-white"
const COLD_STYLE = "bg-[#3f3f46]"

/** Live circuit-breaker telemetry simulation: similarity drifts up, trips at 0.92, resets. Monochrome. */
export function TelemetryTicker({ className }: { className?: string }) {
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => (t + 1) % WAVEFORM.length), 650)
    return () => window.clearInterval(id)
  }, [])

  const head = (20 + tick) % WAVEFORM.length
  const sim = (WAVEFORM[head] / 100).toFixed(2)
  const tripped = WAVEFORM[head] > 73

  return (
    <div className={cn("border-t border-white/10 pt-3", className)}>
      <div className="flex items-center justify-between font-mono text-[8px] tracking-[0.08em] text-zinc-500">
        <span className="flex items-center gap-1.5 text-zinc-300">
          STATE SIMILARITY <span className="font-mono text-white">{sim}</span>
        </span>
        <span className={tripped ? "text-white" : "text-zinc-500"}>
          {tripped ? (
            <span className="inline-flex items-center gap-1 bg-white px-1.5 py-0.5 font-bold text-black">
              <AlertTriangle size={10} /> TRIP · 0.92
            </span>
          ) : (
            "TRIP LINE 0.92"
          )}
        </span>
      </div>
      <div
        className="relative mt-2 flex h-[64px] items-end gap-1 px-1"
        role="img"
        aria-label="Live similarity graph"
      >
        <div className="absolute inset-x-0 bottom-[25%] z-[2] border-t border-dashed border-white/40" />
        {WAVEFORM.map((h, index) => (
          <em
            key={index}
            style={{ height: `${h}%`, opacity: index === head ? 1 : 0.55 }}
            className={cn(
              "z-[1] min-w-[2px] flex-1 not-italic transition-all duration-300",
              h > 73 ? HOT_STYLE : COLD_STYLE
            )}
          />
        ))}
      </div>
      <div className="mt-1.5 flex justify-between font-mono text-[7px] uppercase text-zinc-500">
        <span>t-12s</span>
        <span className={tripped ? "text-white" : ""}>
          {tripped ? "breaker: STOP" : "breaker: armed"}
        </span>
      </div>
    </div>
  )
}
