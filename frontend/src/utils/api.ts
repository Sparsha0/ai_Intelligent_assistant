const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function chatRequest(message: string, mode: string = 'auto') {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, mode }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function getHealth() {
  const res = await fetch(`${BASE}/health`)
  return res.json()
}

export async function getRAGStats() {
  const res = await fetch(`${BASE}/rag/stats`)
  return res.json()
}

export async function ingestText(text: string, source: string) {
  const res = await fetch(`${BASE}/rag/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, source }),
  })
  return res.json()
}

export async function ingestFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/rag/ingest/file`, { method: 'POST', body: form })
  return res.json()
}

export async function listTools() {
  const res = await fetch(`${BASE}/tools/list`)
  return res.json()
}

export async function runTool(tool_name: string, params: Record<string, unknown>) {
  const res = await fetch(`${BASE}/tools/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_name, params }),
  })
  return res.json()
}

export async function getTokenUsage() {
  const res = await fetch(`${BASE}/observability/tokens`)
  return res.json()
}
