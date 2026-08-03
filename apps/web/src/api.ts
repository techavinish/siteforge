import type { User } from "firebase/auth";

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
  return fetch(url, { ...init, headers });
}
