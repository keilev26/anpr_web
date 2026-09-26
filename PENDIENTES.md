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

## 3. Raspberry Pi (F5) — en desarrollo en la laptop

Cinco servicios systemd independientes + Mosquitto local. Se desarrolla en la laptop
con simuladores y se pasa a la Pi en la parte 8. Detalle en `edge/README.md`.

- [x] **Parte 0 — Base común**: configuración, mensajes validados, bus MQTT con
      reconexión y Last Will, logs JSON, watchdog de systemd, GPIO intercambiable
- [x] **Parte 1 — Cámara**: cliente Sony con parser del formato real, simulador y sonda
- [ ] **Correr la sonda con la Sony real** (lo hace el usuario: la laptop se queda sin
      internet mientras está en el Wi-Fi de la cámara) y guardar la grabación
- [ ] Instalar Mosquitto en la laptop: `sudo apt install mosquitto mosquitto-clients`
- [ ] Parte 2 — `anpr-capture`: sesión de liveview persistente, ráfaga al spool
- [ ] Parte 3 — `anpr-uplink`: POST a la nube, reintentos con plazo, campo `late` en la API
- [ ] Parte 4 — `anpr-trigger`: sensor de presencia, reintento si la placa fue ilegible
- [ ] Parte 5 — `anpr-gate`: máquina de estados de la pluma (crítico de seguridad)
- [ ] Parte 6 — `anpr-health`: chequeos, LED y simulador de la pluma
- [ ] Parte 7 — Unidades systemd, ACL de Mosquitto, instalación y pruebas de fallos
- [ ] Parte 8 — En la Pi: comprar (Pi 5 4 GB, fuente 27 W, disipador, NVMe + HAT, pila
      RTC, UPS), dos redes, watchdog de hardware y hito I3 (LED, sin motor)
- [ ] Latido de la Pi a la nube (endpoint y tabla en la API; fuera de esta etapa)

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
