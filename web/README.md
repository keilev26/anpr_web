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

## Cómo trabajar aislado

Mock de la API con **MSW** o `json-server`, alimentado por `contracts/openapi.yaml`.
El cliente TypeScript se **genera** desde ese archivo: no se escriben tipos a mano
en dos lados.

## Terminado cuando

Todas las vistas funcionan contra mocks, con login y guardia de rutas real.

## Punto de partida

`legacy/web/` tiene el Next.js actual con shadcn/ui. Los componentes de
`src/components/ui/` se reutilizan casi tal cual. **No** se migran las ~1.100 líneas
de páginas huérfanas (`dashboard/{statistics,database,users,settings,stream}`),
que están comentadas en el sidebar y llenas de datos mock.

Ver `MEJORAS.md` §4 para la lista de problemas del frontend actual.
