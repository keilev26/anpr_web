import { useCallback, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { downloadCsv, timestampedName, toCsv, type CsvColumn } from "@/lib/csv"
import type { Page } from "@/types/api"

/** Máximo del contrato para `limit`. Menos páginas = menos viajes. */
const FETCH_LIMIT = 200

/** Tope de seguridad: evita que un filtro vacío intente traer la tabla entera. */
const MAX_ROWS = 10_000

interface Options<T> {
  path: string
  /** Los mismos filtros que la vista tiene aplicados. */
  params: Record<string, unknown>
  columns: CsvColumn<T>[]
  filePrefix: string
}

/**
 * Exporta TODAS las filas que cumplen el filtro actual, no solo las páginas ya
 * cargadas en pantalla: exportar lo visible daría un archivo incompleto sin que
 * el usuario lo note.
 *
 * Recorre el cursor del lado del cliente. Cuando F2 exista y el volumen lo pida,
 * esto debería ser un endpoint que genere el CSV en el servidor — es un cambio
 * de contrato, así que se acuerda con F2 antes de hacerlo.
 */
export function useCsvExport<T>({ path, params, columns, filePrefix }: Options<T>) {
  const [isExporting, setIsExporting] = useState(false)

  const exportCsv = useCallback(async () => {
    setIsExporting(true)
    const toastId = toast.loading("Preparando exportación…")

    try {
      const rows: T[] = []
      let cursor: string | null = null
      let truncated = false

      do {
        const page: Page<T> = await api.get<Page<T>>(path, {
          ...params,
          limit: FETCH_LIMIT,
          cursor: cursor ?? undefined,
        })
        rows.push(...page.items)
        cursor = page.next_cursor ?? null

        if (rows.length >= MAX_ROWS) {
          truncated = true
          break
        }
        if (cursor) toast.loading(`Descargando… ${rows.length} filas`, { id: toastId })
      } while (cursor)

      if (rows.length === 0) {
        toast.error("No hay filas que exportar con el filtro actual.", { id: toastId })
        return
      }

      downloadCsv(timestampedName(filePrefix), toCsv(rows, columns))

      toast.success(
        truncated
          ? `Exportadas ${rows.length} filas (límite alcanzado; afina el filtro para el resto)`
          : `${rows.length} fila${rows.length === 1 ? "" : "s"} exportada${rows.length === 1 ? "" : "s"}`,
        { id: toastId },
      )
    } catch {
      toast.error("No se pudo completar la exportación.", { id: toastId })
    } finally {
      setIsExporting(false)
    }
  }, [path, params, columns, filePrefix])

  return { exportCsv, isExporting }
}
