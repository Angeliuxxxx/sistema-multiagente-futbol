import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { obtenerEquipos, predecir } from '../api.js'

// Se grafican solo las métricas en una escala parecida (0-3). PPDA (~5-12) aplastaría las demás barras y los días
// de descanso son otra unidad, así que van en una tabla aparte.
const METRICAS_GRAFICA = [
  ['forma_goles_favor', 'Goles a favor'],
  ['forma_goles_contra', 'Goles en contra'],
  ['forma_xg', 'xG'],
  ['forma_puntos', 'Puntos'],
]

const RESULTADOS = [
  ['local', 'Gana local', 'var(--local)'],
  ['empate', 'Empate', 'var(--empate)'],
  ['visitante', 'Gana visitante', 'var(--visitante)'],
]

const pct = (x) => `${(x * 100).toFixed(1)} %`

function Barras({ p }) {
  return (
    <div className="probabilidades">
      {RESULTADOS.map(([clave, etiqueta, color]) => (
        <div className="fila-prob" key={clave}>
          <span className="etiqueta-prob">{etiqueta}</span>
          {/* El valor va también en texto: el color o el ancho solos no los percibe un lector de pantalla. */}
          <div className="pista" aria-hidden="true"><div className="relleno" style={{ width: pct(p[clave]), background: color }} /></div>
          <strong>{pct(p[clave])}</strong>
        </div>
      ))}
    </div>
  )
}

export default function PanelPrediccion({ externa }) {
  const [equipos, setEquipos] = useState([])
  const [local, setLocal] = useState('')
  const [visitante, setVisitante] = useState('')
  const [fecha, setFecha] = useState('')
  const [resultado, setResultado] = useState(null)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  useEffect(() => {
    obtenerEquipos()
      .then((lista) => { setEquipos(lista); setLocal((l) => l || 'Barcelona'); setVisitante((v) => v || 'Real Madrid') })
      .catch((e) => setError(`No pude cargar los equipos: ${e.message}`))
  }, [])

  // Si el chat predijo algo, el panel muestra ESO y deja los selectores coherentes con ello. Se ajusta durante el render
  // (patrón recomendado por React para "reaccionar a un cambio de prop") y no en un efecto: evita un render extra con datos viejos.
  const [externaVista, setExternaVista] = useState(null)
  if (externa && externa !== externaVista) {
    setExternaVista(externa)
    setResultado(externa)
    setLocal(externa.local)
    setVisitante(externa.visitante)
    setError('')
  }

  async function calcular(ev) {
    ev.preventDefault()
    setCargando(true)
    setError('')
    try {
      setResultado(await predecir({ local, visitante, fecha }))
    } catch (e) {
      setError(e.clase === 'http' ? e.message : `No pude calcular la predicción: ${e.message}`)
    } finally {
      setCargando(false)
    }
  }

  const iguales = local !== '' && local === visitante
  const datos = resultado && METRICAS_GRAFICA.map(([k, nombre]) => ({
    metrica: nombre, [resultado.local]: resultado.forma_local[k], [resultado.visitante]: resultado.forma_visitante[k],
  }))

  return (
    <section className="tarjeta panel" aria-labelledby="titulo-panel">
      <h2 id="titulo-panel">Predicción de un partido</h2>

      <form className="formulario" onSubmit={calcular}>
        <div className="campo">
          <label htmlFor="local">Local</label>
          <select id="local" value={local} onChange={(e) => setLocal(e.target.value)}>
            {equipos.map((e) => <option key={e}>{e}</option>)}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="visitante">Visitante</label>
          <select id="visitante" value={visitante} onChange={(e) => setVisitante(e.target.value)}>
            {equipos.map((e) => <option key={e}>{e}</option>)}
          </select>
        </div>
        <div className="campo">
          <label htmlFor="fecha">Fecha (opcional)</label>
          <input id="fecha" type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
        </div>
        <button type="submit" disabled={cargando || !local || !visitante || iguales}>{cargando ? 'Calculando…' : 'Predecir'}</button>
      </form>
      {iguales && <p className="nota" role="alert">Elige dos equipos distintos.</p>}
      {error && <p className="nota error" role="alert">{error}</p>}

      {resultado ? (
        <div aria-live="polite">
          {/* Aviso siempre visible junto al resultado: la predicción usa datos viejos y el usuario debe saberlo. */}
          <p className="aviso">
            <strong>Datos hasta {resultado.datos_hasta}.</strong> La forma se calculó con los 5 partidos anteriores al {resultado.fecha_forma}; no incluye nada posterior.
          </p>
          <h3>{resultado.local} (local) vs {resultado.visitante} (visitante)</h3>
          <Barras p={resultado.probabilidades} />

          <h3>Forma reciente (últimos 5 partidos)</h3>
          <div className="grafica" role="img"
               aria-label={`Barras agrupadas: forma de ${resultado.local} y ${resultado.visitante} en goles a favor, goles en contra, xG y puntos`}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={datos} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="metrica" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey={resultado.local} fill="var(--local)" />
                <Bar dataKey={resultado.visitante} fill="var(--visitante)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="otras">
            <caption>Otras métricas</caption>
            <thead><tr><th scope="col">Métrica</th><th scope="col">{resultado.local}</th><th scope="col">{resultado.visitante}</th></tr></thead>
            <tbody>
              <tr><th scope="row">PPDA (presión; menor = presiona más)</th><td>{resultado.forma_local.forma_ppda.toFixed(2)}</td><td>{resultado.forma_visitante.forma_ppda.toFixed(2)}</td></tr>
              <tr><th scope="row">Días desde el último partido</th><td>{resultado.forma_local.dias_desde_ultimo_partido}</td><td>{resultado.forma_visitante.dias_desde_ultimo_partido}</td></tr>
            </tbody>
          </table>
        </div>
      ) : (
        <p className="nota">Elige dos equipos y pulsa «Predecir». Aquí verás también las predicciones que pidas en el chat; el aviso con la fecha del último dato aparecerá junto al resultado.</p>
      )}
    </section>
  )
}
