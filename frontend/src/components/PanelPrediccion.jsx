import { useEffect, useState } from 'react'
import { obtenerEquipos, predecir } from '../api.js'
import { formatearFecha } from '../fechas.js'

// Comparación de forma con barras espejo. Cada fila: [clave de la API, nombre, pista de lectura].
// La pista evita leer mal: en goles en contra y PPDA, MENOS es mejor.
const METRICAS = [
  ['forma_goles_favor', 'Goles a favor', 'más es mejor', 2],
  ['forma_goles_contra', 'Goles en contra', 'menos es mejor', 2],
  ['forma_xg', 'xG', 'más es mejor', 2],
  ['forma_puntos', 'Puntos', 'más es mejor', 2],
  ['forma_ppda', 'PPDA', 'menos = presiona más', 2],
  ['dias_desde_ultimo_partido', 'Días de descanso', 'días desde el último partido', 0],
]

// Etiquetas de texto + color: el color solo no basta (daltonismo, proyector).
const RESULTADOS = [
  ['local', 'Local', 'var(--local)'],
  ['empate', 'Empate', 'var(--empate)'],
  ['visitante', 'Visitante', 'var(--visitante)'],
]

const pct = (x) => `${(x * 100).toFixed(1)} %`

// Círculo de iniciales en lugar de escudo (no se usan escudos oficiales): «Real Madrid» → RM, «Sevilla» → SEV.
function iniciales(nombre) {
  const palabras = nombre.split(/\s+/).filter(Boolean)
  return (palabras.length > 1 ? palabras.slice(0, 2).map((w) => w[0]).join('') : nombre.slice(0, 3)).toUpperCase()
}

function Equipo({ nombre, rol }) {
  return (
    <div className={`equipo equipo-${rol}`}>
      <span className="iniciales" aria-hidden="true">{iniciales(nombre)}</span>
      <span className="equipo-nombre">{nombre}</span>
      <span className="equipo-rol">{rol === 'local' ? 'Local' : 'Visitante'}</span>
    </div>
  )
}

// Anchos de los tres segmentos: cada probabilidad entre la suma (que debería ser 1, pero el redondeo de la API puede
// desviarla) para que los tres ocupen SIEMPRE el 100 % de la barra.
function anchosBarra(p) {
  const total = RESULTADOS.reduce((acc, [clave]) => acc + p[clave], 0) || 1
  return RESULTADOS.map(([clave]) => (p[clave] / total) * 100)
}

function Probabilidades({ p }) {
  const anchos = anchosBarra(p)
  return (
    <div className="probabilidades">
      <div className="cifras">
        {RESULTADOS.map(([clave, etiqueta, color]) => (
          <div className="cifra" key={clave}>
            {/* El valor va en texto grande y la etiqueta al lado: el color es solo refuerzo. */}
            <strong className="cifra-valor" style={{ color }}>{pct(p[clave])}</strong>
            <span className="cifra-etiqueta">{etiqueta}</span>
          </div>
        ))}
      </div>
      <div className="barra3" role="img"
           aria-label={`Local ${pct(p.local)}, empate ${pct(p.empate)}, visitante ${pct(p.visitante)}`}>
        {/* Antes se usaba pct() como ancho: producía «45.3 %» (con espacio), CSS inválido, y los segmentos colapsaban.
            flex-grow proporcional reparte el ancho restante tras los huecos, así que nunca desborda ni sobra. */}
        {RESULTADOS.map(([clave, , color], i) => (
          <div key={clave} data-ancho={anchos[i].toFixed(2)} style={{ flex: `${anchos[i]} 1 0%`, background: color }} />
        ))}
      </div>
    </div>
  )
}

function FilaForma({ nombre, pista, decimales, vl, vv }) {
  // Cada fila se escala contra el mayor de sus DOS valores: sirve para comparar los equipos en esa métrica,
  // y los números exactos van siempre escritos al lado.
  const max = Math.max(vl, vv, 1e-9)
  return (
    <li className="fila-forma">
      <span className="forma-valor izq">{vl.toFixed(decimales)}</span>
      <div className="forma-barras" aria-hidden="true">
        <div className="mitad izq"><div style={{ width: `${(vl / max) * 100}%`, background: 'var(--local)' }} /></div>
        <div className="mitad der"><div style={{ width: `${(vv / max) * 100}%`, background: 'var(--visitante)' }} /></div>
      </div>
      <span className="forma-valor der">{vv.toFixed(decimales)}</span>
      <span className="forma-nombre">{nombre} <small>· {pista}</small></span>
    </li>
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
  // ¿El usuario eligió fecha? El chat nunca envía fecha, así que sus predicciones siempre usan la fecha por defecto.
  const [fechaPedida, setFechaPedida] = useState(false)

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
    setFechaPedida(false)
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
      setFechaPedida(Boolean(fecha))
    } catch (e) {
      setError(e.clase === 'http' ? e.message : `No pude calcular la predicción: ${e.message}`)
    } finally {
      setCargando(false)
    }
  }

  const iguales = local !== '' && local === visitante
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
        <div aria-live="polite" className="resultado">
          {/* Marcador: iniciales por equipo, fecha usada para la forma y, si aplica, la nota de fecha por defecto. */}
          <div className="marcador">
            <Equipo nombre={resultado.local} rol="local" />
            <div className="marcador-centro">
              <span className="vs">VS</span>
              <span className="fecha-usada">Forma al {formatearFecha(resultado.fecha_forma)}</span>
              {!fechaPedida && <span className="nota-defecto">fecha por defecto</span>}
            </div>
            <Equipo nombre={resultado.visitante} rol="visitante" />
          </div>

          <Probabilidades p={resultado.probabilidades} />

          <h3>Forma reciente (últimos 5 partidos)</h3>
          <div className="leyenda-forma" aria-hidden="true">
            <span style={{ color: 'var(--local)' }}>◀ {resultado.local}</span>
            <span style={{ color: 'var(--visitante)' }}>{resultado.visitante} ▶</span>
          </div>
          <ul className="forma" aria-label={`Comparación de forma: ${resultado.local} a la izquierda, ${resultado.visitante} a la derecha`}>
            {METRICAS.map(([k, nombre, pista, dec]) => (
              <FilaForma key={k} nombre={nombre} pista={pista} decimales={dec}
                         vl={resultado.forma_local[k]} vv={resultado.forma_visitante[k]} />
            ))}
          </ul>

          {/* Aviso siempre visible junto al resultado: la predicción usa datos viejos y el usuario debe saberlo. */}
          <p className="aviso">
            <strong>Datos hasta {formatearFecha(resultado.datos_hasta)}.</strong> La forma se calculó con los 5 partidos anteriores al {formatearFecha(resultado.fecha_forma)}; no incluye nada posterior.
          </p>
        </div>
      ) : (
        <p className="nota">Elige dos equipos y pulsa «Predecir». Aquí verás también las predicciones que pidas en el chat; el aviso con la fecha del último dato aparecerá junto al resultado.</p>
      )}
    </section>
  )
}
