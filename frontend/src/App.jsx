import { useEffect, useState } from 'react'
import { obtenerEstado } from './api.js'
import { formatearFecha } from './fechas.js'
import Chat from './components/Chat.jsx'
import PanelPrediccion from './components/PanelPrediccion.jsx'
import Posiciones from './components/Posiciones.jsx'
import Registro from './components/Registro.jsx'
import './App.css'

const PESTANAS = [['prediccion', 'Predicción'], ['posiciones', 'Posiciones'], ['acierto', 'Acierto']]

// Flechas izquierda/derecha cambian de pestaña (patrón WAI-ARIA de «tabs»); el foco acompaña a la pestaña activa.
function moverPestana(e, actual, setPestana) {
  const i = PESTANAS.findIndex(([id]) => id === actual)
  const paso = { ArrowRight: 1, ArrowLeft: -1 }[e.key]
  if (!paso) return
  e.preventDefault()
  const sig = PESTANAS[(i + paso + PESTANAS.length) % PESTANAS.length][0]
  setPestana(sig)
  document.getElementById(`tab-${sig}`)?.focus()
}

export default function App() {
  // El estado compartido vive aquí: el chat escribe la última predicción y el panel la lee.
  const [prediccion, setPrediccion] = useState(null)
  const [pestana, setPestana] = useState('prediccion')
  // Fecha real del último dato, la manda la API (/health): antes era una constante escrita a mano y quedaba desactualizada.
  const [datosHasta, setDatosHasta] = useState('')
  useEffect(() => { obtenerEstado().then((e) => setDatosHasta(e.datos_hasta)).catch(() => {}) }, [])

  // En pantallas estrechas el panel queda debajo del chat: «ver detalle» lleva hasta él en vez de cambiar de pestaña.
  const mostrarPanel = (p) => {
    setPrediccion(p)
    setPestana('prediccion')
    document.getElementById('vista-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      <a className="saltar" href="#contenido">Saltar al contenido</a>
      <header className="cabecera">
        <div className="marca">
          {/* Círculo de centro de campo: línea media + círculo + punto. Decorativo, el título ya nombra la app. */}
          <svg className="marca-logo" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
            <circle cx="24" cy="24" r="21" fill="none" stroke="currentColor" strokeWidth="2.5" />
            <line x1="24" y1="3" x2="24" y2="45" stroke="currentColor" strokeWidth="2.5" />
            <circle cx="24" cy="24" r="4" fill="currentColor" />
          </svg>
          <div>
            <h1>Analítica LaLiga</h1>
            <p>Reglamento y pronósticos de Primera División</p>
          </div>
        </div>
        <ul className="chips-estado" aria-label="Estado del sistema">
          {datosHasta && <li className="chip-estado verde">Datos hasta el {formatearFecha(datosHasta)}</li>}
          <li className="chip-estado verde">XGBoost · modelo B</li>
        </ul>
      </header>

      <main id="contenido" className="rejilla">
        <div id="vista-chat"><Chat onPrediccion={(p) => { setPrediccion(p); setPestana('prediccion') }} onMostrarPanel={mostrarPanel} /></div>
        <div id="vista-panel">
          {/* Pestañas accesibles (flechas ← → para moverse). Las tres vistas quedan montadas y solo se ocultan, para no perder el estado del panel. */}
          <div className="pestanas" role="tablist" aria-label="Vistas">
            {PESTANAS.map(([id, nombre]) => (
              <button key={id} type="button" role="tab" id={`tab-${id}`} aria-selected={pestana === id}
                      aria-controls={`vista-${id}`} tabIndex={pestana === id ? 0 : -1}
                      onClick={() => setPestana(id)} onKeyDown={(e) => moverPestana(e, pestana, setPestana)}>
                {nombre}
              </button>
            ))}
          </div>
          <div role="tabpanel" id="vista-prediccion" aria-labelledby="tab-prediccion" hidden={pestana !== 'prediccion'}>
            <PanelPrediccion externa={prediccion} />
          </div>
          <div role="tabpanel" id="vista-posiciones" aria-labelledby="tab-posiciones" hidden={pestana !== 'posiciones'}>
            <Posiciones activa={pestana === 'posiciones'} />
          </div>
          <div role="tabpanel" id="vista-acierto" aria-labelledby="tab-acierto" hidden={pestana !== 'acierto'}>
            <Registro activa={pestana === 'acierto'} />
          </div>
        </div>
      </main>

      <footer className="pie">Proyecto de tesis. Los pronósticos son estadísticos, no consejos de apuesta.</footer>
    </>
  )
}
