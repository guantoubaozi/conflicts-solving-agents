const BASE = '/api'

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export const api = {
  getConfig: () => req<{ api_url: string; api_key_masked: string; model_name: string }>('GET', '/config'),
  putConfig: (api_url: string, api_key: string, model_name = 'gpt-4o') => req('PUT', '/config', { api_url, api_key, model_name }),

  listDebates: () => req<any[]>('GET', '/debates'),
  createDebate: (proposition: string, created_by = 'user', background = '') =>
    req<{ debate_id: string }>('POST', '/debates', { proposition, created_by, background }),
  getDebate: (id: string) => req<any>('GET', `/debates/${id}`),
  deleteDebate: (id: string) => req('DELETE', `/debates/${id}`),
  startDebate: (id: string) => req('POST', `/debates/${id}/start`, {}),
  updateBackground: (debateId: string, background: string) =>
    req('PUT', `/debates/${debateId}/background`, { background }),

  addParty: (debateId: string, name: string, soul = '') =>
    req<any>('POST', `/debates/${debateId}/parties`, { name, soul }),
  listParties: (debateId: string) => req<any[]>('GET', `/debates/${debateId}/parties`),
  updatePartySoul: (debateId: string, partyId: string, soul: string) =>
    req<any>('PUT', `/debates/${debateId}/parties/${partyId}/soul`, { soul }),

  getStance: (debateId: string, partyId: string) =>
    req<any>('GET', `/debates/${debateId}/parties/${partyId}/stance`),
  submitStance: (debateId: string, partyId: string, data: any) =>
    req('POST', `/debates/${debateId}/parties/${partyId}/stance`, data),

  getSolutions: (debateId: string, round: number) =>
    req<any[]>('GET', `/debates/${debateId}/rounds/${round}/solutions`),
  getJudgeSummary: (debateId: string, round: number) =>
    req<any>('GET', `/debates/${debateId}/rounds/${round}/judge-summary`),
  confirmRound: (debateId: string, round: number, partyId: string) =>
    req('POST', `/debates/${debateId}/rounds/${round}/confirm?party_id=${partyId}`, {}),

  getChangelogs: (debateId: string, partyId: string) =>
    req<any[]>('GET', `/debates/${debateId}/parties/${partyId}/changelogs`),

  appendFact: (debateId: string, partyId: string, content: string, round: number) =>
    req<any>('POST', `/debates/${debateId}/parties/${partyId}/facts/append`, { content, round }),

  runSolutionPhase: (debateId: string, round: number) =>
    req('POST', `/debates/${debateId}/rounds/${round}/run-solution`, {}),
  runJudgePhase: (debateId: string, round: number) =>
    req('POST', `/debates/${debateId}/rounds/${round}/run-judge`, {}),
  runDebatePhase: (debateId: string, round: number) =>
    req('POST', `/debates/${debateId}/rounds/${round}/run-debate`, {}),

  requestFinal: (debateId: string, round: number, partyId: string) =>
    req<any>('POST', `/debates/${debateId}/rounds/${round}/request-final`, { party_id: partyId }),
  voteFinal: (debateId: string, round: number, partyId: string, agree: boolean) =>
    req<any>('POST', `/debates/${debateId}/rounds/${round}/vote-final`, { party_id: partyId, agree }),
}
