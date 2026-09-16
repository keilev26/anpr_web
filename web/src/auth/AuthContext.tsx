import { createContext, use, useCallback, useEffect, useMemo, useState } from "react"
import { api, setAccessToken, setUnauthorizedHandler } from "@/lib/api"
import type { LoginResponse, User } from "@/types/api"

interface AuthState {
  user: User | null
  /** true mientras se intenta restaurar la sesión al cargar la página. */
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const clear = useCallback(() => {
    setAccessToken(null)
    setUser(null)
  }, [])

  /**
   * El access token vive solo en memoria, nunca en localStorage: así un XSS no
   * puede robarlo. La sesión se restaura al cargar la página usando el refresh
   * token, que viaja en una cookie HttpOnly inaccesible desde JS.
   */
  useEffect(() => {
    setUnauthorizedHandler(clear)
    let cancelled = false
    ;(async () => {
      try {
        const data = await api.post<LoginResponse>("/auth/refresh")
        if (cancelled) return
        setAccessToken(data.access_token)
        setUser(data.user)
      } catch {
        if (!cancelled) clear()
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [clear])

  const login = useCallback(async (email: string, password: string) => {
    const data = await api.post<LoginResponse>("/auth/login", { email, password })
    setAccessToken(data.access_token)
    setUser(data.user)
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout")
    } finally {
      clear()
    }
  }, [clear])

  const value = useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}

export function useAuth(): AuthState {
  const ctx = use(AuthContext)
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>")
  return ctx
}
