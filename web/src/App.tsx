import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Toaster } from "sonner"
import { AuthProvider } from "@/auth/AuthContext"
import { ProtectedRoute } from "@/auth/ProtectedRoute"
import { DashboardLayout } from "@/components/DashboardLayout"
import LoginPage from "@/pages/Login"
import RecordsPage from "@/pages/Records"
import UsersVehiclesPage from "@/pages/UsersVehicles"
import { HttpError } from "@/lib/api"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      // Un 401 lo resuelve el refresh del cliente HTTP, no un reintento ciego.
      retry: (failureCount, error) =>
        !(error instanceof HttpError && error.status < 500) && failureCount < 2,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<DashboardLayout />}>
                <Route path="/records" element={<RecordsPage />} />
                <Route path="/users-vehicles" element={<UsersVehiclesPage />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/records" replace />} />
          </Routes>
          <Toaster position="top-right" richColors />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
