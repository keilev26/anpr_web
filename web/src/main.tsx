import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App"
import "./index.css"

/**
 * Con VITE_USE_MOCKS=true la app corre contra MSW y no necesita que F2 exista.
 * Es el modo por defecto mientras la API no esté lista.
 */
async function enableMocking() {
  if (import.meta.env.VITE_USE_MOCKS !== "true") return
  const { worker } = await import("./mocks/browser")
  return worker.start({ onUnhandledRequest: "bypass" })
}

void enableMocking().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
