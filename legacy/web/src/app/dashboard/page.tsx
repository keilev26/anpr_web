import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Car, CheckCircle, XCircle, Clock, TrendingUp, TrendingDown } from "lucide-react"
import { Badge } from "@/components/ui/badge"

export default function DashboardPage() {
  const stats = [
    {
      title: "Vehículos Hoy",
      value: "1,284",
      change: "+12.5%",
      trend: "up",
      icon: Car,
    },
    {
      title: "Accesos Autorizados",
      value: "1,156",
      change: "+8.2%",
      trend: "up",
      icon: CheckCircle,
    },
    {
      title: "Accesos Denegados",
      value: "128",
      change: "-3.1%",
      trend: "down",
      icon: XCircle,
    },
    {
      title: "Tiempo Promedio",
      value: "2.4s",
      change: "-0.3s",
      trend: "down",
      icon: Clock,
    },
  ]

  const recentActivity = [
    { plate: "ABC-123", time: "14:32:15", status: "authorized", type: "Docente" },
    { plate: "XYZ-789", time: "14:31:48", status: "authorized", type: "Estudiante" },
    { plate: "DEF-456", time: "14:30:22", status: "denied", type: "Desconocido" },
    { plate: "GHI-321", time: "14:29:55", status: "authorized", type: "Administrativo" },
    { plate: "JKL-654", time: "14:28:33", status: "authorized", type: "Visitante" },
  ]

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Panel general</h1>
          <p className="text-muted-foreground">Monitoreo en tiempo real del sistema ANPR</p>
        </div>
        <Badge variant="outline" className="gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
          </span>
          Sistema Activo
        </Badge>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              <p className="text-xs text-muted-foreground flex items-center gap-1 mt-1">
                {stat.trend === "up" ? (
                  <TrendingUp className="h-3 w-3 text-green-500" />
                ) : (
                  <TrendingDown className="h-3 w-3 text-red-500" />
                )}
                <span className={stat.trend === "up" ? "text-green-500" : "text-red-500"}>{stat.change}</span> desde
                ayer
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Actividad Reciente</CardTitle>
            <CardDescription>Últimos accesos registrados en tiempo real</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {recentActivity.map((activity, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/50 border border-border/50"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-background border border-border">
                      <Car className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{activity.plate}</p>
                      <p className="text-xs text-muted-foreground">{activity.type}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground">{activity.time}</span>
                    <Badge variant={activity.status === "authorized" ? "default" : "destructive"} className="text-xs">
                      {activity.status === "authorized" ? "Autorizado" : "Denegado"}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Estado del Sistema</CardTitle>
            <CardDescription>Monitoreo de componentes críticos</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {[
                { name: "Cámara Principal", status: "online", uptime: "99.9%" },
                { name: "Procesamiento OCR", status: "online", uptime: "99.7%" },
                { name: "Base de Datos", status: "online", uptime: "100%" },
                { name: "Sistema de Barrera", status: "online", uptime: "99.8%" },
              ].map((component, index) => (
                <div key={index} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-2 w-2 rounded-full bg-green-500" />
                    <span className="text-sm font-medium">{component.name}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground">Uptime: {component.uptime}</span>
                    <Badge variant="outline" className="text-xs">
                      {component.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
