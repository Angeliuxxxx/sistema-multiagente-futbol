import { useEffect, useState } from 'react'
import { obtenerTabla } from '../api.js'

const NOMBRE_FORMA = { V: 'ganó', E: 'empató', D: 'perdió' }

export function TablaPosiciones({ tabla }) {
  return (
    <>
          <div className="tabla-scroll">
            <table className="tabla">
              <caption className="solo-lector">Clasificación de la temporada en curso</caption>
              <thead>
                <tr><th scope="col">#</th><th scope="col">Equipo</th><th scope="col" title="Partidos jugados">PJ</th>
                  <th scope="col" title="Diferencia de goles">DG</th><th scope="col" title="Puntos">Pts</th><th scope="col">Forma</th></tr>
              </thead>
              <tbody>
                {tabla.map((f) => (
                  <tr key={f.equipo}>
                    <td>{f.posicion}</td>
                    <th scope="row">{f.equipo}</th>
                    <td>{f.pj}</td>
                    <td>{f.dg > 0 ? `+${f.dg}` : f.dg}</td>
                    <td className="pts">{f.pts}</td>
                    <td>
                      {/* Letra + color: la letra se lee sin ver el color; el aria-label lo dice completo al lector de pantalla. */}
                      <span className="forma-letras" role="img" aria-label={[...f.forma].map((c) => NOMBRE_FORMA[c]).join(', ')}>
                        {[...f.forma].map((c, i) => <i key={i} className={`r-${c}`}>{c}</i>)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="nota">V ganó · E empató · D perdió (más reciente a la derecha). Desempate por diferencia de goles general; el reglamento usa primero el enfrentamiento directo.</p>
    </>
  )
}

// Tabla calculada en el backend con los mismos datos del modelo (CSV + API). Se pide al abrir la pestaña, no al cargar la página.
export default function Posiciones({ activa }) {
  const [tabla, setTabla] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!activa || tabla) return
    obtenerTabla().then(setTabla).catch((e) => setError(`No pude cargar la tabla: ${e.message}`))
  }, [activa, tabla])

  return (
    <section className="tarjeta" aria-labelledby="titulo-posiciones">
      <h2 id="titulo-posiciones">Posiciones</h2>
      {error && <p className="nota error" role="alert">{error}</p>}
      {!tabla && !error && <p className="nota">Cargando tabla…</p>}
      {tabla && <TablaPosiciones tabla={tabla} />}
    </section>
  )
}
