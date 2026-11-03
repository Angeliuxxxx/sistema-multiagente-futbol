import { useEffect, useState } from 'react'
import { obtenerEstado } from './api.js'
import { formatearFecha } from './fechas.js'
import Chat from './components/Chat.jsx'
import PanelPrediccion from './components/PanelPrediccion.jsx'
import './App.css'

export default function App() {
  // El estado compartido vive aquí: el chat escribe la última predicción y el panel la lee.
  const [prediccion, setPrediccion] = useState(null)
  // Fecha real del último dato, la manda la API (/health): antes era una constante escrita a mano y quedaba desactualizada.
  const [datosHasta, setDatosHasta] = useState('')
  useEffect(() => { obtenerEstado().then((e) => setDatosHasta(e.datos_hasta)).catch(() => {}) }, [])

  // En pantallas estrechas el panel queda debajo del chat: «ver detalle» lleva hasta él en vez de cambiar de pestaña.
  const mostrarPanel = (p) => {
    setPrediccion(p)
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
        <div id="vista-chat"><Chat onPrediccion={setPrediccion} onMostrarPanel={mostrarPanel} /></div>
        <div id="vista-panel"><PanelPrediccion externa={prediccion} /></div>
      </main>

      <footer className="pie">Proyecto de tesis. Los pronósticos son estadísticos, no consejos de apuesta.</footer>
    </>
  )
}
