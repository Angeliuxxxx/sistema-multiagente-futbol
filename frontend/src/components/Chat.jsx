import { useEffect, useRef, useState } from 'react'
import { preguntar } from '../api.js'

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

function Burbuja({ m, onMostrarPanel }) {
  if (m.rol === 'usuario') return <li className="burbuja usuario">{m.texto}</li>
  return (
    <li className={`burbuja sistema${m.error ? ' error' : ''}`}>
      {m.fuente && <span className={`etiqueta etiqueta-${m.fuente}`}>{ETIQUETA[m.fuente]}</span>}
      <p>{m.texto}</p>

      {m.fuentes?.length > 0 && (
        <ul className="fuentes" aria-label="Fuentes citadas">
          {m.fuentes.map((f, i) => (
            <li key={i}>
              {f.documento}
              {f.seccion && `, ${f.seccion.split(' – ')[0]}`}
              {f.pagina && `, pág. ${f.pagina}`}
            </li>
          ))}
        </ul>
      )}

      {m.prediccion && (
        <button type="button" className="enlace" onClick={() => onMostrarPanel(m.prediccion)}>
          Ver detalle en el panel
        </button>
      )}

      {m.ruta && (
        <details>
          <summary>¿Por qué esta ruta?</summary>
          <p>
            <strong>Ruta:</strong> {m.ruta}
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
  const final = useRef(null)

  // Al llegar un mensaje nuevo, bajar hasta él; si no, la respuesta queda fuera de la vista.
  useEffect(() => { final.current?.scrollIntoView({ block: 'end' }) }, [mensajes, pensando])

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
      <ol className="mensajes" role="log" aria-live="polite" aria-label="Conversación">
        {mensajes.length === 0 && (
          <li className="vacio">Escribe una pregunta de reglamento o de pronóstico, o prueba un ejemplo.</li>
        )}
        {mensajes.map((m) => <Burbuja key={m.id} m={m} onMostrarPanel={onMostrarPanel} />)}
        {pensando && <li className="burbuja sistema pensando" role="status">Pensando<span aria-hidden="true">…</span></li>}
        <li ref={final} aria-hidden="true" />
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
