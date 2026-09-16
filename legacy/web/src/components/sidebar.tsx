"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import {
  LayoutDashboard,
  Car,
  BarChart3,
  Settings,
  Shield,
  Users,
  Database,
  LogOut,
  Video,
  UserCheck,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import Image from "next/image"

const navigation = [
  // { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  // { name: "Stream en Vivo", href: "/dashboard/stream", icon: Video },
  { name: "Registros ANPR", href: "/dashboard/records", icon: Car },
  // { name: "Estadísticas", href: "/dashboard/statistics", icon: BarChart3 },
  { name: "Usuarios y Placas", href: "/dashboard/users-vehicles", icon: UserCheck },
  // { name: "Usuarios", href: "/dashboard/users", icon: Users },
  // { name: "Base de Datos", href: "/dashboard/database", icon: Database },
  // { name: "Configuración", href: "/dashboard/settings", icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <div className="flex h-full w-64 flex-col border-r border-border bg-sidebar">
      <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-6">
        <div className="flex items-center justify-center w-10 h-10 ">
          {/* <Shield className="w-5 h-5 text-sidebar-primary" /> */}
          <Image src= "/uni_logo.png" alt="uni" width={40} height={40} />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-sidebar-foreground">ANPR FIM UNI</span>
          <span className="text-xs text-sidebar-foreground/60">Puerta 2</span>
        </div>
      </div>

      <nav className="flex-1 space-y-1 p-4">
        {navigation.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.name}
            </Link>
          )
        })}
      </nav>

      <div className="border-t border-sidebar-border p-4">
        <Button
          variant="ghost"
          className="w-full justify-start gap-3 text-sidebar-foreground/70 hover:text-sidebar-accent-foreground"
          onClick={() => (window.location.href = "/login")}
        >
          <LogOut className="h-4 w-4" />
          Cerrar Sesión
        </Button>
      </div>
    </div>
  )
}
