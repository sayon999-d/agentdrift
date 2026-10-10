"use client"

// AsciiArt — "ascii flower", made with the 21st.dev ASCII editor and baked
// to its exact rendered output (looping video + poster). Zero dependencies:
// one <video> that fills its parent. Drop it behind or inside your content:
// <div className="relative h-96"><AsciiArt className="absolute inset-0" /></div>
// Remix the source recipe (styles, animation, palette) in the editor:
// https://21st.dev/community/ascii/editor?from=7e81d96d-0512-43e2-b311-ec057243029b
export function AsciiArt({ className }: { className?: string }) {
  return (
    <video
      className={className}
      src={"https://assets.21st.dev/ascii-recipes/videos/user_303XMtoirrQlWWGb8KnV7WJoQOZ/fc9d5504-d38b-4561-8b1b-2dbaec1e9a6e.mp4"}
      poster={"https://assets.21st.dev/ascii-recipes/thumbnails/user_303XMtoirrQlWWGb8KnV7WJoQOZ/7fa35d6b-864c-403a-ac1c-31366c7f0ace.webp"}
      autoPlay
      loop
      muted
      playsInline
      aria-label={"ascii flower — animated ASCII art"}
      style={{
        display: "block",
        width: "100%",
        height: "100%",
        objectFit: "cover",
      }}
    />
  )
}
