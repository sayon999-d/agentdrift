import { useEffect, useRef } from 'react'

const GLYPHS = '@#S%?*+;:,. '

export default function HeroAsciiFlower() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const frameRef = useRef(0)
  const pointer = useRef({ x: -1000, y: -1000, active: false })

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d', { willReadFrequently: true })
    if (!canvas || !ctx) return

    const source = new Image()
    source.src = '/hero-flower.png'
    source.onerror = () => { source.src = '/hero-flower.svg' }
    let pixels: ImageData | null = null
    let width = 0
    let height = 0
    let animation = 0

    const resize = () => {
      const box = canvas.getBoundingClientRect()
      const scale = Math.min(window.devicePixelRatio || 1, 1.6)
      width = Math.max(1, Math.round(box.width * scale))
      height = Math.max(1, Math.round(box.height * scale))
      canvas.width = width
      canvas.height = height
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.fillStyle = '#000000'
      ctx.fillRect(0, 0, width, height)
      if (!source.complete || !source.naturalWidth) return
      const ratio = Math.max(width / source.naturalWidth, height / source.naturalHeight)
      const drawW = source.naturalWidth * ratio
      const drawH = source.naturalHeight * ratio
      ctx.drawImage(source, (width - drawW) / 2, (height - drawH) / 2, drawW, drawH)
      pixels = ctx.getImageData(0, 0, width, height)
    }

    source.onload = resize
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    window.addEventListener('resize', resize)

    const draw = () => {
      animation = requestAnimationFrame(draw)
      if (!pixels) return
      frameRef.current += 1
      if (frameRef.current % 2) return
      ctx.clearRect(0, 0, width, height)
      const cellX = Math.max(8, Math.floor(width / 46))
      const cellY = Math.round(cellX * 1.2)
      const split = Math.floor(height * 0.49)
      const px = pointer.current.x * (window.devicePixelRatio || 1)
      const py = pointer.current.y * (window.devicePixelRatio || 1)
      ctx.font = `${cellY}px 'JetBrains Mono', 'Geist Mono', monospace`
      ctx.textBaseline = 'top'

      for (let y = 0; y < split; y += cellY) {
        for (let x = 0; x < width; x += cellX) {
          const at = (y * width + x) * 4
          const red = pixels.data[at]
          const green = pixels.data[at + 1]
          const blue = pixels.data[at + 2]
          const alpha = pixels.data[at + 3]
          const light = (red * 0.3 + green * 0.55 + blue * 0.15) / 255
          if (alpha < 20 || light < 0.075) continue
          const distance = Math.hypot(px - x, py - y)
          const near = pointer.current.active && distance < cellX * 8
          const drift = near ? Math.sin(frameRef.current * 0.13 + x) * cellX * 0.36 : 0
          const glyphIndex = Math.min(GLYPHS.length - 1, Math.floor((1 - light) * GLYPHS.length))
          const color = near
            ? 'rgba(255,255,255,.96)'
            : `rgba(${Math.min(255, red + 22)},${Math.min(255, red + 22)},${Math.min(255, blue + 20)},${Math.min(.92, .16 + light * .96)})`
          ctx.fillStyle = color
          ctx.fillText(GLYPHS[glyphIndex], x + drift, y)
        }
      }
      // Signal registration slips a few pixels while the cursor is over the glass.
      if (pointer.current.active && frameRef.current % 28 < 4) {
        ctx.globalCompositeOperation = 'screen'
        ctx.globalAlpha = 0.16
        ctx.drawImage(canvas, -2, 0)
        ctx.globalAlpha = 1
        ctx.globalCompositeOperation = 'source-over'
      }
    }
    animation = requestAnimationFrame(draw)

    const onPointer = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      pointer.current = {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
        active: true,
      }
    }
    const onLeave = () => { pointer.current.active = false }
    canvas.addEventListener('pointermove', onPointer)
    canvas.addEventListener('pointerleave', onLeave)

    return () => {
      cancelAnimationFrame(animation)
      observer.disconnect()
      window.removeEventListener('resize', resize)
      canvas.removeEventListener('pointermove', onPointer)
      canvas.removeEventListener('pointerleave', onLeave)
    }
  }, [])

  return (
    <div className="flower-frame" aria-label="A monochrome botanical plate rendered as a grayscale terminal matrix">
      <img src="/hero-flower.svg" className="flower-underlay" alt="Monochrome botanical plate with scanline reflection" />
      <canvas ref={canvasRef} className="flower-canvas" aria-hidden="true" />
      <div className="flower-scanlines" aria-hidden="true" />
      <div className="flower-stamp"><span>FIG. 01</span><span>STATE / BLOOM</span><span>384D</span></div>
      <div className="flower-coordinate">37° 46' 49.3" N<br />122° 25' 09.1" W</div>
      <span className="flower-side-label">RUNTIME BOTANY — LIVE SIGNAL</span>
    </div>
  )
}
