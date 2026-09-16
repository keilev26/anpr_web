import { useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"

interface Props {
  hasNextPage: boolean
  isFetchingNextPage: boolean
  fetchNextPage: () => void
  loaded: number
  /** Sustantivo en singular: "registro", "usuario". */
  noun: string
}

/**
 * Carga la siguiente página al entrar en viewport, con botón manual de respaldo.
 * El botón no es decorativo: si IntersectionObserver no dispara (contenedor con
 * overflow, navegador antiguo, usuario navegando por teclado), sigue habiendo
 * una forma de avanzar.
 */
export function InfiniteFooter({
  hasNextPage, isFetchingNextPage, fetchNextPage, loaded, noun,
}: Props) {
  const sentinel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = sentinel.current
    if (!el || !hasNextPage || isFetchingNextPage) return

    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) fetchNextPage()
      },
      { rootMargin: "200px" }, // precarga antes de llegar al final
    )
    io.observe(el)
    return () => io.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  return (
    <div className="flex flex-col items-center gap-2 py-4">
      <div ref={sentinel} aria-hidden className="h-px w-full" />
      <p className="text-sm text-muted-foreground" aria-live="polite">
        {loaded} {noun}
        {loaded === 1 ? "" : "s"} cargado{loaded === 1 ? "" : "s"}
        {hasNextPage ? "" : " — no hay más"}
      </p>
      {hasNextPage && (
        <Button
          variant="outline"
          size="sm"
          onClick={fetchNextPage}
          disabled={isFetchingNextPage}
        >
          {isFetchingNextPage ? "Cargando…" : "Cargar más"}
        </Button>
      )}
    </div>
  )
}
