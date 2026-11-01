import { lazy, Suspense, useState } from 'react'
import Chat from './components/Chat.jsx'
// El panel arrastra Recharts (~350 kB). Con import perezoso va en su propio archivo y el chat carga sin esperarlo.
const PanelPrediccion = lazy(() => import('./components/PanelPrediccion.jsx'))
import './App.css'

export default function App() {
  // El estado compartido vive aquí: el chat escribe la última predicción y el panel la lee.
  const [prediccion, setPrediccion] = useState(null)
  // Solo importa en pantallas estrechas, donde se ve una sección a la vez (en anchas se ven las dos).
  const [pestana, setPestana] = useState('chat')

  const mostrarPanel = (p) => { setPrediccion(p); setPestana('panel') }

  return (
    <>
      <a className="saltar" href="#contenido">Saltar al contenido</a>
      <header className="cabecera">
        <h1>Analítica LaLiga</h1>
        <p>Reglamento y pronósticos de Primera División</p>
      </header>

      <div className="pestanas" role="tablist" aria-label="Sección">
        {[['chat', 'Chat'], ['panel', 'Predicción']].map(([id, nombre]) => (
          <button key={id} role="tab" type="button" id={`tab-${id}`} aria-selected={pestana === id}
                  aria-controls={`vista-${id}`} onClick={() => setPestana(id)}>{nombre}</button>
        ))}
      </div>

      <main id="contenido" className="rejilla">
        {/* Ambas vistas siempre montadas: ocultar no desmonta, así el chat no pierde la conversación al cambiar de pestaña. */}
        <div id="vista-chat" role="tabpanel" aria-labelledby="tab-chat" className={pestana === 'chat' ? '' : 'oculta-movil'}>
          <Chat onPrediccion={setPrediccion} onMostrarPanel={mostrarPanel} />
        </div>
        <div id="vista-panel" role="tabpanel" aria-labelledby="tab-panel" className={pestana === 'panel' ? '' : 'oculta-movil'}>
          <Suspense fallback={<p role="status">Cargando panel…</p>}><PanelPrediccion externa={prediccion} /></Suspense>
        </div>
      </main>

      <footer className="pie">Proyecto de tesis. Los pronósticos son estadísticos, no consejos de apuesta.</footer>
    </>
  )
}
