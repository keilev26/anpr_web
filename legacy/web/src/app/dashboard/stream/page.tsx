"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Video, Camera, Activity, AlertCircle, CheckCircle2, Play, Pause, Maximize2, Car } from "lucide-react"

export default function StreamPage() {
  const [isLive, setIsLive] = useState(true)
  const [detections, setDetections] = useState<
    Array<{
      id: string
      plate: string
      time: string
      confidence: number
    }>
  >([])

  // Simular detecciones en tiempo real
  useEffect(() => {
    if (!isLive) return

    const interval = setInterval(() => {
      const plates = ["ABC-123", "XYZ-789", "DEF-456", "GHI-012", "JKL-345"]
      const randomPlate = plates[Math.floor(Math.random() * plates.length)]
      const confidence = 85 + Math.random() * 15

      setDetections((prev) => [
        {
          id: Date.now().toString(),
          plate: randomPlate,
          time: new Date().toLocaleTimeString(),
          confidence: Math.round(confidence),
        },
        ...prev.slice(0, 9), // Mantener solo las últimas 10 detecciones
      ])
    }, 5000) // Nueva detección cada 5 segundos

    return () => clearInterval(interval)
  }, [isLive])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Stream en Vivo</h1>
        <p className="text-muted-foreground">Monitoreo en tiempo real de la cámara ANPR - Puerta 2</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Video Stream Principal */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Camera className="h-5 w-5 text-primary" />
                <CardTitle>Cámara Principal</CardTitle>
              </div>
              <div className="flex items-center gap-2">
                {isLive ? (
                  <>
                    <div className="flex items-center gap-1.5">
                      <div className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
                      <span className="text-sm font-medium text-red-500">EN VIVO</span>
                    </div>
                  </>
                ) : (
                  <Badge variant="secondary">Pausado</Badge>
                )}
              </div>
            </div>
            <CardDescription>FIM UNI - Puerta 2 - Entrada Principal</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="relative aspect-video bg-black rounded-lg overflow-hidden border border-border">
              {/* Simulación de video stream */}
              <div className="absolute inset-0 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-center space-y-4">
                    <Video className="h-16 w-16 text-muted-foreground mx-auto" />
                    <p className="text-sm text-muted-foreground">
                      Stream de cámara ANPR
                      <br />
                      <span className="text-xs">Conectar con: rtsp://camera-ip:554/stream</span>
                    </p>
                  </div>
                </div>

                {/* Overlay de información */}
                <div className="absolute top-4 left-4 space-y-2">
                  <div className="bg-black/60 backdrop-blur-sm px-3 py-1.5 rounded-md text-xs text-white font-mono">
                    {new Date().toLocaleString()}
                  </div>
                  <div className="bg-black/60 backdrop-blur-sm px-3 py-1.5 rounded-md text-xs text-white">
                    FPS: 30 | Resolución: 1920x1080
                  </div>
                </div>

                {/* Zona de detección */}
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="border-2 border-primary/50 w-2/3 h-1/3 rounded-lg">
                    <div className="absolute -top-6 left-0 bg-primary/80 px-2 py-1 rounded text-xs text-primary-foreground">
                      Zona de Detección
                    </div>
                  </div>
                </div>
              </div>

              {/* Controles */}
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2">
                <Button size="sm" variant={isLive ? "secondary" : "default"} onClick={() => setIsLive(!isLive)}>
                  {isLive ? <Pause className="h-4 w-4 mr-2" /> : <Play className="h-4 w-4 mr-2" />}
                  {isLive ? "Pausar" : "Reanudar"}
                </Button>
                <Button size="sm" variant="secondary">
                  <Maximize2 className="h-4 w-4 mr-2" />
                  Pantalla Completa
                </Button>
              </div>
            </div>

            {/* Estadísticas del stream */}
            <div className="grid grid-cols-3 gap-4 mt-4">
              <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                <Activity className="h-5 w-5 text-green-500" />
                <div>
                  <p className="text-xs text-muted-foreground">Estado</p>
                  <p className="text-sm font-semibold text-foreground">Activo</p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                <CheckCircle2 className="h-5 w-5 text-blue-500" />
                <div>
                  <p className="text-xs text-muted-foreground">Detecciones Hoy</p>
                  <p className="text-sm font-semibold text-foreground">247</p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                <AlertCircle className="h-5 w-5 text-yellow-500" />
                <div>
                  <p className="text-xs text-muted-foreground">Alertas</p>
                  <p className="text-sm font-semibold text-foreground">3</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Panel de Detecciones en Tiempo Real */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              Detecciones Recientes
            </CardTitle>
            <CardDescription>Últimas placas detectadas</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 max-h-[500px] overflow-y-auto">
              {detections.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground text-sm">Esperando detecciones...</div>
              ) : (
                detections.map((detection) => (
                  <div
                    key={detection.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-muted/50 border border-border animate-in fade-in slide-in-from-top-2 duration-300"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-primary/10 border border-primary/20">
                        <Car className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <p className="font-mono font-semibold text-foreground">{detection.plate}</p>
                        <p className="text-xs text-muted-foreground">{detection.time}</p>
                      </div>
                    </div>
                    <Badge variant={detection.confidence > 95 ? "default" : "secondary"}>{detection.confidence}%</Badge>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Cámaras Secundarias */}
      <Card>
        <CardHeader>
          <CardTitle>Cámaras Adicionales</CardTitle>
          <CardDescription>Vistas secundarias del sistema ANPR</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            {[
              { name: "Cámara Contexto", status: "Activa", view: "Vista General" },
              { name: "Cámara Salida", status: "Activa", view: "Puerta 2 - Salida" },
              { name: "Cámara Backup", status: "Standby", view: "Respaldo" },
            ].map((camera, index) => (
              <div key={index} className="space-y-2">
                <div className="relative aspect-video bg-black rounded-lg overflow-hidden border border-border">
                  <div className="absolute inset-0 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 flex items-center justify-center">
                    <Camera className="h-8 w-8 text-muted-foreground" />
                  </div>
                  <div className="absolute top-2 right-2">
                    <Badge variant={camera.status === "Activa" ? "default" : "secondary"} className="text-xs">
                      {camera.status}
                    </Badge>
                  </div>
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{camera.name}</p>
                  <p className="text-xs text-muted-foreground">{camera.view}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
