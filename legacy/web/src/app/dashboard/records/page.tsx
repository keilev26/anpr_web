"use client"

import { useEffect, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Search, Filter, Download, Eye } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

export type AnprRecord = {
  id: string
  plate: string
  datetime: string
  status: "authorized" | "denied"
  type: string
  confidence: number
  image?: string | null
}

// Mapea la respuesta exacta que envías: { vehicles: [ { id, plate, datetime, authorization, type } ] }
function adaptRecord(v: any): AnprRecord {
  return {
    id: String(v.id ?? ""),
    plate: String(v.plate ?? ""),
    datetime: String(v.datetime ?? ""),
    status: (v.authorization === "authorized" ? "authorized" : "denied") as AnprRecord["status"],
    type: String(v.type ?? "unknown"),
    confidence: 0, // tu backend no envía confidence; puedes cambiar cuando lo tengas
    image: null,
  }
}

export default function RecordsPage() {
  const [records, setRecords] = useState<AnprRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [searchQuery, setSearchQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  const [selectedRecord, setSelectedRecord] = useState<AnprRecord | null>(null)
    useEffect(() => {
    const controller = new AbortController()
    ;(async () => {
      try {
        setLoading(true)
        setError(null)
        const res = await fetch("/api/event", { signal: controller.signal, cache: "no-store" })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const raw = await res.json()
        const list: any[] = raw?.vehicles ?? []
        setRecords(list.map(adaptRecord))
      } catch (e: any) {
        if (e?.name !== "AbortError") setError(e?.message ?? "Error al obtener los registros")
      } finally {
        setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [])



  const filteredRecords = records.filter((record) => {
    const matchesSearch = record.plate.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesStatus = statusFilter === "all" || record.status === statusFilter
    return matchesSearch && matchesStatus
  })

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground">Cargando registros…</div>
  }

  if (error) {
    return <div className="p-6 text-sm text-red-600">{error}</div>
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Registros ANPR</h1>
          <p className="text-muted-foreground">Historial completo de detecciones de placas</p>
        </div>
        <Button className="gap-2">
          <Download className="h-4 w-4" />
          Exportar
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <CardTitle>Registros Recientes</CardTitle>
              <CardDescription>Búsqueda y filtrado de detecciones</CardDescription>
            </div>
            <div className="flex flex-col gap-2 md:flex-row md:items-center">
              <div className="relative flex-1 md:w-64">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Buscar por placa..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-full md:w-[180px]">
                  <Filter className="h-4 w-4 mr-2" />
                  <SelectValue placeholder="Estado" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="authorized">Autorizados</SelectItem>
                  <SelectItem value="denied">Denegados</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Placa</TableHead>
                  <TableHead>Fecha y Hora</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Confianza</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRecords.map((record) => (
                  <TableRow key={record.id}>
                    <TableCell className="font-mono text-xs">{record.id}</TableCell>
                    <TableCell className="font-semibold">{record.plate}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{record.datetime}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{record.type}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={record.status === "authorized" ? "default" : "destructive"}>
                        {record.status === "authorized" ? "Autorizado" : "Denegado"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm font-medium">{record.confidence ? `${record.confidence}%` : "—"}</span>
                    </TableCell>
                    <TableCell className="text-right">
                      <Dialog>
                        <DialogTrigger asChild>
                          <Button variant="ghost" size="sm" className="gap-2" onClick={() => setSelectedRecord(record)}>
                            <Eye className="h-4 w-4" />
                            Ver
                          </Button>
                        </DialogTrigger>
                        <DialogContent className="max-w-2xl">
                          <DialogHeader>
                            <DialogTitle>Detalles del Registro</DialogTitle>
                            <DialogDescription>Información completa de la detección</DialogDescription>
                          </DialogHeader>
                          {selectedRecord && (
                            <div className="space-y-4">
                              <div className="rounded-lg border overflow-hidden">
                                <img
                                  src={selectedRecord.image || "/placeholder.svg"}
                                  alt={`Placa ${selectedRecord.plate}`}
                                  className="w-full h-auto"
                                />
                              </div>
                              <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-1">
                                  <p className="text-sm text-muted-foreground">ID de Registro</p>
                                  <p className="font-mono font-semibold">{selectedRecord.id}</p>
                                </div>
                                <div className="space-y-1">
                                  <p className="text-sm text-muted-foreground">Placa</p>
                                  <p className="font-semibold text-lg">{selectedRecord.plate}</p>
                                </div>
                                <div className="space-y-1">
                                  <p className="text-sm text-muted-foreground">Fecha y Hora</p>
                                  <p className="font-medium">{selectedRecord.datetime}</p>
                                </div>
                                <div className="space-y-1">
                                  <p className="text-sm text-muted-foreground">Tipo de Vehículo</p>
                                  <Badge variant="outline">{selectedRecord.type}</Badge>
                                </div>
                                <div className="space-y-1">
                                  <p className="text-sm text-muted-foreground">Estado</p>
                                  <Badge variant={selectedRecord.status === "authorized" ? "default" : "destructive"}>
                                    {selectedRecord.status === "authorized" ? "Autorizado" : "Denegado"}
                                  </Badge>
                                </div>
                                <div className="space-y-1">
                                  <p className="text-sm text-muted-foreground">Confianza OCR</p>
                                  <p className="font-semibold">{selectedRecord.confidence ? `${selectedRecord.confidence}%` : "—"}</p>
                                </div>
                              </div>
                            </div>
                          )}
                        </DialogContent>
                      </Dialog>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-muted-foreground">
              Mostrando {filteredRecords.length} de {records.length} registros
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled>
                Anterior
              </Button>
              <Button variant="outline" size="sm">
                Siguiente
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
