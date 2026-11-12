# Split chat experiment

This is a disposable local proof of concept, separate from the Streamlit app.
The static frontend runs in the browser; the Flask-SocketIO backend checks local
credentials and broadcasts messages to authenticated users in one shared room.
It does not use MongoDB, Redis, campaign data, or existing accounts. Chat
messages are stored in a local JSON file; the last 20 are restored on reconnect.

**Experiment only:** chat is shared with every authenticated user. Tokens are
stored in browser session storage, where injected JavaScript can read them.
There is no login rate limiting, account administration UI, or production
server. An ngrok tunnel makes the login publicly reachable. Do not use
campaign credentials or sensitive messages.

## Run locally

From the repository root, create a separate environment and install only the
experiment's dependencies:

```bash
python3 -m venv experiments/.venv
experiments/.venv/bin/python -m pip install -r experiments/backend/requirements.txt
```

Create accounts while the backend is stopped. Pick a separate password of at
least 12 characters for each; it is entered interactively:

```bash
experiments/.venv/bin/python experiments/backend/manage_users.py player1
experiments/.venv/bin/python experiments/backend/manage_users.py player2
```

In one terminal, start the backend:

```bash
experiments/.venv/bin/python experiments/backend/app.py
```

In another terminal, start the static frontend:

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory experiments/frontend
```

Open `http://127.0.0.1:8000` in two browser tabs. The default backend URL is
`http://127.0.0.1:5000`. Log in with the accounts you created. Each tab stores
its own session and restores it on refresh; a newly opened tab can inherit a
copy of its opener's session. Tokens expire after eight hours. Log out to
revoke the current token and disconnect its sockets. The Socket.IO client is
loaded from a CDN, so the browser needs internet access.

The backend creates `backend/data/` on first use. `users.json` stores salted,
one-way scrypt password hashes, not reversible encrypted passwords.
`jwt.key` is the signing secret, `history.json` holds chat messages, and
`revoked.json` tracks logged-out tokens until they expire. These local files
are git-ignored; keep them private, back them up if needed, and never put them
in the frontend directory. Deleting the signing key invalidates all tokens;
deleting history or revocation data loses those records. The user-management
command also updates passwords, but changing a password does not invalidate
already issued tokens. Stop the backend before editing users; invalidate all
sessions by removing the signing key while it is stopped if needed. The JSON
storage is intended for one backend process; do not run multiple instances or
edit its files concurrently.

The backend permits frontend origins `http://127.0.0.1:8000` and
`http://localhost:8000` by default. These checks are not authentication and do
not prevent direct non-browser clients from connecting.

## Optional ngrok exposure

The two services remain separate. The following setup uses one public ngrok
domain and one internal endpoint: `experiments/ngrok-policy.json` routes
`/api/` and `/socket.io/` to the backend and all other paths to the frontend.
This avoids assuming that two separate public domains are available on a free
account. An ngrok account, configured agent, and a plan supporting internal
endpoints and the policy are required; check current
[free-plan limits](https://ngrok.com/docs/pricing-limits/free-plan-limits).
Provider features and limits may change.

1. Start the frontend as above.
2. In another terminal, start an internal backend endpoint:

   ```bash
   ngrok http 5000 --url https://split-chat-backend.internal
   ```

3. In another terminal, start the public frontend endpoint:

   ```bash
   ngrok http 8000 --traffic-policy-file experiments/ngrok-policy.json
   ```

4. Copy the public HTTPS origin printed by ngrok. Start or restart the backend
   with that exact frontend origin, without a trailing path:

   ```bash
   FRONTEND_ORIGIN=https://YOUR-NGROK-DOMAIN experiments/.venv/bin/python experiments/backend/app.py
   ```

5. Open the public HTTPS URL. If ngrok displays its browser warning, continue
   through it. The backend URL field defaults to the current HTTPS origin; use
   that same public origin in both tabs. The backend accepts only the configured
   frontend origin and the two localhost origins in browsers.

The frontend adds ngrok's warning-bypass header to login requests and uses
WebSocket-only Socket.IO transport: browsers cannot attach arbitrary headers
to WebSocket handshakes. If the tunnel or network blocks WebSockets, chat will
show a connection error. If the public URL changes, restart the backend with the
new `FRONTEND_ORIGIN`. Stop both ngrok processes when finished.

If your account instead provides two distinct public domains, they can be
routed separately to ports 8000 and 5000. Configure `FRONTEND_ORIGIN` as the
frontend domain and enter the backend domain in the login screen. An HTTPS
frontend cannot connect to an HTTP backend because browsers block mixed content.
