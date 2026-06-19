import { useState } from 'react'

function App() {
  const [eps, setEps] = useState('FAMISANAR EPS')
  const [codigoGlosa, setCodigoGlosa] = useState('TA5801')
  const [valorObjetado, setValorObjetado] = useState('1980300')
  const [textoGlosa, setTextoGlosa] = useState('Se aplica glosa por cuanto las tarifas cobradas no corresponden a lo pactado en el anexo de medicina interna.')
  
  // Selector de ruta por si tu backend usa un prefijo diferente
  const [rutaApi, setRutaApi] = useState('http://localhost:8000/api/glosas/analizar')
  
  const [cargando, setCargando] = useState(false)
  const [dictamen, setDictamen] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  const handleAnalizar = async (e: React.FormEvent) => {
    e.preventDefault()
    setCargando(true)
    setError(null)
    setDictamen(null)

    const datosGlosa = {
      eps_pagador: eps,
      codigo_glosa: codigoGlosa,
      valor_objetado: parseFloat(valorObjetado) || 0,
      texto_glosa: textoGlosa,
      etapa: "Inicial",
      tono: "Conciliador"
    }

    try {
      const respuesta = await fetch(rutaApi, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(datosGlosa)
      })

      if (!respuesta.ok) {
        const errData = await respuesta.json()
        throw new Error(errData.detail || `Error ${respuesta.status}: No se pudo procesar.`);
      }

      const resultado = await respuesta.json()
      setDictamen(resultado)
    } catch (err: any) {
      setError(err.message || 'Error de red. Verifica si la consola de Python está encendida.')
    } finally {
      setCargando(false)
    }
  }

  return (
    <div style={{ padding: '2rem', fontFamily: 'system-ui, sans-serif', backgroundColor: '#f1f5f9', minHeight: '100vh' }}>
      <header style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <h1 style={{ color: '#1e3a8a', margin: '0 0 0.5rem 0' }}>🏥 Panel de Auditoría IA (Local)</h1>
        <p style={{ color: '#475569', margin: 0 }}>Modelos en cadena: Groq (Llama 3) ➔ Gemini ➔ Cohere</p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
        
        {/* COLUMNA IZQUIERDA */}
        <div style={{ backgroundColor: '#ffffff', padding: '1.5rem', borderRadius: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}>
          <h2 style={{ color: '#0f172a', fontSize: '1.25rem', marginTop: 0, borderBottom: '2px solid #e2e8f0', paddingBottom: '0.5rem' }}>Datos de la Objeción</h2>
          
          <form onSubmit={handleAnalizar} style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontWeight: '600', marginBottom: '0.25rem', fontSize: '0.9rem', color: '#b91c1c' }}>⚡ Ajuste de Ruta Técnica Local</label>
              <select value={rutaApi} onChange={(e) => setRutaApi(e.target.value)} style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '2px solid #b91c1c', backgroundColor: '#fff5f5', fontWeight: 'bold' }}>
                <option value="http://localhost:8000/api/glosas/analizar">Opción 1: /api/glosas/analizar</option>
                <option value="http://localhost:8000/glosas/analizar">Opción 2: /glosas/analizar</option>
                <option value="http://localhost:8000/api/v1/glosas/analizar">Opción 3: /api/v1/glosas/analizar</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontWeight: '600', marginBottom: '0.25rem', fontSize: '0.9rem' }}>EPS / Entidad Pagadora</label>
              <select value={eps} onChange={(e) => setEps(e.target.value)} style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1' }}>
                <option value="FAMISANAR EPS">FAMISANAR EPS</option>
                <option value="NUEVA EPS">NUEVA EPS</option>
                <option value="COOSALUD">COOSALUD</option>
                <option value="COMPENSAR">COMPENSAR</option>
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontWeight: '600', marginBottom: '0.25rem', fontSize: '0.9rem' }}>Código de Glosa</label>
                <input type="text" value={codigoGlosa} onChange={(e) => setCodigoGlosa(e.target.value)} style={{ width: '90%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontWeight: '600', marginBottom: '0.25rem', fontSize: '0.9rem' }}>Valor Objetado ($)</label>
                <input type="number" value={valorObjetado} onChange={(e) => setValorObjetado(e.target.value)} style={{ width: '90%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1' }} />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontWeight: '600', marginBottom: '0.25rem', fontSize: '0.9rem' }}>Texto Completo de la Glosa</label>
              <textarea value={textoGlosa} onChange={(e) => setTextoGlosa(e.target.value)} rows={4} style={{ width: '97%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', resize: 'vertical' }} />
            </div>

            <button type="submit" disabled={cargando} style={{ backgroundColor: cargando ? '#94a3b8' : '#2563eb', color: 'white', padding: '0.75rem', border: 'none', borderRadius: '6px', fontWeight: 'bold', cursor: cargando ? 'not-allowed' : 'pointer', fontSize: '1rem' }}>
              {cargando ? '🔄 Procesando Escuadrón de IA...' : '🧠 Analizar con IA'}
            </button>
          </form>
        </div>

        {/* COLUMNA DERECHA */}
        <div style={{ backgroundColor: '#ffffff', padding: '1.5rem', borderRadius: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)', display: 'flex', flexDirection: 'column' }}>
          <h2 style={{ color: '#0f172a', fontSize: '1.25rem', marginTop: 0, borderBottom: '2px solid #e2e8f0', paddingBottom: '0.5rem' }}>Respuesta Técnico-Jurídica</h2>
          
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: '1rem' }}>
            {(!cargando && !dictamen && !error) && (
              <p style={{ color: '#94a3b8', textAlign: 'center' }}>Presiona "Analizar con IA" para redactar la defensa legal local.</p>
            )}

            {cargando && (
              <div style={{ textAlign: 'center' }}>
                <p style={{ color: '#2563eb', fontWeight: 'bold', fontSize: '1.1rem' }}>🔄 Conectando...</p>
                <p style={{ color: '#64748b', fontSize: '0.9rem' }}>Llamando a tus llaves gratuitas de IA configuradas.</p>
              </div>
            )}

            {error && (
              <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fca5a5', padding: '1rem', borderRadius: '8px', color: '#991b1b', width: '100%' }}>
                <strong>⚠️ Fallo en el proceso:</strong>
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.9rem' }}>{error}</p>
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.8rem', color: '#475569' }}>Prueba cambiando la "Ruta Técnica Local" arriba a la izquierda.</p>
              </div>
            )}

            {dictamen && (
              <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', backgroundColor: '#f8fafc', padding: '0.75rem', borderRadius: '6px', fontSize: '0.85rem' }}>
                  <div><strong>Acción sugerida:</strong> {dictamen.accion || 'DEFENDER_TOTAL'}</div>
                  <div><strong>Monto a defender:</strong> ${dictamen.valor_defender || valorObjetado}</div>
                </div>
                <div style={{ flex: 1, backgroundColor: '#0f172a', color: '#e2e8f0', padding: '1rem', borderRadius: '8px', fontFamily: 'monospace', fontSize: '0.85rem', whiteSpace: 'pre-wrap', overflowY: 'auto', maxHeight: '300px', textAlign: 'left' }}>
                  {dictamen.argumento || JSON.stringify(dictamen, null, 2)}
                </div>
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}

export default App