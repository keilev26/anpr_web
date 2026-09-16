import { useState } from "react"
import { useInfiniteQuery } from "@tanstack/react-query"
import { Search, Eye, RefreshCw, Download } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { InfiniteFooter } from "@/components/InfiniteFooter"
import { useDebounce } from "@/hooks/useDebounce"
import { useCsvExport } from "@/hooks/useCsvExport"
import type { CsvColumn } from "@/lib/csv"
import { api } from "@/lib/api"
import { formatConfidence, formatDateTime } from "@/lib/format"
import { ROLE_LABELS, type AnprEvent, type Page } from "@/types/api"

type StatusFilter = "all" | "authorized" | "denied"

const PAGE_SIZE = 25

const CSV_COLUMNS: CsvColumn<AnprEvent>[] = [
  { header: "ID", value: (e) => e.id },
  { header: "Placa", value: (e) => e.plate },
  { header: "Fecha y hora (Lima)", value: (e) => formatDateTime(e.detected_at) },
  { header: "Fecha y hora (UTC)", value: (e) => e.detected_at },
  { header: "Estado", value: (e) => (e.authorized ? "Autorizado" : "Denegado") },
  { header: "Propietario", value: (e) => e.user?.name ?? "" },
  { header: "Correo", value: (e) => e.user?.email ?? "" },
  { header: "Rol", value: (e) => (e.user ? ROLE_LABELS[e.user.role] : "Desconocido") },
  { header: "Confianza", value: (e) => (e.confidence == null ? "" : e.confidence.toFixed(3)) },
  { header: "Porton abrio", value: (e) => (e.gate_opened == null ? "" : e.gate_opened ? "Si" : "No") },
  { header: "Latencia (ms)", value: (e) => e.latency_ms ?? "" },
  { header: "Camara", value: (e) => e.camera_id ?? "" },
]

export default function RecordsPage() {
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState<StatusFilter>("all")
  const [selected, setSelected] = useState<AnprEvent | null>(null)

  const plate = useDebounce(search)

  /**
   * Los filtros van al servidor, no se aplican sobre un array en memoria:
   * el legacy traía la tabla `event_detection` completa y filtraba en el
   * navegador, lo que no escala con meses de detecciones.
   */
  const {
    data, isPending, isFetching, isError, error, refetch,
    fetchNextPage, hasNextPage, isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["events", { plate, status }],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api.get<Page<AnprEvent>>("/events", {
        plate: plate || undefined,
        authorized: status === "all" ? undefined : status === "authorized",
        limit: PAGE_SIZE,
        cursor: pageParam ?? undefined,
      }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    // Auto-refresco solo mientras se ve la primera página. Con varias páginas
    // cargadas, refetchInterval las repetiría TODAS cada 15 s y además haría
    // saltar la lista bajo el cursor del operador.
    refetchInterval: (query) =>
      (query.state.data?.pages.length ?? 0) <= 1 ? 15_000 : false,
  })

  const events = data?.pages.flatMap((p) => p.items) ?? []

  // Exporta todo lo que cumple el filtro, no solo las páginas cargadas.
  const { exportCsv, isExporting } = useCsvExport<AnprEvent>({
    path: "/events",
    params: {
      plate: plate || undefined,
      authorized: status === "all" ? undefined : status === "authorized",
    },
    columns: CSV_COLUMNS,
    filePrefix: "anpr-registros",
  })

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Registros ANPR</h1>
          <p className="text-muted-foreground">Historial de detecciones en la Puerta 2</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline" size="sm"
            onClick={() => void exportCsv()}
            disabled={isExporting || events.length === 0}
          >
            <Download className="h-4 w-4" />
            {isExporting ? "Exportando…" : "Exportar CSV"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching}>
            <RefreshCw className={isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            Actualizar
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Detecciones</CardTitle>
          <CardDescription>
            {isPending ? "Cargando…" : "Detecciones más recientes primero"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Buscar por placa…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
                aria-label="Buscar por placa"
              />
            </div>
            <Select value={status} onValueChange={(v) => setStatus(v as StatusFilter)}>
              <SelectTrigger className="sm:w-48" aria-label="Filtrar por estado">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="authorized">Autorizados</SelectItem>
                <SelectItem value="denied">Denegados</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {isError ? (
            <div className="rounded-lg border border-destructive/50 p-6 text-center">
              <p className="text-sm text-destructive">
                {error instanceof Error ? error.message : "Error al cargar los registros"}
              </p>
              <Button variant="outline" size="sm" className="mt-3" onClick={() => void refetch()}>
                Reintentar
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Placa</TableHead>
                    <TableHead>Fecha y hora</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead className="text-right">Confianza</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isPending ? (
                    Array.from({ length: 5 }, (_, i) => (
                      <TableRow key={i}>
                        <TableCell colSpan={6}>
                          <Skeleton className="h-6 w-full" />
                        </TableCell>
                      </TableRow>
                    ))
                  ) : events.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                        {plate || status !== "all"
                          ? "Ningún registro coincide con el filtro."
                          : "Todavía no hay detecciones."}
                      </TableCell>
                    </TableRow>
                  ) : (
                    events.map((ev) => (
                      <TableRow key={ev.id}>
                        <TableCell className="font-mono font-medium">{ev.plate}</TableCell>
                        <TableCell className="text-muted-foreground">
                          {formatDateTime(ev.detected_at)}
                        </TableCell>
                        <TableCell>
                          <Badge variant={ev.authorized ? "default" : "destructive"}>
                            {ev.authorized ? "Autorizado" : "Denegado"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {ev.user ? ROLE_LABELS[ev.user.role] : "Desconocido"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-muted-foreground">
                          {formatConfidence(ev.confidence)}
                        </TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Ver detalle de ${ev.plate}`}
                            onClick={() => setSelected(ev)}
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          )}

          {!isPending && !isError && events.length > 0 && (
            <InfiniteFooter
              hasNextPage={hasNextPage}
              isFetchingNextPage={isFetchingNextPage}
              fetchNextPage={() => void fetchNextPage()}
              loaded={events.length}
              noun="registro"
            />
          )}
        </CardContent>
      </Card>

      <Dialog open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-mono">{selected?.plate}</DialogTitle>
            <DialogDescription>
              {selected && formatDateTime(selected.detected_at)}
            </DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="space-y-4">
              {selected.image_url ? (
                <img
                  src={selected.image_url}
                  alt={`Detección de ${selected.plate}`}
                  className="w-full rounded-lg border"
                />
              ) : (
                <div className="rounded-lg border border-dashed py-10 text-center text-sm text-muted-foreground">
                  Sin imagen registrada
                </div>
              )}
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-muted-foreground">Estado</dt>
                  <dd>{selected.authorized ? "Autorizado" : "Denegado"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Portón</dt>
                  <dd>
                    {selected.gate_opened == null
                      ? "—"
                      : selected.gate_opened
                        ? "Abrió"
                        : "No abrió"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Confianza</dt>
                  <dd className="tabular-nums">{formatConfidence(selected.confidence)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Latencia</dt>
                  <dd className="tabular-nums">
                    {selected.latency_ms == null ? "—" : `${selected.latency_ms} ms`}
                  </dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-muted-foreground">Propietario</dt>
                  <dd>
                    {selected.user
                      ? `${selected.user.name} — ${ROLE_LABELS[selected.user.role]}`
                      : "Placa no registrada"}
                  </dd>
                </div>
              </dl>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
