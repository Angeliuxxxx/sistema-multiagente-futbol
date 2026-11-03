import { useEffect, useRef, useState } from 'react'
import { preguntar } from '../api.js'
import { formatearFecha } from '../fechas.js'

// Nombres legibles de las rutas. Solo es presentación: los valores que devuelve la API no cambian.
// Si llega una ruta nueva que no está aquí, se muestra tal cual en vez de romper.
const NOMBRE_RUTA = {
  prediccion: 'Predicción',
  conocimiento: 'Conocimiento',
  aclarar: 'Necesito más datos',
  fuera_de_alcance: 'Fuera de alcance',
}

// Una de cada tipo de ruta, para que quien abre la app vea qué sabe hacer el sistema sin adivinar.
const EJEMPLOS = [
  '¿Cuántos suplentes se pueden usar en un partido?',
  '¿Qué es el fuera de juego?',
  '¿Quién gana el Barcelona contra el Real Madrid?',
  'Sevilla vs Valencia',
  '¿Cuántos goles ha marcado Messi esta temporada?',
]

// RF07: toda respuesta indica qué agente la produjo.
const ETIQUETA = {
  agente_conocimiento: 'Conocimiento',
  agente_predictivo: 'Predicción',
  orquestador: 'Sistema',
}

// El backend responde 503 cuando Ollama está apagado; las predicciones no lo necesitan, así que lo decimos.
function mensajeDeError(e) {
  if (e.clase === 'no_disponible')
    return 'El asistente de conocimiento no está disponible ahora (¿Ollama está apagado?). Los pronósticos sí funcionan: prueba «Sevilla vs Valencia».'
  if (e.clase === 'timeout') return 'La respuesta tardó más de 60 segundos. Inténtalo de nuevo en un momento.'
  if (e.clase === 'red') return `No pude conectar con el servidor. ¿Está arrancado el backend? (${e.message})`
  return `Algo salió mal: ${e.message}`
}

// Insignia de ruta: la clase pone el color, pero el TEXTO es lo que identifica la ruta (nunca solo color).
const CLASE_RUTA = { prediccion: 'pred', conocimiento: 'conoc', aclarar: 'aviso', fuera_de_alcance: 'aviso' }

// «Ficha de fuente»: de dónde sale la respuesta (CLAUDE.md: toda respuesta indica su fuente). Todo viene de la API.
function FichaFuente({ m }) {
  if (m.fuentes?.length > 0) {
    return (
      <div className="ficha-fuente">
        <span className="ficha-titulo">Fuente</span>
        <ul aria-label="Fuentes citadas">
          {m.fuentes.map((f, i) => (
            <li key={i}>
              {f.documento}
              {f.seccion && `, ${f.seccion.split(' – ')[0]}`}
              {f.pagina && `, pág. ${f.pagina}`}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  if (m.prediccion) {
    return (
      <div className="ficha-fuente">
        <span className="ficha-titulo">Fuente</span>
        <p>Modelo XGBoost · datos hasta {formatearFecha(m.prediccion.datos_hasta)}</p>
      </div>
    )
  }
  if (m.fuente) {
    return (
      <div className="ficha-fuente">
        <span className="ficha-titulo">Fuente</span>
        <p>{ETIQUETA[m.fuente] ?? m.fuente}</p>
      </div>
    )
  }
  return null
}

function Burbuja({ m, onMostrarPanel }) {
  if (m.rol === 'usuario') return <li className="burbuja usuario">{m.texto}</li>
  return (
    <li className={`respuesta${m.error ? ' error' : ''}`}>
      {m.ruta && <span className={`insignia insignia-${CLASE_RUTA[m.ruta] ?? 'aviso'}`}>{NOMBRE_RUTA[m.ruta] ?? m.ruta}</span>}
      <p className="respuesta-texto">{m.texto}</p>

      {m.prediccion && (
        <button type="button" className="enlace" onClick={() => onMostrarPanel(m.prediccion)}>
          Ver detalle en el panel
        </button>
      )}

      <FichaFuente m={m} />

      {m.ruta && (
        <details>
          <summary>¿Por qué esta ruta?</summary>
          <p>
            <strong>Ruta:</strong> {NOMBRE_RUTA[m.ruta] ?? m.ruta}
            <br />
            <strong>Motivo:</strong> {m.motivo}
          </p>
        </details>
      )}
      {m.ms_total != null && <small className="tiempo">{m.ms_total} ms</small>}
    </li>
  )
}

export default function Chat({ onPrediccion, onMostrarPanel }) {
  const [mensajes, setMensajes] = useState([])
  const [texto, setTexto] = useState('')
  const [pensando, setPensando] = useState(false)
  const lista = useRef(null)

  // Al llegar un mensaje nuevo, bajar hasta él. Se mueve solo el scroll de la lista: scrollIntoView también
  // desplazaría los contenedores de alrededor (la página o la columna) y sacaría el campo de texto de la vista.
  useEffect(() => { lista.current?.scrollTo({ top: lista.current.scrollHeight }) }, [mensajes, pensando])

  async function enviar(pregunta) {
    const p = pregunta.trim()
    // El botón bloqueado no basta: Enter en el campo también envía, así que se protege aquí.
    if (p.length < 3 || pensando) return
    setMensajes((ms) => [...ms, { id: crypto.randomUUID(), rol: 'usuario', texto: p }])
    setTexto('')
    setPensando(true)
    try {
      const r = await preguntar(p)
      setMensajes((ms) => [...ms, {
        id: crypto.randomUUID(), rol: 'sistema', texto: r.respuesta, fuente: r.fuente, fuentes: r.fuentes,
        ruta: r.ruta, motivo: r.motivo, ms_total: r.ms_total, prediccion: r.prediccion,
      }])
      if (r.prediccion) onPrediccion(r.prediccion) // el panel se actualiza solo con lo que el chat predijo
    } catch (e) {
      setMensajes((ms) => [...ms, { id: crypto.randomUUID(), rol: 'sistema', texto: mensajeDeError(e), error: true }])
    } finally {
      setPensando(false)
    }
  }

  return (
    <section className="tarjeta chat" aria-labelledby="titulo-chat">
      <h2 id="titulo-chat">Pregunta al sistema</h2>

      {/* role="log" + aria-live: el lector de pantalla anuncia cada mensaje nuevo sin perder el foco del campo. */}
      <ol ref={lista} className="mensajes" role="log" aria-live="polite" aria-label="Conversación">
        {mensajes.length === 0 && (
          <li className="vacio">Escribe una pregunta de reglamento o de pronóstico, o prueba un ejemplo.</li>
        )}
        {mensajes.map((m) => <Burbuja key={m.id} m={m} onMostrarPanel={onMostrarPanel} />)}
        {pensando && <li className="respuesta pensando" role="status">Pensando<span aria-hidden="true">…</span></li>}
      </ol>

      <div className="ejemplos" role="group" aria-label="Preguntas de ejemplo">
        {EJEMPLOS.map((e) => (
          <button key={e} type="button" className="chip" disabled={pensando} onClick={() => enviar(e)}>{e}</button>
        ))}
      </div>

      {/* <form>: Enter envía sin código extra y funciona igual con teclado, móvil y lectores de pantalla. */}
      <form className="entrada" onSubmit={(ev) => { ev.preventDefault(); enviar(texto) }}>
        <label htmlFor="pregunta" className="solo-lector">Tu pregunta</label>
        <input id="pregunta" type="text" value={texto} maxLength={500} autoComplete="off"
               placeholder="Ej.: ¿Cuántos puntos se dan por una victoria?" onChange={(ev) => setTexto(ev.target.value)} />
        <button type="submit" disabled={pensando || texto.trim().length < 3}>{pensando ? 'Esperando…' : 'Enviar'}</button>
      </form>
    </section>
  )
}
