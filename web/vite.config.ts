import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "node:path"

export default defineConfig(({ mode }) => {
  // loadEnv y no process.env: Vite expone las variables de .env.local en
  // import.meta.env, no en process.env. Leyéndolas de process.env, cambiar
  // VITE_API_URL no tenía ningún efecto sobre el proxy.
  const env = loadEnv(mode, process.cwd(), "")

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
      port: 3000,
      proxy: {
        // Con VITE_USE_MOCKS=true, MSW intercepta antes y esto no se usa.
        "/api": {
          target: env.VITE_API_URL || "http://localhost:8000",
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ""),
        },
      },
    },
  }
})
