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
| `src/components/PanelPrediccion.jsx` | Selectores desde `/teams`, fecha opcional, llamada directa a `/predict` (sin LLM). Marcador con iniciales, cifras de probabilidad, barras espejo de forma y aviso «Datos hasta …». Si el chat predice, el panel se actualiza (estado elevado a `App`). |
| `src/App.jsx` | Estado compartido, cabecera y rejilla. Ya no hay pestañas ni `React.lazy`: sin Recharts el panel es ligero. |
| `src/styles/tokens.css` | ÚNICO sitio con colores, fuentes y medidas (variables CSS). |
| `src/index.css`, `App.css`, `styles/{componentes,chat,panel}.css` | Base, layout/cabecera y estilos por componente; solo usan `var(--…)`. |

Decisiones:
- **Gráfica solo con goles a favor/en contra, xG y puntos**: PPDA (~5–12) y los días de descanso (otra unidad) aplastarían las barras; van en una tabla.
- **Responsive**: ≥ 900 px dos columnas; por debajo, el panel queda debajo del chat (sin pestañas; «Ver detalle en el panel» baja hasta él) y la entrada del chat va fija abajo.
- **Accesibilidad**: `label` en cada campo, `role="log"` con `aria-live="polite"` para mensajes nuevos, foco visible, enlace «saltar al contenido», valores de probabilidad también en texto, colores con contraste AA.
- **Cambiar de estado al recibir una predicción externa se hace durante el render**, no en un `useEffect` (el linter lo marcaba y evita un render con datos viejos).

## Rediseño «Estadio nocturno» (rama `frontend-rediseno`)
Solo capa visual; `api.js` y el backend no cambian.

**Tokens** (`src/styles/tokens.css`): fondo `#0A1512`, superficie `#101F1A`, superficie 2 `#16291F`, línea `#23382E`; texto `#EAF2EC`,
atenuado `#9DB3A6`; local `#3DDC84`, empate `#C9D6CE`, visitante `#5BA8FF`, aviso `#F5B83D`. Insignias: Predicción `#3DDC84`/`#123524`,
Conocimiento `#8CC4FF`/`#12283D`, Fuera de alcance y «Necesito más datos» `#F5B83D`/`#3A2C0B`. Error (no estaba en el diseño): `#FFB4AB`/`#3A1613`.
Texto del botón principal `#06210F` sobre `#3DDC84`.

**Fuentes locales**: `@fontsource/barlow-condensed` (600, 700) e `@fontsource/inter` (400, 500, 600) se empaquetan en `dist/`; no hay CDN de
Google Fonts, así que la demo funciona sin Wi-Fi.

**Contraste medido** (WCAG, calculado con la fórmula de luminancia): texto/fondo 16,3; atenuado/superficie 7,7; atenuado/superficie 2 6,9;
local/superficie 2 8,6; visitante/superficie 2 6,2; aviso/fondo 10,5; insignias 7,5 / 8,2 / 7,6; botón 9,6; error 9,5. Todos ≥ 4,5:1.
El borde de los campos (`#7A9A88`) se subió para superar 3:1 (componente de interfaz).

**Decisiones**
- Se retiró `recharts`: la comparación de forma son ahora barras espejo en CSS (local a la izquierda, visitante a la derecha), cada fila escalada
  contra el mayor de sus dos valores y con los números exactos escritos. En «goles en contra» y PPDA se indica que menos es mejor.
- Chip «Datos hasta el 25 may 2025» de la cabecera: es una constante en `App.jsx` (`DATOS_HASTA_CABECERA`), porque ningún endpoint la devuelve
  sin pedir una predicción. Cada resultado muestra el `datos_hasta` real de la API. Si cambian los datos hay que actualizar la constante.
- «fecha por defecto» aparece cuando el usuario no eligió fecha. Las predicciones del chat siempre la llevan (`preguntar` no envía fecha).
- Color nunca solo: cada cifra, barra e insignia lleva su etiqueta de texto.

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
