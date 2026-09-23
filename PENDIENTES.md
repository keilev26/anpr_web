# Pendientes

Lista viva de lo que falta, por frente. Actualizada el 2026-09-22.
Detalle técnico de cada frente en su propio `README.md`.

## Decisiones ya tomadas (no reabrir sin motivo)

- **Edge: Raspberry Pi 5 de 4 GB.** Se evaluaron la Zero 2 W (sirve, pero solo tiene
  Wi-Fi y 512 MB) y la Pi 4; se eligió la Pi 5 por NVMe y RTC integrados.
- **Cámara: se mantiene la Sony HDR-AS100V.** Solo se controla desde su propia red Wi-Fi
  (`192.168.122.1`, Camera Remote API): no puede unirse al router. La Pi usa **Wi-Fi
  para la cámara y Ethernet para internet**.
- **Portón: pluma** (barrera vehicular) movida por un **UX-52**, con selector
  FWD / STOP / REV en la caja de mando. La Pi imitará ese selector con dos relés.
- **Dashboard en Lambda, no en EC2**: el tráfico es bajo y EC2 costaría ~$10/mes más.

## 1. Visita técnica a la puerta (F6) — lo más urgente

Bloquea la compra de la electrónica. Ir con el electricista, un celular y cronómetro.

- [ ] **Foto de la etiqueta** del UX-52 (marca, modelo, datos eléctricos)
- [ ] **Foto de la bornera** del UX-52, con la serigrafía legible
- [ ] **Foto del interior de la caja de mando** (energía cortada): cables del selector
      FWD / STOP / REV hacia `FWD`, `REV` y `0V`
- [ ] **Placa del motor**: potencia (W), voltaje y corriente
- [ ] **Tiempo de recorrido**: subir y bajar, 3 veces cada uno, en video. Anotar la
      posición de la perilla de velocidad
- [ ] ¿El selector **vuelve solo a STOP** al soltarlo, o se queda en su posición?
- [ ] ¿El brazo está **equilibrado** (resorte o contrapeso)?
- [ ] ¿Hay **desbloqueo manual** para levantar la pluma sin energía?
- [ ] **Largo del brazo y ancho del carril** (alcance de la fotocelda)
- [ ] **Dónde irá el gabinete**, si llega **cable de red** y si hay toma de 220 V
- [ ] **Dónde irá la cámara** y **dónde se detiene el auto** frente a la pluma (sensor de presencia)

## 2. Electrónica (F6)

- [ ] Comprar la lista de materiales de `hardware/README.md` tras la visita
      (fotoceldas y finales de carrera pueden tardar semanas)
- [ ] Relés de interfaz **activables a 3,3 V** y entradas **optoacopladas** 24 V → 3,3 V
- [ ] Selector **MANUAL / AUTO** para que la Pi y el selector actual nunca manden a la vez
- [ ] Banco de pruebas **sin la Pi**: la pluma se mueve con el selector, y fotocelda y
      finales de carrera la detienen
- [ ] Criterio de aceptación: **con la Pi apagada y sin red**, fotocelda y finales de
      carrera siguen deteniendo el motor

## 3. Raspberry Pi (F5) — sin empezar

- [ ] Comprar Pi 5 4 GB, fuente oficial 27 W, disipador activo, SSD NVMe + HAT, pila RTC, UPS
- [ ] Red: Wi-Fi a la Sony + Ethernet a internet, con la ruta por defecto por Ethernet
- [ ] Servicios: presencia → ráfaga (≥3 fotos) → `POST /api/v1/detections` → relés
- [ ] Cierre automático de la pluma cuando la fotocelda se interrumpe y se libera
      (`contracts/gpio-map.md`); nunca cerrar con la fotocelda interrumpida
- [ ] Cerrar la fuga de sesiones de la Sony (`startLiveview` sin `stopLiveview`)
- [ ] Watchdog de hardware y sistema resistente a cortes de luz
- [ ] Hito I3: ráfaga → nube → veredicto → **LED**, sin motor

## 4. Modelo de IA (F4)

- [ ] **Fotos reales con la Sony desde la puerta** + `measure_plate_px` (¿la placa tiene
      suficientes píxeles en el liveview?)
- [ ] Benchmark de lectura con ~30 imágenes etiquetadas
- [ ] Formato de placas de motos
- [ ] Exportar `best.pt` a ONNX
- [ ] Reentrenar solo si las fotos reales lo justifican

## 5. Nube (F3)

- [ ] **Subir el modelo**: mover Docker a `/data` (sudo), construir y probar la imagen de
      inferencia, subirla a ECR, `infer_image_tag` y `terraform apply` (`infra/README.md` paso 5)
- [ ] Probar el camino crítico completo (paso 6)
- [ ] **Recrear la suscripción de alarmas** (`terraform apply`) y confirmar el correo
      antes de 3 días: la primera expiró sin confirmar
- [ ] Opcional: ping cada 5 min con EventBridge para evitar el arranque en frío (~5 s)
- [ ] Respaldar el estado tras cada apply (`infra/scripts/backup_tfstate.sh`)
- [ ] Al terminar la prueba: desactivar la clave de acceso de `anpr-terraform`
- [x] Cuota de Lambda 10 → 1000 (aprobada)
- [x] Usuario de consola `caleb-consola` (solo lectura + facturación)

## 6. API y web

- [ ] Decidir el rol "Administrativo": hoy mezcla la categoría de la persona con el
      permiso de entrar al dashboard
- [ ] Crear la segunda cuenta del dashboard (`api/scripts/seed.py`)
