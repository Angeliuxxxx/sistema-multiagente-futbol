import { useEffect, useState } from 'react'
import { obtenerRegistro } from '../api.js'
import { formatearFecha } from '../fechas.js'

const NOMBRE = { victoria_local: 'Local', empate: 'Empate', victoria_visitante: 'Visitante' }
const pc = (x) => Math.round(x * 100)

// Cifra con su etiqueta; el valor ausente se muestra como guion en vez de inventar un número.
function Dato({ valor, etiqueta }) {
  return <div className="dato"><strong>{valor ?? '—'}</strong><span>{etiqueta}</span></div>
}

export function ResumenYPartidos({ datos }) {
  const r = datos.resumen
  return (
    <>
          <div className="datos">
            <Dato valor={r.registrados} etiqueta="pronosticados" />
            <Dato valor={r.jugados} etiqueta="ya jugados" />
            <Dato valor={r.acierto_pct != null ? `${r.acierto_pct} %` : null} etiqueta="aciertos" />
            <Dato valor={r.log_loss} etiqueta="log-loss del modelo" />
            <Dato valor={r.log_loss_frecuencia} etiqueta="log-loss sin saber nada" />
          </div>
          {/* Aviso honesto SIEMPRE visible: con pocos partidos las cifras no prueban nada. */}
          <p className="aviso">
            {r.concluyente
              ? <>Diferencia modelo − «sin saber nada»: <strong>{r.diferencia}</strong> ± {r.error_2e}. {r.diferencia + r.error_2e < 0 ? 'El modelo supera al azar informado.' : 'El intervalo incluye 0: no hay diferencia demostrable.'}</>
              : <><strong>Todavía no se puede concluir nada.</strong> Hay {r.jugados} partidos jugados y hacen falta al menos {r.minimo_para_concluir}. El log-loss es más bajo cuanto mejor (menor es mejor).</>}
          </p>
          <h3>Partidos</h3>
          <ul className="registro">
            {datos.partidos.map((p) => {
              const pr = p.probabilidades
              const top = Object.keys(pr).reduce((a, b) => (pr[a] >= pr[b] ? a : b))
              return (
                <li key={p.inicio_partido + p.local}>
                  <span className="reg-partido">{p.local} <small>vs</small> {p.visitante}</span>
                  <span className="reg-fecha">{formatearFecha(p.inicio_partido)}{p.jornada ? ` · J${p.jornada}` : ''}</span>
                  <span className="reg-probs">Local {pc(pr.victoria_local)} · Empate {pc(pr.empate)} · Visitante {pc(pr.victoria_visitante)}</span>
                  <span className={`reg-estado ${p.resultado ? (p.acierto ? 'ok' : 'mal') : 'pendiente'}`}>
                    {p.resultado
                      ? `${p.acierto ? '✓ Acertó' : '✗ Falló'} · fue ${NOMBRE[p.resultado].toLowerCase()} (decía ${NOMBRE[top].toLowerCase()})`
                      : `Pendiente · favorito: ${NOMBRE[top].toLowerCase()}`}
                  </span>
                </li>
              )
            })}
          </ul>
    </>
  )
}

// Evaluación hacia adelante: lo que el modelo dijo ANTES del partido y lo que pasó después.
export default function Registro({ activa }) {
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  // Se vuelve a pedir cada vez que se abre la pestaña: los resultados nuevos aparecen sin recargar la página.
  useEffect(() => {
    if (!activa) return
    obtenerRegistro().then(setDatos).catch((e) => setError(`No pude cargar el registro: ${e.message}`))
  }, [activa])

  return (
    <section className="tarjeta" aria-labelledby="titulo-acierto">
      <h2 id="titulo-acierto">Acierto del modelo</h2>
      <p className="nota">Cada pronóstico se guarda <strong>antes</strong> del partido y no se puede cambiar después. Aquí se comparan con lo que pasó.</p>
      {error && <p className="nota error" role="alert">{error}</p>}
      {!datos && !error && <p className="nota">Cargando registro…</p>}
      {datos && <ResumenYPartidos datos={datos} />}
    </section>
  )
}
