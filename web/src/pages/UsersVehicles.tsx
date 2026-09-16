import { useState } from "react"
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Search, UserPlus, Trash2, Pencil, Download } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { InfiniteFooter } from "@/components/InfiniteFooter"
import { UserFormDialog } from "@/components/UserFormDialog"
import { useDebounce } from "@/hooks/useDebounce"
import { useCsvExport } from "@/hooks/useCsvExport"
import type { CsvColumn } from "@/lib/csv"
import { api } from "@/lib/api"
import { ROLE_LABELS, type Page, type Role, type UserWithCars } from "@/types/api"
import { formatDateTime } from "@/lib/format"

const PAGE_SIZE = 20

const CSV_COLUMNS: CsvColumn<UserWithCars>[] = [
  { header: "ID", value: (u) => u.id },
  { header: "Nombre", value: (u) => u.name },
  { header: "Correo", value: (u) => u.email },
  { header: "Telefono", value: (u) => u.phone ?? "" },
  { header: "Rol", value: (u) => ROLE_LABELS[u.role] },
  { header: "Estado", value: (u) => (u.is_active ? "Activo" : "Inactivo") },
  // Varias placas en una celda: separadas por espacio, no por el separador CSV.
  { header: "Placas", value: (u) => u.cars.map((c) => c.plate).join(" ") },
  { header: "Cantidad de placas", value: (u) => u.cars.length },
  { header: "Registrado", value: (u) => (u.created_at ? formatDateTime(u.created_at) : "") },
]

export default function UsersVehiclesPage() {
  const [search, setSearch] = useState("")
  const [role, setRole] = useState<Role | "all">("all")
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<UserWithCars | null>(null)
  const [toDelete, setToDelete] = useState<UserWithCars | null>(null)
  const qc = useQueryClient()

  const q = useDebounce(search)

  const {
    data, isPending, isError, refetch,
    fetchNextPage, hasNextPage, isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["users", { q, role }],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api.get<Page<UserWithCars>>("/users", {
        q: q || undefined,
        role: role === "all" ? undefined : role,
        limit: PAGE_SIZE,
        cursor: pageParam ?? undefined,
      }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })

  const deleteUser = useMutation({
    mutationFn: (id: number) => api.delete<void>(`/users/${id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["users"] })
      setToDelete(null)
      toast.success("Usuario eliminado")
    },
    onError: () => toast.error("No se pudo eliminar el usuario."),
  })

  const users = data?.pages.flatMap((p) => p.items) ?? []

  const { exportCsv, isExporting } = useCsvExport<UserWithCars>({
    path: "/users",
    params: { q: q || undefined, role: role === "all" ? undefined : role },
    columns: CSV_COLUMNS,
    filePrefix: "anpr-usuarios",
  })

  function openCreate() {
    setEditing(null)
    setFormOpen(true)
  }
  function openEdit(u: UserWithCars) {
    setEditing(u)
    setFormOpen(true)
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Usuarios y Placas</h1>
          <p className="text-muted-foreground">Lista blanca de acceso a la Puerta 2</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => void exportCsv()}
            disabled={isExporting || users.length === 0}
          >
            <Download className="h-4 w-4" />
            {isExporting ? "Exportando…" : "Exportar CSV"}
          </Button>
          <Button onClick={openCreate}>
            <UserPlus className="h-4 w-4" />
            Nuevo usuario
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Registrados</CardTitle>
          <CardDescription>
            {isPending ? "Cargando…" : "Busca por nombre, correo, teléfono o placa"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Buscar…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
                aria-label="Buscar usuarios"
              />
            </div>
            <Select value={role} onValueChange={(v) => setRole(v as Role | "all")}>
              <SelectTrigger className="sm:w-52" aria-label="Filtrar por rol">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos los roles</SelectItem>
                {(Object.keys(ROLE_LABELS) as Role[]).map((r) => (
                  <SelectItem key={r} value={r}>{ROLE_LABELS[r]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {isError ? (
            <div className="rounded-lg border border-destructive/50 p-6 text-center">
              <p className="text-sm text-destructive">Error al cargar los usuarios</p>
              <Button variant="outline" size="sm" className="mt-3" onClick={() => void refetch()}>
                Reintentar
              </Button>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Nombre</TableHead>
                      <TableHead>Correo</TableHead>
                      <TableHead>Rol</TableHead>
                      <TableHead>Placas</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead className="w-24" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {isPending ? (
                      Array.from({ length: 6 }, (_, i) => (
                        <TableRow key={i}>
                          <TableCell colSpan={6}><Skeleton className="h-6 w-full" /></TableCell>
                        </TableRow>
                      ))
                    ) : users.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                          {q || role !== "all"
                            ? "Ningún usuario coincide con el filtro."
                            : "Todavía no hay usuarios."}
                        </TableCell>
                      </TableRow>
                    ) : (
                      users.map((u) => (
                        <TableRow key={u.id} className={u.is_active ? "" : "opacity-60"}>
                          <TableCell className="font-medium">{u.name}</TableCell>
                          <TableCell className="text-muted-foreground">{u.email}</TableCell>
                          <TableCell>
                            <Badge variant="secondary">{ROLE_LABELS[u.role]}</Badge>
                          </TableCell>
                          <TableCell>
                            <div className="flex flex-wrap gap-1">
                              {u.cars.length === 0 ? (
                                <span className="text-muted-foreground">—</span>
                              ) : (
                                u.cars.map((c) => (
                                  <Badge key={c.id} variant="outline" className="font-mono">
                                    {c.plate}
                                  </Badge>
                                ))
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <span
                              className={
                                u.is_active ? "text-sm" : "text-sm text-muted-foreground"
                              }
                            >
                              {u.is_active ? "Activo" : "Inactivo"}
                            </span>
                          </TableCell>
                          <TableCell>
                            <div className="flex justify-end gap-1">
                              <Button
                                variant="ghost" size="icon"
                                aria-label={`Editar a ${u.name}`}
                                onClick={() => openEdit(u)}
                              >
                                <Pencil className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost" size="icon"
                                aria-label={`Eliminar a ${u.name}`}
                                onClick={() => setToDelete(u)}
                              >
                                <Trash2 className="h-4 w-4 text-destructive" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>

              {!isPending && users.length > 0 && (
                <InfiniteFooter
                  hasNextPage={hasNextPage}
                  isFetchingNextPage={isFetchingNextPage}
                  fetchNextPage={() => void fetchNextPage()}
                  loaded={users.length}
                  noun="usuario"
                />
              )}
            </>
          )}
        </CardContent>
      </Card>

      <UserFormDialog open={formOpen} onOpenChange={setFormOpen} user={editing} />

      {/* Confirmación antes de borrar: el legacy eliminaba sin preguntar. */}
      <Dialog open={toDelete !== null} onOpenChange={(open) => !open && setToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>¿Eliminar a {toDelete?.name}?</DialogTitle>
            <DialogDescription>
              Se eliminarán también sus {toDelete?.cars.length ?? 0} placa(s) y perderá el acceso a
              la puerta. Esta acción no se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setToDelete(null)}>Cancelar</Button>
            <Button
              variant="destructive"
              disabled={deleteUser.isPending}
              onClick={() => toDelete && deleteUser.mutate(toDelete.id)}
            >
              {deleteUser.isPending ? "Eliminando…" : "Eliminar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
