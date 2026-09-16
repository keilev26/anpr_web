import { NavLink, useNavigate } from "react-router-dom"
import { Car, UserCheck, LogOut } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useAuth } from "@/auth/AuthContext"
import { ROLE_LABELS } from "@/types/api"

const navigation = [
  { name: "Registros ANPR", to: "/records", icon: Car },
  { name: "Usuarios y Placas", to: "/users-vehicles", icon: UserCheck },
]

export function Sidebar({ className }: { className?: string }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate("/login", { replace: true })
  }

  return (
    <div className={cn("flex h-full w-64 flex-col border-r border-border bg-sidebar", className)}>
      <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-6">
        <img src="/uni_logo.png" alt="UNI" width={40} height={40} />
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-sidebar-foreground">ANPR FIM UNI</span>
          <span className="text-xs text-sidebar-foreground/60">Puerta 2</span>
        </div>
      </div>

      <nav className="flex-1 space-y-1 p-4">
        {navigation.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.name}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-sidebar-border p-4">
        {user && (
          <div className="mb-2 px-3">
            <p className="truncate text-sm font-medium text-sidebar-foreground">{user.name}</p>
            <p className="truncate text-xs text-sidebar-foreground/60">{ROLE_LABELS[user.role]}</p>
          </div>
        )}
        <Button
          variant="ghost"
          className="w-full justify-start gap-3 text-sidebar-foreground/70 hover:text-sidebar-accent-foreground"
          onClick={handleLogout}
        >
          <LogOut className="h-4 w-4" />
          Cerrar Sesión
        </Button>
      </div>
    </div>
  )
}
