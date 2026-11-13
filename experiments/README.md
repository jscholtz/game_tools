# Split chat experiment

This is a disposable local proof of concept, separate from the Streamlit app.
The static frontend runs in the browser; the Flask-SocketIO backend checks local
credentials and routes private messages between each player and the `dm` account.
It uses an in-memory mongomock database, not a MongoDB server, Redis, campaign
data, or existing campaign accounts. The last 20 messages per conversation are
shown on reconnect. The DM sees one chat window per player account (four for
four players); each player sees only their own conversation with the DM.
Players also have Chat and Notes tabs. Players can create and edit multiple
private Markdown notes. Switching tabs keeps unsaved edits; leaving or logging
out warns about unsaved changes. An unread-chat indicator is not implemented yet.

Both roles have a Board tab. The `dm` account can create and edit Markdown
notes, choosing whether each is visible to players; new notes start hidden.
The DM sees both published and hidden notes, while the server returns only
published notes to players. Saving persists immediately and notifies connected
clients to refresh; use Refresh board if disconnected or a refresh fails.
Concurrent DM edits to the same note are rejected rather than overwritten:
copy unsaved edits if needed, refresh the board and reopen the note.
Personal and board notes have headers and expand from a collapsed header to
show their content and last-save time in the browser's local time. Each note
is limited to 100,000 characters and each header to 200 characters. Concurrent
edits to the same personal note are also rejected; refresh notes and reopen it.
Existing personal text becomes one note titled "Personal notes"; existing board
notes become "Untitled". Their original save time is unknown until edited.
The snapshot is upgraded when the backend starts; back it up before upgrading,
because older backend versions cannot read the new personal-note format.
Deletion is not implemented.

**Experiment only:** messages and notes are not encrypted on the server. Tokens are
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

For an existing experiment environment, rerun the `pip install` command to
install the experiment's current dependencies, including Pydantic.

Create accounts while the backend is stopped. Pick a separate password of at
least 8 characters for each; it is entered interactively:

```bash
experiments/.venv/bin/python experiments/backend/manage_users.py dm
experiments/.venv/bin/python experiments/backend/manage_users.py player1
experiments/.venv/bin/python experiments/backend/manage_users.py player2
```

The `dm` username receives the `dm` role; other new accounts default to
`player`. To assign a different role, use `--role dm` or `--role player`
(the `dm` account cannot be assigned `player`). Updating an existing account
without `--role` keeps its role. Existing hash-only accounts migrate on load:
`dm` becomes `dm`, and all other accounts become `player`.

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
loaded from a CDN, as are the Markdown parser and HTML sanitizer used by the
board, so the browser needs internet access. Board Markdown is sanitized
before display; embedded images may load from external URLs.
Login and session verification return the account role. The server verifies
participants on every message and filters history and live delivery. Only the
account named `dm` can use the DM chat; additional DM-role accounts cannot use
private chat. Messages from the old shared chat have no recipient and are not
displayed in private conversations.

The backend creates `backend/data/` on first use. Accounts, chat, personal notes,
board notes and token
revocations live in mongomock collections. Passwords are stored as salted,
one-way scrypt hashes, not reversible encrypted passwords. `jwt.key` remains
the separate signing secret.

Collections are saved in `mongo-snapshot.json` on startup, after each change,
and on normal shutdown (including Ctrl+C and SIGTERM). A snapshot write must
succeed before a message, personal or board note, logout or account update is acknowledged. When
there is no snapshot, existing `users.json`, `history.json` and `revoked.json`
are imported. Older snapshots without a `users` field import accounts from
`users.json` while preserving the snapshot's messages and revocations. The
legacy files are left untouched; after migration the snapshot takes
precedence and legacy files no longer receive updates. Stop the backend before
restoring or editing data or running the account-management command.

These local files are git-ignored; keep them private, back them up if needed,
and never put them in the frontend directory. Messages, notes and snapshots are not
encrypted. Deleting the signing key invalidates all tokens; deleting the
snapshot loses saved accounts, messages, personal and board notes, and revocations, and may re-import stale legacy
data. An abrupt termination can bypass shutdown; the most recent successful
per-change snapshot remains available. The user-management
command also updates passwords, but changing a password does not invalidate
already issued tokens. Stop the backend before editing users; invalidate all
sessions by removing the signing key while it is stopped if needed. The JSON
storage is intended for one backend process; do not run multiple instances or
edit its files concurrently. Mongomock is a limited MongoDB simulation, not a
production database or a complete substitute for a MongoDB server.

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
