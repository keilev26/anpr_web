import { Navigate, Outlet, useLocation } from "react-router-dom"
import { useAuth } from "./AuthContext"

/**
 * Guardia de rutas real. El legacy no tenía ninguna: el login era un
 * `setTimeout` de 1 s y bastaba escribir /dashboard en la barra para entrar.
 */
export function ProtectedRoute() {
  const { user, loading } = useAuth()
  const location = useLocation()

  // Sin esto, al recargar se vería un parpadeo al login antes de restaurar sesión.
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
        Verificando sesión…
      </div>
    )
  }

  if (!user) return <Navigate to="/login" state={{ from: location }} replace />

  return <Outlet />
}
