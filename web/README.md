# F1 — Web (React SPA)

Dashboard de operación: registros ANPR, gestión de usuarios y placas, login.

## Alcance

- React SPA (Vite), desplegada en S3 + CloudFront
- TanStack Query para datos del servidor
- Guardia de rutas real contra la API de F2
- Vista de evento con foto desde S3 (URL prefirmada) y confianza de lectura

## No incluye

- La API (F2) ni su despliegue (F3)
- Nada del dispositivo de campo

## Cómo correrlo

```bash
npm install
cp .env.example .env.local
npm run dev                  # http://localhost:3000
```

Por defecto apunta a la **API real de F2** en `http://localhost:8000`, que debe
estar corriendo (ver `api/README.md`).

Para trabajar en la UI sin backend, pon `VITE_USE_MOCKS=true`: entonces entra
con **cualquier correo** y la contraseña `anpr12345` (`src/mocks/data.ts`).

| Comando | Qué hace |
|---|---|
| `npm run dev` | Servidor de desarrollo, contra MSW |
| `npm run build` | Build de producción para S3 + CloudFront |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run preview` | Sirve el build |

## Cómo trabajar aislado

Con `VITE_USE_MOCKS=true` la app corre contra **MSW** (`src/mocks/`) y no necesita
que F2 exista. En producción ese código se elimina por tree-shaking: verificado,
el bundle no contiene MSW.

Para apuntar a la API real de F2: `VITE_USE_MOCKS=false` y `VITE_API_URL=http://localhost:8000`.
`vite.config.ts` hace de proxy de `/api` hacia esa URL.

### Tipos

`src/types/api.ts` se mantiene a mano **solo mientras F2 no exista**. En cuanto la
API publique su `openapi.json`, ese archivo se genera con `openapi-typescript` y
deja de editarse: el contrato es la fuente de verdad.

## Estructura

```
src/
├── lib/         api.ts (HTTP + refresh), format.ts (fechas Lima, placas), csv.ts, utils.ts
├── types/       api.ts — derivado de contracts/openapi.yaml
├── auth/        AuthContext.tsx, ProtectedRoute.tsx
├── hooks/       useDebounce.ts, useCsvExport.ts
├── components/  Sidebar, DashboardLayout, UserFormDialog, InfiniteFooter, ui/
├── pages/       Login, Records, UsersVehicles
└── mocks/       handlers MSW + datos de ejemplo (38 usuarios, 120 eventos)
```

## Estado

- [x] Scaffold Vite + React 19 + TS + Tailwind v4
- [x] Cliente HTTP con refresh automático de token
- [x] `AuthContext` + `ProtectedRoute` (guardia real)
- [x] Login contra la API
- [x] Registros ANPR: filtros en servidor, detalle, auto-refresco
- [x] Usuarios y Placas: alta transaccional, baja con confirmación
- [x] Mocks MSW de los 8 endpoints
- [x] Paginación por cursor con scroll infinito (ambas vistas)
- [x] Edición de usuario, incluyendo alta/baja de placas y estado activo
- [x] Exportar a CSV (respeta filtros, recorre todas las páginas)
- [x] **Hito I1**: conectado a la API real de F2 y verificado extremo a extremo
- [ ] Reemplazar `src/types/api.ts` por tipos generados desde el openapi.json de F2

## Terminado cuando

Todas las vistas funcionan contra mocks, con login y guardia de rutas real. **Hecho.**

## Punto de partida

`legacy/web/` tiene el Next.js actual con shadcn/ui. Los componentes de
`src/components/ui/` se reutilizan casi tal cual. **No** se migran las ~1.100 líneas
de páginas huérfanas (`dashboard/{statistics,database,users,settings,stream}`),
que están comentadas en el sidebar y llenas de datos mock.

Ver `MEJORAS.md` §4 para la lista de problemas del frontend actual.
