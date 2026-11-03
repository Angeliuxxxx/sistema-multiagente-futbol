const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

// «2025-06-01» → «1 jun 2025». Se parte el texto a mano en vez de usar new Date(): un ISO sin hora se interpreta
// como UTC y, en husos horarios al oeste, el día mostrado saldría uno menos. Si el formato no es AAAA-MM-DD
// se devuelve tal cual, para no ocultar un dato raro con un «NaN».
export function formatearFecha(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '')
  if (!m || +m[2] < 1 || +m[2] > 12) return iso ?? ''
  return `${+m[3]} ${MESES[+m[2] - 1]} ${m[1]}`
}
