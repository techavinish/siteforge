import type { User } from "firebase/auth";

// Firebase Hosting rewrites BUFFER responses — SSE cannot stream through
// them. On the hosted app, agent calls go straight to the agent's own
// Cloud Run URL (CORS-allowed); locally the vite proxy streams fine.
export const AGENT_BASE = location.hostname.endsWith("web.app")
  ? "https://agent-247435823944.asia-south1.run.app"
  : "";

export function agentUrl(path: string): string {
  return path.startsWith("/agent") ? AGENT_BASE + path : path;
}

// every /agent call carries the Firebase ID token — the BE verifies it and
// derives identity from it; the client never claims a uid
let authUser: User | null = null;

export function setAuthUser(u: User | null) {
  authUser = u;
}

export async function idToken(): Promise<string> {
  return authUser ? authUser.getIdToken() : "";
}

export async function authFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = await idToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(agentUrl(url), { ...init, headers });
}
