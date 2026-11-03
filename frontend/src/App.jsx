import { useState } from 'react'
import Chat from './components/Chat.jsx'
import PanelPrediccion from './components/PanelPrediccion.jsx'
import './App.css'

// Fecha fija del dataset (docs/datos.md: los datos NO se actualizan). La cabecera se pinta antes de que exista
// cualquier predicción y ningún endpoint la devuelve sola, así que vive aquí; en cada resultado se muestra el
// valor real que manda la API (`datos_hasta`).
const DATOS_HASTA_CABECERA = '25 may 2025'

export default function App() {
  // El estado compartido vive aquí: el chat escribe la última predicción y el panel la lee.
  const [prediccion, setPrediccion] = useState(null)

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
          <li className="chip-estado ambar">Datos hasta el {DATOS_HASTA_CABECERA}</li>
          <li className="chip-estado verde">Modelo local · XGBoost</li>
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
