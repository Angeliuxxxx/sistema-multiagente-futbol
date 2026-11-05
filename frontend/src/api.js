// Todas las llamadas al backend viven aquí: los componentes no conocen URLs ni detalles de fetch.
export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

// 60 s: la primera pregunta de conocimiento puede tardar (carga del LLM); más que eso casi seguro es un fallo.
const TIMEOUT_MS = 60_000

// Un solo tipo de error con una `clase` para que la interfaz elija el mensaje amable sin mirar textos.
export class ApiError extends Error {
  constructor(clase, mensaje, status = null) {
    super(mensaje)
    this.clase = clase // 'timeout' | 'red' | 'no_disponible' | 'http'
    this.status = status
  }
}

async function peticion(ruta, opciones = {}) {
  // AbortController: fetch no tiene timeout propio, hay que cortarlo a mano.
  const control = new AbortController()
  const temporizador = setTimeout(() => control.abort(), TIMEOUT_MS)
  try {
    const r = await fetch(`${API_URL}${ruta}`, { ...opciones, signal: control.signal })
    if (!r.ok) {
      // FastAPI manda el motivo en `detail` (texto en 404/503, lista en 422).
      let detalle = ''
      try {
        const cuerpo = await r.json()
        detalle = typeof cuerpo.detail === 'string' ? cuerpo.detail : JSON.stringify(cuerpo.detail)
      } catch { /* la respuesta no era JSON: nos quedamos sin detalle */ }
      throw new ApiError(r.status === 503 ? 'no_disponible' : 'http', detalle || `Error ${r.status}`, r.status)
    }
    return await r.json()
  } catch (e) {
    if (e instanceof ApiError) throw e
    if (e.name === 'AbortError') throw new ApiError('timeout', 'La petición tardó más de 60 s.')
    throw new ApiError('red', `No se pudo conectar con ${API_URL}.`)
  } finally {
    clearTimeout(temporizador) // sin esto el temporizador seguiría vivo tras una respuesta rápida
  }
}

const post = (ruta, cuerpo) =>
  peticion(ruta, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) })

export const obtenerEquipos = (modelo = 'b') => peticion(`/teams?modelo=${modelo}`)
export const obtenerEstado = () => peticion('/health')
export const obtenerTabla = () => peticion('/tabla')
export const obtenerRegistro = () => peticion('/registro')
export const obtenerProximos = (n = 6) => peticion(`/proximos?n=${n}`)

// /predict y /preguntar describen la predicción con formas distintas; el resto de la app solo ve ESTA forma.
export async function predecir({ local, visitante, fecha, modelo = 'b' }) {
  const r = await post('/predict', { local, visitante, fecha: fecha || null, modelo })
  return {
    modelo: r.modelo,
    local: r.local,
    visitante: r.visitante,
    probabilidades: {
      local: r.probabilidades.victoria_local,
      empate: r.probabilidades.empate,
      visitante: r.probabilidades.victoria_visitante,
    },
    fecha_forma: r.fecha,
    fecha_origen: r.fecha_origen, // 'calendario' | 'por_defecto' | 'usuario' (solo modelo B)
    datos_hasta: r.datos_hasta,
    aviso: r.aviso ?? null, // fecha pasada: el modelo ya vio ese partido al entrenar (solo modelo B)
    forma_local: r.forma_local,
    forma_visitante: r.forma_visitante,
  }
}

// Devuelve la respuesta tal cual: { respuesta, ruta, motivo, fuente, fuentes, ms_total, prediccion|null, ... }
export const preguntar = (pregunta) => post('/preguntar', { pregunta })
