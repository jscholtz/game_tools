# Split chat experiment

This is a disposable local proof of concept, separate from the Streamlit app.
The static frontend runs in the browser; the Flask-SocketIO backend checks local
credentials and routes private messages between each player and the `dm` account.
It uses an in-memory mongomock database for experiment data, not Redis or
existing campaign accounts. The optional read-only bestiary uses MongoDB
separately. The last 20 messages per conversation and
any older unread incoming messages are shown on reconnect. The DM sees one chat window per player account (four for
four players); each player sees only their own conversation with the DM.
Players also have Chat and Notes tabs. Players can create and edit multiple
private Markdown notes. Switching tabs keeps unsaved edits; leaving or logging
out warns about unsaved changes.
The left navigation uses up and down arrow keys to switch tabs.
The Theme selector offers Parchment (default) and Dark. The choice is saved
in browser local storage, separately for each browser and device, and applies
before login. If storage is unavailable, the selector reports that the choice
cannot be saved.
Navigation and primary buttons use the locally hosted Cinzel font; its license
is included in `frontend/assets/fonts/CINZEL-OFL.txt`.
Shared layout and default color tokens live in `frontend/assets/styles/styles.css`; Dark
overrides and its panel treatment live in `frontend/assets/styles/theme-dark.css`. To add a
theme, provide its token and decorative overrides, link its stylesheet, and
add its value to both the selector and the allowlist in `frontend/js/theme.js`.

The page markup is in `frontend/index.html`; feature scripts are in
`frontend/js/`. They run as ordered classic scripts and share the existing
page-level state: keep their order intact, with `app.js` last so session
restoration starts after the feature handlers are registered.
The standalone statblock page remains at `frontend/statblock.html`. Images,
icons, fonts and styles are grouped under `frontend/assets/`; legacy root
favicon files remain available at their original URLs. Backend entry points
and data remain in `backend/`; supporting models and MongoDB bestiary access
are in `backend/app_support/`. The snapshot and credentials remain in
`backend/data/` and are not moved by this reorganization.

The Chat tab shows an account-wide unread count for incoming messages. It
survives reconnects and restarts, including messages received while offline.
Messages are marked read when Chat is selected and the browser tab is visible;
opening Chat in any session clears the count for that account in all sessions.
Existing messages are treated as read when upgrading. Back up the snapshot first: older versions of
the experiment cannot read the new read-position field.

Players also have a Character tab. Each player can view and edit their own
character name, race, gender, portrait, classes and subclass links, passive
perception and insight, armor class, maximum HP, initiative, six ability scores,
movement speeds in feet, description, background and story. Blank numeric
fields mean unknown; no game rules or ability modifiers are calculated.
Portraits support PNG, JPEG and WebP up to 2 MiB. Data is saved to this
experiment's snapshot, not the Streamlit database; it is not automatically
imported. The `dm` account can view every player's full saved sheet, including
description, background and story, in its read-only Characters tab. Players
without a saved character are listed too; use Reload character to refresh.
The sheet groups identity, combat, abilities, senses, movement and narrative
details; the editor uses the same stat groupings.
Other players cannot access these sheets. Concurrent edits are rejected; copy the draft,
cancel and reload before applying it again.

Both roles have an Initiative tab. The `dm` can add combatants without
statblocks, edit initiative and current/maximum hit points, mark them defeated
or hidden, remove them, reorder by initiative and advance to the next living
combatant. Changes to combatant fields require **Save combatant changes**;
other actions save immediately. New combatants are visible by default. Players
see only visible combatants, their names, initiative, defeat status and the
current turn when that combatant is visible. The server never sends hit points,
hidden combatants or saved encounters to players.
When the DM advances the turn, a music reminder appears once per round at
initiative 35, including the first round. If all combatants are on the same
side of 35, it appears when the round starts instead. Use **Reorder by
initiative** to keep turn order aligned with initiative values. The reminder
appears only after a successful turn save.

The DM can save named encounter snapshots and load, overwrite or delete them.
These controls are under the expandable **Saved encounters** section.
Snapshots include the order, turn, visibility and hit points; subsequent live
changes do not alter a saved encounter until overwritten. Connected clients
refresh after changes; use Reload initiative after a disconnect or failed
refresh. Concurrent DM changes are rejected: copy any draft, reload and
reapply it. The tracker and encounters are stored in the experiment snapshot,
separately from Streamlit. Back up the snapshot before upgrading, since older
experiment versions cannot read the new snapshot field.

The `dm` account has a read-only Bestiary tab with standard and custom
creatures from the Streamlit MongoDB collections. Filter by name, type,
challenge rating, size and source, then select a row in the results table to
see its statblock. Creature names in the table are keyboard-accessible buttons.
Source titles are abbreviated in the table; hover for the full title or use
the Source filter, which lists full titles.
Statblocks use the same renderer as Streamlit and retain its parchment styling
in both themes. Trait, action and note text supports inline Markdown emphasis;
raw HTML is displayed as text. Selecting a creature rolls 1d20 plus its `initiative_bonus`,
or its Dexterity modifier if no bonus is stored. The roll is editable, can be
rerolled, and is rolled again after each successful addition. Select a creature
and add it to the current fight with its listed starting hit points. Additions are visible
to players by default, do not reorder the tracker, and preserve the current
turn. Save or reload unsaved initiative edits before adding. Bestiary-linked
combatants have a DM-only **View in bestiary** button, including in restored
encounters, and an **Open statblock in new tab** link for a read-only page.
The new tab copies the current browser session and retrieves the statblock from
the DM-only endpoint; it can be refreshed while that session remains valid.
If a creature is removed from MongoDB, its combatant remains.
Refresh reloads the index; creature details load on selection. Creature editing
is not available here. Indexes above 10,000 combined entries are rejected
explicitly rather than silently truncated.

Bestiary links are stored in the experiment snapshot. Back up the snapshot
before upgrading: older versions of the experiment cannot read these links.

The DM's **Custom creatures** tab stores a separate creature library in the
experiment's mock database and snapshot, not in the Streamlit MongoDB custom
bestiary. Create a new creature or select **Copy to custom creatures** on a
bestiary statblock; the copy is an unsaved draft until saved. Selecting a saved
creature shows its statblock and fight controls; use **Edit creature** to open
the editor. The editor covers statblock fields and an optional initiative bonus.
Separate action paragraphs with blank lines; start an action with
its name followed by a period to emphasize the name.

Saved creatures can be edited and added to the current fight. Initiative rolls
use 1d20 plus the saved bonus, or the Dexterity modifier if blank. Save edits
before adding; the fight uses the saved hit points and links back to the custom
creature and its separate statblock page. Creature edits use revision checks:
if another session saves first, copy your draft and reload before reapplying it.
Back up the snapshot before upgrading: older experiment versions cannot read
the new custom creature collection.

Both roles have a Board tab. The `dm` account can create and edit Markdown
notes, choosing whether each is visible to players; new notes start hidden.
The DM can attach up to five PNG, JPEG, GIF, or WebP images per board note,
up to 2 MiB each. Images appear after the note text; edit a note to add images
or mark existing attachments for removal. Changes take effect when the note is
saved. Attachments follow the note's visibility and are included in the local
snapshot; image metadata is not removed.
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

**Experiment only:** messages, notes, character data and images are not encrypted on the server. Tokens are
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
install the experiment's current dependencies, including Pydantic and Pillow.

To enable the DM bestiary, set `MONGODB_URI` in the backend process environment
before starting it. The experiment does not load the repository `.env` file
automatically. Use a MongoDB account with read access to
`creatures.basic_list` and `game_helper.custom_bestiary`; the backend never
writes to these collections. Missing configuration, connection failures and
invalid data are reported in the Bestiary tab. Other experiment data continues
to use the local snapshot and does not require MongoDB.

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
characters, initiative, saved encounters, board notes, board attachments and token
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
snapshot loses saved accounts, messages, personal and board notes, characters, initiative, encounters and revocations, and may re-import stale legacy
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
