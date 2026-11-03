import { useEffect, useState } from 'react'
import { obtenerProximos } from '../api.js'
import { formatearFecha } from '../fechas.js'

// Próximos partidos del calendario oficial con el pronóstico del modelo B ya calculado por la API.
// Tocar uno abre su detalle completo (forma, descansos) en el panel.
export default function Proximos({ onElegir }) {
  const [partidos, setPartidos] = useState(null) // null = cargando
  useEffect(() => { obtenerProximos(6).then(setPartidos).catch(() => setPartidos([])) }, [])

  if (partidos === null) return <p className="nota">Cargando próximos partidos…</p>
  if (partidos.length === 0) return null // sin calendario (sin token o sin red) el panel sigue funcionando a mano

  return (
    <section className="proximos" aria-labelledby="titulo-proximos">
      <h3 id="titulo-proximos">Próximos partidos</h3>
      <ul>
        {partidos.map((p) => {
          const { victoria_local: l, empate: e, victoria_visitante: v } = p.probabilidades
          const pc = (x) => Math.round(x * 100)
          return (
            <li key={p.fecha + p.local}>
              <button type="button" className="proximo" onClick={() => onElegir(p.local, p.visitante)}
                      aria-label={`${p.local} contra ${p.visitante}, ${formatearFecha(p.fecha)}: local ${pc(l)} %, empate ${pc(e)} %, visitante ${pc(v)} %. Ver detalle`}>
                <span className="proximo-partido">{p.local} <small>vs</small> {p.visitante}</span>
                <span className="proximo-fecha">{formatearFecha(p.fecha)}{p.jornada ? ` · J${p.jornada}` : ''}</span>
                <span className="proximo-barra" aria-hidden="true">
                  <i style={{ flex: `${l} 1 0%`, background: 'var(--local)' }} />
                  <i style={{ flex: `${e} 1 0%`, background: 'var(--empate)' }} />
                  <i style={{ flex: `${v} 1 0%`, background: 'var(--visitante)' }} />
                </span>
                <span className="proximo-cifras">{pc(l)} · {pc(e)} · {pc(v)}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
