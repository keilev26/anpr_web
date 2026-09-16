"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { Slider } from "@/components/ui/slider"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { Camera, Server, Bell, Shield, Database, Zap } from "lucide-react"

export default function SettingsPage() {
  const [ocrThreshold, setOcrThreshold] = useState([95])
  const [autoOpen, setAutoOpen] = useState(true)
  const [notifications, setNotifications] = useState(true)

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Configuración</h1>
        <p className="text-muted-foreground">Administración avanzada del sistema ANPR</p>
      </div>

      <Tabs defaultValue="system" className="space-y-4">
        <TabsList>
          <TabsTrigger value="system">Sistema</TabsTrigger>
          <TabsTrigger value="camera">Cámara</TabsTrigger>
          <TabsTrigger value="access">Control de Acceso</TabsTrigger>
          <TabsTrigger value="notifications">Notificaciones</TabsTrigger>
        </TabsList>

        <TabsContent value="system" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Server className="h-5 w-5 text-primary" />
                  <CardTitle>Configuración del Servidor</CardTitle>
                </div>
                <CardDescription>Parámetros de conexión y rendimiento</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="server-url">URL del Servidor</Label>
                  <Input id="server-url" defaultValue="https://anpr.fim.uni.edu.pe" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="api-key">API Key</Label>
                  <Input id="api-key" type="password" defaultValue="••••••••••••••••" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="timeout">Timeout (segundos)</Label>
                  <Input id="timeout" type="number" defaultValue="30" />
                </div>
                <Button className="w-full">Guardar Cambios</Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Database className="h-5 w-5 text-primary" />
                  <CardTitle>Base de Datos</CardTitle>
                </div>
                <CardDescription>Configuración de almacenamiento</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="db-host">Host</Label>
                  <Input id="db-host" defaultValue="localhost:5432" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="db-name">Nombre de la Base de Datos</Label>
                  <Input id="db-name" defaultValue="anpr_fim_uni" />
                </div>
                <div className="space-y-2">
                  <Label>Retención de Datos</Label>
                  <Select defaultValue="90">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="30">30 días</SelectItem>
                      <SelectItem value="90">90 días</SelectItem>
                      <SelectItem value="180">180 días</SelectItem>
                      <SelectItem value="365">1 año</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button className="w-full">Guardar Cambios</Button>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-primary" />
                <CardTitle>Rendimiento</CardTitle>
              </div>
              <CardDescription>Optimización del sistema</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Procesamiento en Paralelo</Label>
                    <p className="text-sm text-muted-foreground">Procesar múltiples placas simultáneamente</p>
                  </div>
                  <Switch defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Caché de Resultados</Label>
                    <p className="text-sm text-muted-foreground">Almacenar resultados para acceso rápido</p>
                  </div>
                  <Switch defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Compresión de Imágenes</Label>
                    <p className="text-sm text-muted-foreground">Reducir tamaño de almacenamiento</p>
                  </div>
                  <Switch defaultChecked />
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="camera" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Camera className="h-5 w-5 text-primary" />
                <CardTitle>Configuración de Cámara</CardTitle>
              </div>
              <CardDescription>Parámetros de captura y procesamiento de imagen</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="camera-ip">Dirección IP de la Cámara</Label>
                  <Input id="camera-ip" defaultValue="192.168.1.100" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="camera-port">Puerto</Label>
                  <Input id="camera-port" type="number" defaultValue="554" />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="resolution">Resolución</Label>
                <Select defaultValue="1080p">
                  <SelectTrigger id="resolution">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="720p">1280x720 (720p)</SelectItem>
                    <SelectItem value="1080p">1920x1080 (1080p)</SelectItem>
                    <SelectItem value="4k">3840x2160 (4K)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="fps">FPS (Cuadros por Segundo)</Label>
                <Select defaultValue="30">
                  <SelectTrigger id="fps">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="15">15 FPS</SelectItem>
                    <SelectItem value="30">30 FPS</SelectItem>
                    <SelectItem value="60">60 FPS</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-4">
                <div>
                  <Label>Umbral de Confianza OCR: {ocrThreshold[0]}%</Label>
                  <p className="text-sm text-muted-foreground mb-2">
                    Nivel mínimo de confianza para aceptar una detección
                  </p>
                  <Slider value={ocrThreshold} onValueChange={setOcrThreshold} min={80} max={100} step={1} />
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Detección Nocturna</Label>
                    <p className="text-sm text-muted-foreground">Ajuste automático para condiciones de poca luz</p>
                  </div>
                  <Switch defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Corrección de Perspectiva</Label>
                    <p className="text-sm text-muted-foreground">Ajustar ángulo de captura automáticamente</p>
                  </div>
                  <Switch defaultChecked />
                </div>
              </div>

              <Button className="w-full">Guardar Configuración</Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="access" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Shield className="h-5 w-5 text-primary" />
                <CardTitle>Control de Acceso</CardTitle>
              </div>
              <CardDescription>Reglas y permisos de entrada</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Apertura Automática</Label>
                    <p className="text-sm text-muted-foreground">Abrir barrera automáticamente para autorizados</p>
                  </div>
                  <Switch checked={autoOpen} onCheckedChange={setAutoOpen} />
                </div>
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Modo Estricto</Label>
                    <p className="text-sm text-muted-foreground">Requerir confirmación manual para visitantes</p>
                  </div>
                  <Switch />
                </div>
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Lista Negra Activa</Label>
                    <p className="text-sm text-muted-foreground">Bloquear placas en lista negra</p>
                  </div>
                  <Switch defaultChecked />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="access-hours">Horario de Acceso</Label>
                <div className="grid grid-cols-2 gap-2">
                  <Input id="access-start" type="time" defaultValue="06:00" />
                  <Input id="access-end" type="time" defaultValue="22:00" />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="max-attempts">Intentos Máximos</Label>
                <Input id="max-attempts" type="number" defaultValue="3" />
                <p className="text-sm text-muted-foreground">
                  Número de intentos fallidos antes de bloquear temporalmente
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="whitelist">Lista Blanca (Placas Autorizadas)</Label>
                <Textarea
                  id="whitelist"
                  placeholder="ABC-123&#10;XYZ-789&#10;DEF-456"
                  className="font-mono text-sm"
                  rows={5}
                />
              </div>

              <Button className="w-full">Guardar Configuración</Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notifications" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Bell className="h-5 w-5 text-primary" />
                <CardTitle>Notificaciones</CardTitle>
              </div>
              <CardDescription>Alertas y notificaciones del sistema</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Notificaciones Habilitadas</Label>
                    <p className="text-sm text-muted-foreground">Recibir alertas del sistema</p>
                  </div>
                  <Switch checked={notifications} onCheckedChange={setNotifications} />
                </div>
              </div>

              {notifications && (
                <>
                  <div className="space-y-4 pt-4 border-t">
                    <h3 className="font-medium">Tipos de Notificaciones</h3>
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label>Accesos Denegados</Label>
                          <p className="text-sm text-muted-foreground">Alertar cuando se deniegue un acceso</p>
                        </div>
                        <Switch defaultChecked />
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label>Placas Desconocidas</Label>
                          <p className="text-sm text-muted-foreground">Notificar placas no registradas</p>
                        </div>
                        <Switch defaultChecked />
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label>Errores del Sistema</Label>
                          <p className="text-sm text-muted-foreground">Alertar sobre fallos técnicos</p>
                        </div>
                        <Switch defaultChecked />
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <Label>Mantenimiento</Label>
                          <p className="text-sm text-muted-foreground">Recordatorios de mantenimiento</p>
                        </div>
                        <Switch />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="email">Correo de Notificaciones</Label>
                    <Input id="email" type="email" defaultValue="admin@fim.uni.edu.pe" />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="phone">Teléfono (SMS)</Label>
                    <Input id="phone" type="tel" defaultValue="+51 999 999 999" />
                  </div>
                </>
              )}

              <Button className="w-full">Guardar Configuración</Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
