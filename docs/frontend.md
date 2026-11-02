# Frontend

## Contrato con el backend (campos reales)
- `GET /teams` → `string[]` (31 nombres sin tildes, p. ej. `"Atletico Madrid"`).
- `POST /predict` ← `{local, visitante, fecha|null}` → `{fuente, local, visitante, fecha, probabilidades{victoria_visitante, empate, victoria_local}, resultado_probable, forma_local{6 métricas}, forma_visitante, datos_hasta}`.
  Sin `fecha` usa el último dato + 7 días a las 17:30 (antes «hoy», con ~500 días de descanso, y luego «el día siguiente», con 0-1 días: ambos fuera de lo que el modelo vio; ver `docs/datos.md`, «Desfase entrenamiento-inferencia»).
- `POST /preguntar` ← `{pregunta, fecha|null}` → `{respuesta, ruta, motivo, fuente, equipos, fuentes[{documento, seccion, pagina, texto}], probabilidades, datos_hasta, prediccion|null, ms_total}`.
  `prediccion` (nuevo) = `{local, visitante, probabilidades{local, empate, visitante}, fecha_forma, datos_hasta, forma_local, forma_visitante}`.

## Arranque
Ver `frontend/README.md` (dos terminales: backend en :8000, frontend en :5173). CORS permite `localhost:5173` y `127.0.0.1:5173`
(para el navegador son orígenes distintos).

## Estructura y porqués
| Archivo | Qué hace / por qué |
|---|---|
| `src/api.js` | Único sitio con `fetch`. Timeout de 60 s con `AbortController` (fetch no tiene) y un `ApiError` con `clase` (`timeout`, `red`, `no_disponible`, `http`) para que la interfaz elija el mensaje sin leer textos. Convierte la respuesta de `/predict` a la misma forma que `prediccion` de `/preguntar`: el panel solo conoce una. |
| `src/components/Chat.jsx` | Burbujas, etiqueta de fuente (RF07), fuentes citadas, «¿por qué esta ruta?» (`<details>`), ms totales, «pensando», 5 ejemplos. Es un `<form>`: Enter envía sin código extra. Botón bloqueado y guardia en `enviar` (Enter también cuenta). |
| `src/components/PanelPrediccion.jsx` | Selectores desde `/teams`, fecha opcional, llamada directa a `/predict` (sin LLM). Barras de probabilidad, gráfica agrupada y aviso «Datos hasta …» junto al resultado. Si el chat predice, el panel se actualiza (estado elevado a `App`). |
| `src/App.jsx` | Estado compartido y diseño. Panel con `React.lazy`: Recharts pesa ~350 kB y así el chat carga sin esperarlo (y el build no avisa de chunks > 500 kB). |
| `src/App.css`, `index.css` | Estilo sobrio con variables CSS; sin escudos ni logos. |

Decisiones:
- **Gráfica solo con goles a favor/en contra, xG y puntos**: PPDA (~5–12) y los días de descanso (otra unidad) aplastarían las barras; van en una tabla.
- **Responsive**: ≥ 900 px dos columnas; por debajo, pestañas. Ambas vistas siguen montadas para no perder la conversación al cambiar.
- **Accesibilidad**: `label` en cada campo, `role="log"` con `aria-live="polite"` para mensajes nuevos, foco visible, enlace «saltar al contenido», valores de probabilidad también en texto, colores con contraste AA.
- **Cambiar de estado al recibir una predicción externa se hace durante el render**, no en un `useEffect` (el linter lo marcaba y evita un render con datos viejos).

## Qué se probó y qué no (01–02/11/2026)
Probado con el backend real (qwen2.5:7b) ejecutando el propio `src/api.js` con Vite en Node y renderizando `App` en servidor:
- Las 4 rutas por `/preguntar`: conocimiento (3 fuentes, 5,1 s), predicción (`prediccion` estructurada, 23 ms), aclarar y fuera de alcance (1 ms).
- `/teams` (31), `/predict` (200) y 422 con equipos iguales; preflight CORS desde ambos orígenes → permitido.
- Sin Ollama (`OLLAMA_BASE_URL` inválida): `/preguntar` de reglamento → 503 → `clase: no_disponible`; la predicción sigue funcionando.
- Backend apagado → `clase: red`.
- `npm run build` y `npm run lint` sin errores ni avisos.

**No probado:** la interfaz en un navegador real (no hay navegador en este entorno): ni el aspecto, ni el responsive, ni
lectores de pantalla, ni el foco con teclado; tampoco el aviso de timeout de 60 s (no se esperó); ni el gráfico de Recharts
dibujado. Hay que abrir `http://127.0.0.1:5173` y recorrerlo a mano.
