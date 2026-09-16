import { useEffect, useState } from "react"
import { Outlet, useLocation } from "react-router-dom"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { Menu, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sidebar } from "./Sidebar"

export function DashboardLayout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()

  // Al navegar desde el menú móvil, cerrarlo: si no, tapa la página a la que se fue.
  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  return (
    // h-dvh y no h-screen: en el navegador del celular, 100vh incluye la barra de
    // direcciones y el final de la página queda oculto detrás de ella.
    <div className="flex h-dvh overflow-hidden">
      <Sidebar className="hidden md:flex" />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-sidebar px-4 md:hidden">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Abrir menú"
            onClick={() => setMenuOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>
          <img src="/uni_logo.png" alt="" width={28} height={28} />
          <span className="text-sm font-semibold">ANPR FIM UNI</span>
        </header>

        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>

      {/* Menú lateral en celular. Dialog de Radix: cierra con Escape, retiene el foco
          y lo anuncia a lectores de pantalla. */}
      <DialogPrimitive.Root open={menuOpen} onOpenChange={setMenuOpen}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=open]:fade-in-0 md:hidden" />
          <DialogPrimitive.Content className="fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] shadow-lg outline-none data-[state=open]:animate-in data-[state=open]:slide-in-from-left md:hidden">
            <DialogPrimitive.Title className="sr-only">Menú de navegación</DialogPrimitive.Title>
            <DialogPrimitive.Description className="sr-only">
              Secciones del sistema y cierre de sesión
            </DialogPrimitive.Description>
            <Sidebar className="w-full" />
            <DialogPrimitive.Close asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Cerrar menú"
                className="absolute top-3 right-3"
              >
                <X className="h-5 w-5" />
              </Button>
            </DialogPrimitive.Close>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    </div>
  )
}
