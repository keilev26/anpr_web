import { useEffect, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { Plus, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { api, HttpError } from "@/lib/api"
import { normalizePlate, PLATE_RE } from "@/lib/format"
import { ROLE_LABELS, type Car, type Role, type UserWithCars } from "@/types/api"

const schema = z.object({
  name: z.string().min(1, "El nombre es obligatorio"),
  email: z.string().email("Correo inválido"),
  phone: z.string().optional(),
  role: z.enum(["student", "teacher", "administrator"]),
  is_active: z.boolean(),
})
type FormValues = z.infer<typeof schema>

const EMPTY: FormValues = {
  name: "", email: "", phone: "", role: "student", is_active: true,
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Ausente = modo alta. Presente = modo edición. */
  user?: UserWithCars | null
}

export function UserFormDialog({ open, onOpenChange, user }: Props) {
  const isEdit = Boolean(user)
  const qc = useQueryClient()

  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: EMPTY })

  // Las placas no son campos del formulario: son un recurso aparte (/cars).
  // Se acumulan los cambios y se aplican al guardar, para que "Cancelar" de verdad cancele.
  const [plates, setPlates] = useState<string[]>([])
  const [existing, setExisting] = useState<Car[]>([])
  const [removedCarIds, setRemovedCarIds] = useState<number[]>([])
  const [plateDraft, setPlateDraft] = useState("")
  const [plateError, setPlateError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setPlates([])
    setRemovedCarIds([])
    setPlateDraft("")
    setPlateError(null)
    if (user) {
      form.reset({
        name: user.name, email: user.email, phone: user.phone ?? "",
        role: user.role, is_active: user.is_active,
      })
      setExisting(user.cars)
    } else {
      form.reset(EMPTY)
      setExisting([])
    }
  }, [open, user, form])

  const visibleExisting = existing.filter((c) => !removedCarIds.includes(c.id))
  const totalPlates = visibleExisting.length + plates.length

  function addPlate() {
    const p = normalizePlate(plateDraft)
    if (!PLATE_RE.test(p)) return setPlateError("Formato esperado: ABC-123")
    if (plates.includes(p) || visibleExisting.some((c) => c.plate === p)) {
      return setPlateError("Esa placa ya está en la lista")
    }
    setPlates((prev) => [...prev, p])
    setPlateDraft("")
    setPlateError(null)
  }

  const save = useMutation({
    mutationFn: async (values: FormValues) => {
      if (!isEdit) {
        return api.post<UserWithCars>("/users", {
          name: values.name, email: values.email,
          phone: values.phone || undefined, role: values.role, plates,
        })
      }
      const id = user!.id
      const updated = await api.patch<UserWithCars>(`/users/${id}`, {
        name: values.name, email: values.email,
        phone: values.phone || undefined, role: values.role, is_active: values.is_active,
      })
      // Las placas se sincronizan después: si una falla, el usuario ya quedó guardado
      // y el error indica exactamente qué placa no se pudo aplicar.
      for (const carId of removedCarIds) await api.delete<void>(`/cars/${carId}`)
      for (const plate of plates) await api.post<Car>("/cars", { plate, user_id: id })
      return updated
    },
    onSuccess: (saved) => {
      void qc.invalidateQueries({ queryKey: ["users"] })
      onOpenChange(false)
      toast.success(isEdit ? `${saved.name} actualizado` : `${saved.name} registrado`)
    },
    onError: (err) => {
      toast.error(
        err instanceof HttpError && err.status === 409
          ? err.detail
          : `No se pudo ${isEdit ? "actualizar" : "registrar"} el usuario.`,
      )
    },
  })

  function onSubmit(values: FormValues) {
    if (!isEdit && totalPlates === 0) {
      return setPlateError("Registra al menos una placa")
    }
    save.mutate(values)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Editar a ${user!.name}` : "Registrar usuario y placa"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Los cambios se aplican al guardar."
              : "El usuario y sus placas se crean juntos o no se crea nada."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div className="space-y-2">
            <Label htmlFor="name">Nombre completo</Label>
            <Input id="name" {...form.register("name")} />
            {form.formState.errors.name && (
              <p className="text-sm text-destructive">{form.formState.errors.name.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Correo electrónico</Label>
            <Input id="email" type="email" {...form.register("email")} />
            {form.formState.errors.email && (
              <p className="text-sm text-destructive">{form.formState.errors.email.message}</p>
            )}
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="phone">Teléfono</Label>
              <Input id="phone" {...form.register("phone")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role">Rol</Label>
              <Select
                value={form.watch("role")}
                onValueChange={(v) => form.setValue("role", v as Role)}
              >
                <SelectTrigger id="role" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(Object.keys(ROLE_LABELS) as Role[]).map((r) => (
                    <SelectItem key={r} value={r}>{ROLE_LABELS[r]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {isEdit && (
            <div className="space-y-2">
              <Label htmlFor="status">Estado</Label>
              <Select
                value={form.watch("is_active") ? "active" : "inactive"}
                onValueChange={(v) => form.setValue("is_active", v === "active")}
              >
                <SelectTrigger id="status" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Activo</SelectItem>
                  <SelectItem value="inactive">Inactivo — sin acceso a la puerta</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="plate">Placas</Label>
            <div className="flex gap-2">
              <Input
                id="plate"
                placeholder="ABC-123"
                className="font-mono"
                value={plateDraft}
                onChange={(e) => {
                  setPlateDraft(normalizePlate(e.target.value))
                  setPlateError(null)
                }}
                onKeyDown={(e) => {
                  // Enter agrega la placa; sin esto enviaría el formulario entero.
                  if (e.key === "Enter") {
                    e.preventDefault()
                    addPlate()
                  }
                }}
              />
              <Button type="button" variant="outline" onClick={addPlate} aria-label="Agregar placa">
                <Plus className="h-4 w-4" />
              </Button>
            </div>
            {plateError && <p className="text-sm text-destructive">{plateError}</p>}

            {totalPlates > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {visibleExisting.map((c) => (
                  <Badge key={c.id} variant="secondary" className="gap-1 font-mono">
                    {c.plate}
                    <button
                      type="button"
                      aria-label={`Quitar ${c.plate}`}
                      onClick={() => setRemovedCarIds((prev) => [...prev, c.id])}
                      className="rounded-sm hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
                {plates.map((p) => (
                  <Badge key={p} variant="outline" className="gap-1 font-mono">
                    {p}
                    <button
                      type="button"
                      aria-label={`Quitar ${p}`}
                      onClick={() => setPlates((prev) => prev.filter((x) => x !== p))}
                      className="rounded-sm hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Guardando…" : isEdit ? "Guardar cambios" : "Registrar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
