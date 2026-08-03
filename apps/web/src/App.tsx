import { useEffect, useState } from "react";
import { onAuthStateChanged, signInWithPopup, signOut, type User } from "firebase/auth";
import { auth, googleProvider } from "./firebase";

type MeResponse = {
  uid: string;
  email: string;
  name: string;
  picture: string;
  verified_by: string;
};

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Firebase persists the session; this fires on load and on every
  // sign-in/out, so refreshing the page keeps you logged in.
  useEffect(() => {
    return onAuthStateChanged(auth, (u) => {
      setUser(u);
      setLoading(false);
      setMe(null);
    });
  }, []);

  async function callGateway() {
    if (!user) return;
    setError(null);
    try {
      // The ID token is a signed JWT proving who we are. The gateway
      // verifies its signature server-side — the client is never trusted.
      const token = await user.getIdToken();
      const res = await fetch("/api/me", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Gateway said ${res.status}`);
      setMe(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (loading) return <main className="shell">Loading…</main>;

  return (
    <main className="shell">
      <h1>SiteForge</h1>
      <p className="tagline">The copilot that builds your business website.</p>

      {!user ? (
        <button className="primary" onClick={() => signInWithPopup(auth, googleProvider)}>
          Sign in with Google
        </button>
      ) : (
        <section className="card">
          <div className="row">
            {user.photoURL && <img className="avatar" src={user.photoURL} alt="" />}
            <div>
              <strong>{user.displayName}</strong>
              <div className="muted">{user.email}</div>
            </div>
          </div>

          <div className="actions">
            <button className="primary" onClick={callGateway}>
              Verify me at the gateway
            </button>
            <button onClick={() => signOut(auth)}>Sign out</button>
          </div>

          {me && (
            <pre className="result">{JSON.stringify(me, null, 2)}</pre>
          )}
          {error && <p className="error">{error} — is the gateway running on :8000?</p>}
        </section>
      )}
    </main>
  );
}
