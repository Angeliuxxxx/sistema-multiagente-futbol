# Frontend — Analítica LaLiga

Chat (reglamento + pronósticos) y panel de predicción. React + Vite (JavaScript) + Recharts, sin librerías de componentes.

## Arranque (dos terminales)
```bash
# Terminal 1 — backend (desde la raíz del repo; Ollama debe estar corriendo para las preguntas de reglamento)
cd backend && ../venv/bin/uvicorn app.main:app --port 8000

# Terminal 2 — frontend
cd frontend
cp .env.example .env      # opcional: solo si el backend no está en http://127.0.0.1:8000
npm install
npm run dev               # http://127.0.0.1:5173
```
Otros comandos: `npm run build` (genera `dist/`), `npm run lint`.

Más detalle y decisiones de diseño: [`docs/frontend.md`](../docs/frontend.md).
