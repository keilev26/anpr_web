"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"

const hourlyData = [
  { time: "00:00", vehicles: 45, authorized: 42, denied: 3 },
  { time: "02:00", vehicles: 23, authorized: 21, denied: 2 },
  { time: "04:00", vehicles: 12, authorized: 11, denied: 1 },
  { time: "06:00", vehicles: 89, authorized: 85, denied: 4 },
  { time: "08:00", vehicles: 234, authorized: 220, denied: 14 },
  { time: "10:00", vehicles: 189, authorized: 178, denied: 11 },
  { time: "12:00", vehicles: 156, authorized: 148, denied: 8 },
  { time: "14:00", vehicles: 198, authorized: 186, denied: 12 },
  { time: "16:00", vehicles: 267, authorized: 251, denied: 16 },
  { time: "18:00", vehicles: 312, authorized: 295, denied: 17 },
  { time: "20:00", vehicles: 178, authorized: 169, denied: 9 },
  { time: "22:00", vehicles: 98, authorized: 93, denied: 5 },
]

const weeklyData = [
  { day: "Lun", vehicles: 1284, authorized: 1156, denied: 128 },
  { day: "Mar", vehicles: 1456, authorized: 1342, denied: 114 },
  { day: "Mié", vehicles: 1389, authorized: 1278, denied: 111 },
  { day: "Jue", vehicles: 1523, authorized: 1401, denied: 122 },
  { day: "Vie", vehicles: 1678, authorized: 1534, denied: 144 },
  { day: "Sáb", vehicles: 456, authorized: 423, denied: 33 },
  { day: "Dom", vehicles: 234, authorized: 218, denied: 16 },
]

const vehicleTypeData = [
  { type: "Docentes", count: 456, percentage: 35.5 },
  { type: "Estudiantes", count: 389, percentage: 30.3 },
  { type: "Administrativos", count: 234, percentage: 18.2 },
  { type: "Visitantes", count: 156, percentage: 12.1 },
  { type: "Otros", count: 49, percentage: 3.9 },
]

const responseTimeData = [
  { time: "00:00", avgTime: 2.1 },
  { time: "04:00", avgTime: 1.9 },
  { time: "08:00", avgTime: 2.8 },
  { time: "12:00", avgTime: 2.4 },
  { time: "16:00", avgTime: 3.1 },
  { time: "20:00", avgTime: 2.3 },
]

export default function StatisticsPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Estadísticas</h1>
          <p className="text-muted-foreground">Análisis detallado del sistema ANPR</p>
        </div>
        <Select defaultValue="today">
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Seleccionar período" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="today">Hoy</SelectItem>
            <SelectItem value="week">Esta Semana</SelectItem>
            <SelectItem value="month">Este Mes</SelectItem>
            <SelectItem value="year">Este Año</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Tabs defaultValue="traffic" className="space-y-4">
        <TabsList>
          <TabsTrigger value="traffic">Tráfico</TabsTrigger>
          <TabsTrigger value="types">Tipos de Vehículos</TabsTrigger>
          <TabsTrigger value="performance">Rendimiento</TabsTrigger>
        </TabsList>

        <TabsContent value="traffic" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Tráfico por Hora</CardTitle>
                <CardDescription>Distribución de vehículos durante el día</CardDescription>
              </CardHeader>
              <CardContent>
                <ChartContainer
                  config={{
                    vehicles: {
                      label: "Vehículos",
                      color: "hsl(var(--chart-1))",
                    },
                  }}
                  className="h-[300px]"
                >
                  <AreaChart data={hourlyData}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis dataKey="time" className="text-xs" />
                    <YAxis className="text-xs" />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Area
                      type="monotone"
                      dataKey="vehicles"
                      stroke="hsl(var(--chart-1))"
                      fill="hsl(var(--chart-1))"
                      fillOpacity={0.2}
                    />
                  </AreaChart>
                </ChartContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Tráfico Semanal</CardTitle>
                <CardDescription>Comparación de accesos por día</CardDescription>
              </CardHeader>
              <CardContent>
                <ChartContainer
                  config={{
                    authorized: {
                      label: "Autorizados",
                      color: "hsl(var(--chart-2))",
                    },
                    denied: {
                      label: "Denegados",
                      color: "hsl(var(--chart-5))",
                    },
                  }}
                  className="h-[300px]"
                >
                  <BarChart data={weeklyData}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis dataKey="day" className="text-xs" />
                    <YAxis className="text-xs" />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="authorized" fill="hsl(var(--chart-2))" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="denied" fill="hsl(var(--chart-5))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ChartContainer>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Tendencia de Accesos</CardTitle>
              <CardDescription>Evolución de autorizaciones y denegaciones</CardDescription>
            </CardHeader>
            <CardContent>
              <ChartContainer
                config={{
                  authorized: {
                    label: "Autorizados",
                    color: "hsl(var(--chart-2))",
                  },
                  denied: {
                    label: "Denegados",
                    color: "hsl(var(--chart-5))",
                  },
                }}
                className="h-[300px]"
              >
                <LineChart data={hourlyData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="time" className="text-xs" />
                  <YAxis className="text-xs" />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Line type="monotone" dataKey="authorized" stroke="hsl(var(--chart-2))" strokeWidth={2} />
                  <Line type="monotone" dataKey="denied" stroke="hsl(var(--chart-5))" strokeWidth={2} />
                </LineChart>
              </ChartContainer>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="types" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Distribución por Tipo</CardTitle>
                <CardDescription>Clasificación de vehículos registrados</CardDescription>
              </CardHeader>
              <CardContent>
                <ChartContainer
                  config={{
                    count: {
                      label: "Cantidad",
                      color: "hsl(var(--chart-3))",
                    },
                  }}
                  className="h-[300px]"
                >
                  <BarChart data={vehicleTypeData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis type="number" className="text-xs" />
                    <YAxis dataKey="type" type="category" className="text-xs" width={100} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="count" fill="hsl(var(--chart-3))" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ChartContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Detalles por Tipo</CardTitle>
                <CardDescription>Estadísticas detalladas de cada categoría</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {vehicleTypeData.map((item, index) => (
                    <div key={index} className="space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{item.type}</span>
                        <span className="text-muted-foreground">
                          {item.count} ({item.percentage}%)
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-muted overflow-hidden">
                        <div className="h-full bg-chart-3 transition-all" style={{ width: `${item.percentage}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="performance" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Tiempo de Respuesta</CardTitle>
              <CardDescription>Tiempo promedio de procesamiento del sistema</CardDescription>
            </CardHeader>
            <CardContent>
              <ChartContainer
                config={{
                  avgTime: {
                    label: "Tiempo (segundos)",
                    color: "hsl(var(--chart-4))",
                  },
                }}
                className="h-[300px]"
              >
                <AreaChart data={responseTimeData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="time" className="text-xs" />
                  <YAxis className="text-xs" />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Area
                    type="monotone"
                    dataKey="avgTime"
                    stroke="hsl(var(--chart-4))"
                    fill="hsl(var(--chart-4))"
                    fillOpacity={0.2}
                  />
                </AreaChart>
              </ChartContainer>
            </CardContent>
          </Card>

          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>Precisión OCR</CardTitle>
                <CardDescription>Tasa de reconocimiento exitoso</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">98.7%</div>
                <p className="text-xs text-muted-foreground mt-1">+0.3% desde el mes pasado</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Disponibilidad</CardTitle>
                <CardDescription>Uptime del sistema</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">99.9%</div>
                <p className="text-xs text-muted-foreground mt-1">Últimos 30 días</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Procesamiento</CardTitle>
                <CardDescription>Velocidad promedio</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">2.4s</div>
                <p className="text-xs text-muted-foreground mt-1">Por vehículo</p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
