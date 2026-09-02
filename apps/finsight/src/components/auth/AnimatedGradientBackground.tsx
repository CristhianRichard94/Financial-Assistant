export function AnimatedGradientBackground() {
  return (
    <div aria-hidden="true" className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
      <div
        className="absolute rounded-full w-[60vw] h-[60vw] max-w-[520px] max-h-[520px] top-[-10%] left-[-15%] bg-[hsl(var(--primary)/0.30)] animate-blob-a max-[375px]:max-w-[280px] max-[375px]:max-h-[280px]"
        style={{ filter: "blur(80px)" }}
      />
      <div
        className="absolute rounded-full w-[50vw] h-[50vw] max-w-[440px] max-h-[440px] bottom-[-15%] right-[-10%] bg-[hsl(var(--accent)/0.35)] animate-blob-b max-[375px]:max-w-[280px] max-[375px]:max-h-[280px]"
        style={{ filter: "blur(80px)" }}
      />
      <div
        className="absolute rounded-full w-[40vw] h-[40vw] max-w-[360px] max-h-[360px] top-[35%] right-[20%] bg-[hsl(var(--secondary)/0.30)] animate-blob-c max-[375px]:max-w-[280px] max-[375px]:max-h-[280px]"
        style={{ filter: "blur(80px)" }}
      />
    </div>
  );
}
