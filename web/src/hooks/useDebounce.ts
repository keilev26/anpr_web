import { useEffect, useState } from "react"

/**
 * Retrasa la propagación de un valor. Con paginación por cursor, cada pulsación
 * en el buscador reiniciaría la consulta y descartaría las páginas ya cargadas;
 * esto espera a que el usuario deje de escribir.
 */
export function useDebounce<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(t)
  }, [value, delayMs])

  return debounced
}
