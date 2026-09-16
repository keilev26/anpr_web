import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Database, Download, Upload, RefreshCw, HardDrive } from "lucide-react"

export default function DatabasePage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Base de Datos</h1>
        <p className="text-muted-foreground">Gestión y mantenimiento de la base de datos</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Registros Totales</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">45,231</div>
            <p className="text-xs text-muted-foreground mt-1">Detecciones almacenadas</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Tamaño de BD</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">2.4 GB</div>
            <p className="text-xs text-muted-foreground mt-1">Espacio utilizado</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Último Backup</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">Hace 2h</div>
            <p className="text-xs text-muted-foreground mt-1">30/09/2025 12:00</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5 text-primary" />
              <CardTitle>Operaciones de Base de Datos</CardTitle>
            </div>
            <CardDescription>Acciones de mantenimiento y respaldo</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button className="w-full justify-start gap-2 bg-transparent" variant="outline">
              <Download className="h-4 w-4" />
              Exportar Base de Datos
            </Button>
            <Button className="w-full justify-start gap-2 bg-transparent" variant="outline">
              <Upload className="h-4 w-4" />
              Importar Datos
            </Button>
            <Button className="w-full justify-start gap-2 bg-transparent" variant="outline">
              <RefreshCw className="h-4 w-4" />
              Crear Backup Manual
            </Button>
            <Button className="w-full justify-start gap-2 bg-transparent" variant="outline">
              <HardDrive className="h-4 w-4" />
              Optimizar Base de Datos
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Estado de la Base de Datos</CardTitle>
            <CardDescription>Información del sistema de almacenamiento</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Estado de Conexión</span>
              <Badge variant="default">Conectado</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Tipo de Base de Datos</span>
              <Badge variant="outline">PostgreSQL</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Versión</span>
              <Badge variant="outline">15.3</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Backup Automático</span>
              <Badge variant="default">Habilitado</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Frecuencia de Backup</span>
              <Badge variant="outline">Cada 6 horas</Badge>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
