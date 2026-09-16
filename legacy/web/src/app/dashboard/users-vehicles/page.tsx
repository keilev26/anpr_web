"use client"

import { useEffect, useState, useMemo } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { UserPlus, Search, Edit, Trash2, Car } from "lucide-react"

// ===== Tipos que la UI REALMENTE usa =====
type UIUser = {
  id: string
  name: string
  phone: string
  email: string
  role: "admin" | "operator" | "viewer" | string
  plate: string
  status: "active" | "inactive"
}

// Adaptador: del backend (Nombre, Telefono, Correo, Rol, Placa, Estado) a la UI
function adaptToUI(v: any): UIUser {
  // Soporta: {Nombre, Telefono, Correo, Rol, Placa, Estado}  o  {name, phone, email, role, plate}
  const estadoRaw = v?.Estado ?? v?.estado
  const estado = String(estadoRaw ?? "").toLowerCase()

  return {
    id: String(v?.id ?? ""),
    name: String(v?.Nombre ?? v?.name ?? ""),
    phone: String(v?.Telefono ?? v?.phone ?? ""),
    email: String(v?.Correo ?? v?.email ?? ""),
    role: String(v?.Rol ?? v?.role ?? "").toLowerCase(),
    plate: String(v?.Placa ?? v?.plate ?? ""),
    status: estado === "inactivo" ? "inactive" : "active", // si no viene, será "active"
  }
}


// Estado del formulario (coincide con lo que dibuja el form)
type FormState = {
  name: string
  phone: string
  email: string
  role: "administrator" | "teacher" | "student"
  plate: string
}

const EMPTY_FORM: FormState = { name: "", phone: "", email: "", role: "student", plate: "" }

export default function UsersVehiclesPage() {
  const [searchQuery, setSearchQuery] = useState("")
  const [users, setUsers] = useState<UIUser[]>([])        // ← nunca null
  const [newUser, setNewUser] = useState<FormState>(EMPTY_FORM)
  useEffect(() => {
  const controller = new AbortController()
  ;(async () => {
    try {
      const res = await fetch("/api/list_car", { signal: controller.signal, cache: "no-store" })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const raw = await res.json()
      const list: any[] = Array.isArray(raw) ? raw : (raw?.vehicles ?? [])
      setUsers(list.map(adaptToUI))
    } catch {
      // opcional: setear error
    }
  })()
  return () => controller.abort()
}, [])

  const filteredUsers = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return users
    return users.filter((u) =>
      u.name.toLowerCase().includes(q) ||
      u.phone.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      String(u.role).toLowerCase().includes(q) ||
      u.plate.toLowerCase().includes(q) ||
      u.status.toLowerCase().includes(q)
    )
  }, [users, searchQuery])

  const handleAddUser = async () => {
  const { name, phone, email, role, plate } = newUser
  if (!name || !phone || !email || !plate) return

  try {
    const r = await fetch("/api/list_car", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        phone,
        email,
        role,
        plate: plate.toUpperCase(),
      }),
    })

    if (!r.ok) {
      const err = await r.json().catch(() => ({}))
      throw new Error(err?.error || `HTTP ${r.status}`)
    }

    const { user, car } = await r.json()

    // Actualiza tu UI con lo devuelto por el backend
    const uiUser: UIUser = {
      id: String(user.id),
      name: user.name,
      phone: user.phone,
      email: user.email,
      role: (user.role ?? role ?? "viewer").toLowerCase(),
      plate: car?.plate ?? plate.toUpperCase(),
      status: "active",
    }

    setUsers(prev => [uiUser, ...prev])
    setNewUser(EMPTY_FORM)
  } catch (e: any) {
    console.error("Create user+car failed:", e?.message || e)
    // aquí puedes mostrar un toast/error UI si quieres
  }
}

const handleDelete = async (id: string) => {
  if (!confirm("¿Seguro que deseas eliminar este usuario?")) return

  try {
    const r = await fetch("/api/list_car", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    })

    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    setUsers(prev => prev.filter(u => u.id !== id))
  } catch (e: any) {
    console.error("Delete failed:", e.message)
    alert("Error al eliminar el usuario")
  }
}


  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Usuarios y Placas</h1>
          <p className="text-muted-foreground">Gestión de usuarios con sus vehículos autorizados</p>
        </div>
        <Dialog>
          <DialogTrigger asChild>
            <Button className="gap-2">
              <UserPlus className="h-4 w-4" />
              Nuevo Usuario
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Agregar Usuario y Placa</DialogTitle>
              <DialogDescription>Ingresa los datos del usuario y su placa de vehículo</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="new-name">Nombre Completo</Label>
                <Input id="new-name" placeholder="Juan Pérez"
                  value={newUser.name}
                  onChange={(e) => setNewUser({ ...newUser, name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-phone">Teléfono</Label>
                <Input id="new-phone" placeholder="+51 999 123 456"
                  value={newUser.phone}
                  onChange={(e) => setNewUser({ ...newUser, phone: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-email">Correo Electrónico</Label>
                <Input id="new-email" type="email" placeholder="usuario@uni.edu.pe"
                  value={newUser.email}
                  onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-role">Rol</Label>
                <Select value={newUser.role} onValueChange={(value) => setNewUser({ ...newUser, role: value as FormState["role"] })}>
                  <SelectTrigger id="new-role"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="administrator">Personal</SelectItem>
                    <SelectItem value="teacher">Catedratico</SelectItem>
                    <SelectItem value="student">Estudiante</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="new-plate">Placa del Vehículo</Label>
                <Input id="new-plate" placeholder="ABC-1234"
                  value={newUser.plate}
                  onChange={(e) => setNewUser({ ...newUser, plate: e.target.value.toUpperCase() })}
                />
              </div>
              <Button className="w-full" onClick={handleAddUser}>Agregar Usuario</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <CardTitle>Lista de Usuarios y Vehículos</CardTitle>
              <CardDescription>Administra usuarios con sus placas autorizadas</CardDescription>
            </div>
            <div className="relative md:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por nombre, email o placa..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Teléfono</TableHead>
                  <TableHead>Correo</TableHead>
                  <TableHead>Rol</TableHead>
                  <TableHead><div className="flex items-center gap-2"><Car className="h-4 w-4" />Placa</div></TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredUsers.length > 0 ? (
                  filteredUsers.map((user) => (
                    <TableRow key={`${user.id}-${user.plate}`}>
                      <TableCell className="font-medium">{user.name}</TableCell>
                      <TableCell className="text-muted-foreground">{user.phone}</TableCell>
                      <TableCell className="text-muted-foreground">{user.email}</TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {user.role === "administrator" ? "Personal" : user.role === "teacher" ? "Catedratico" : "Estudiante"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30 font-mono">
                          {user.plate}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={user.status === "active" ? "default" : "secondary"}>
                          {user.status === "active" ? "Activo" : "Inactivo"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button variant="ghost" size="sm"><Edit className="h-4 w-4" /></Button>
                          <Button variant="ghost" size="sm" onClick={() => handleDelete(user.id)}><Trash2 className="h-4 w-4" /></Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                      No se encontraron usuarios
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
