// Same hostname as the frontend dev server (both `localhost`) so the auth session
// cookie is same-site and browsers actually attach it to cross-port fetch requests.
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')