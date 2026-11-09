# D&D Campaign Helper

The app stores logins, private data, chats, and public data in MongoDB database
`game_helper`. Initiative tracker state is stored in Redis. Configure
`MONGODB_URI`, `JEV_TOKEN`, `REDIS_USERNAME`, and `REDIS_PASSWORD` in a
root-level `.env` file. Copy `.env.example` to `.env` and replace the
placeholder values. Redis host and port can also be overridden there. Keep
`.env` private; it is ignored by Git. Existing process environment variables
override values from `.env`.

## Application structure

`main.py` is the Streamlit entry point. It loads login records when a login is
submitted, handles login and logout, and assembles tabs using the role stored in
Streamlit session state. The authenticated session also retains the player-name
list used by DM views, so normal app reruns do not reload login records or
recheck account membership. A user's login or role changes, and changes to the
DM's player list, take effect in each session after that session logs out and
logs in again. The app has no separate page directory: tab rendering and
supporting modules are in `tab_views/`.

The main interaction path is:

1. `main.py` renders a tab by calling a function in a tab view.
2. The view handles Streamlit widgets, presentation, and session state.
3. Service modules apply role and ownership checks, validate operations, and
   coordinate app behavior.
4. Storage modules read or write MongoDB or Redis.

### Tabs

| Tab | Player view | DM view |
| --- | --- | --- |
| **Character** | View and edit own character details, stats, classes, picture, and private text. | View configured player character cards and edit shared character details. |
| **Notes** | Create, edit, and delete private notes. | Not shown. |
| **Public Board** | Read notes and images marked visible to players. | Create, edit, delete, and set note visibility; manage images. |
| **Messages with DM** | Chat with the DM; conversation refreshes automatically. | View player conversations, unread counts, and send replies. |
| **Initiative Tracker** | See visible combatants, initiative, and turn status. | Manage combatants, HP, visibility, turn order, and tracker snapshots. |
| **Bestiary** | Not shown. | Filter creatures, view stat blocks, and add creatures to initiative. |

Tabs are role-dependent: players get **Notes**, while the DM gets **Bestiary**.
Both roles get the other four tabs.

### Module responsibilities

- `tab_views/character.py`, `notes.py`, `public_board.py`, `messages.py`,
  `initiative.py`, and `bestiary.py` render their respective tab interfaces.
- `auth_service.py` loads and checks logins. `principal.py` represents the
  authenticated account and provides role guards.
- `character_service.py`, `board_service.py`, `user_data.py`,
  `initiative_service.py`, and `bestiary_service.py` contain feature operations
  and access checks. Views call these rather than directly implementing
  feature rules.
- `database.py` is the MongoDB access layer. `initiative_store.py` is the Redis
  and MongoDB storage layer for initiative state.
- `data_models.py` defines validated records for logins, characters, notes,
  chats, public-board data, and bestiary entries. `initiative_models.py`
  defines tracker and combatant records.
- `config.py` loads `.env` settings and `character_cards.toml`.
  `message_injection.py` provides the external text-screening client used for
  chat messages and private notes.
- `stat_blocks.py` renders Bestiary stat blocks in sandboxed frames.

At the repository root, `pyproject.toml`, `requirements.txt`, and `uv.lock`
describe the Python project and dependencies. `tests/` contains the bestiary
data validation test and a manual Redis connectivity check; `bin/` contains
the ngrok helper script.

DM and player screens use separate service operations. Player initiative
projections omit hidden combatants and hit points; player board reads return
only visible notes and images. Character and private-note operations enforce
ownership, and DM character edits are limited to shared character fields.
These checks use the authenticated server-side session principal; storage
modules remain internal to the application, not independently authenticated APIs.
Character edits, initiative combatant updates, board edits, bestiary filtering,
authentication checks, and message/note screening live in their respective
services; views handle input, presentation, and session state.

On first initiative load, if Redis has no tracker state, the app copies the
saved tracker and default from MongoDB into Redis. Redis holds live tracker
state. Use the DM's **Save snapshot** button to save the current state to
MongoDB's `initiative` collection as a recovery snapshot; this preserves the
configured default tracker. If Redis loses its state, the saved snapshot is
used to initialize it.

Every initiative combatant has a boolean `visible` field. The DM can toggle
**Visible** per combatant; unchecked entries are omitted from the player view
but remain in the DM's turn order. Manually added combatants start visible;
Bestiary additions start hidden. Existing current and default tracker states
in Redis and MongoDB must have this field before deploying this version.
Initiative state is validated when loaded and saved: `current_turn_id` must
be a string or null, combatant fields must have their expected types, and hit
points must be between zero and the positive maximum. Legacy combatants
must have explicit current and maximum HP. Unrecognized tracker and combatant
fields are preserved.

The DM's Character tab shows cards for the player login names listed in
`character_cards.toml`, in the configured order. Names are matched
case-insensitively; missing or ambiguous accounts are reported. The file is
loaded into Streamlit session state once per session, so start a new session
after editing it. This selection affects only character cards, not chat access.
Each card shows the character name, the player login in smaller text, and a
bell when that player has unread messages. The DM can edit each character's name,
passive perception, passive insight, armor class, maximum HP, class and subclass
websites, and picture. Unknown stats can remain blank.
Values and the uploaded picture are stored in the player's `private_data`
document. A picture shares the MongoDB 16 MiB document limit with that player's
other private data. A character's `classes` field is an ordered list of objects
with string fields `class_name`, `class_url`, `subclass_name`, `subclass_url`,
and `levels`. Players and the DM can add or remove classes in the character
editor; levels may be blank or a positive whole number. Class and subclass names
link to their reference sites when URLs are available; links must use HTTP or
HTTPS. Only `classes` entries are displayed; existing single-class fields are
not read. Characters without `classes` start with an empty class editor.
Players can view and edit their own character name, portrait, tracked stats,
class and subclass links, description, background, and story on their Character tab. The DM
can edit the shared details but does not see the background or story in the DM
view. The player view shows an editable initiative bonus, defaulting to +0 when
not stored. Background, story, and initiative bonus are stored in the player's
`private_data` document.

Character, private-note, chat message, and public-board data are validated at
the MongoDB boundary, as are login records and bestiary index and display
projections. Private notes must be a list of objects with string
`id`, `text`, and `created_at` fields; an absent field means no notes. Existing
string-valued `notes` fields must be migrated to that format before the affected
players can use their notes. Invalid values are reported and are not overwritten.

The DM-only **Bestiary** searches the `creatures.basic_list` MongoDB collection
by name, type, challenge rating, size, and source. Filters appear on the left;
the matching creature selector and stat block appear on the right. Selecting a
result loads its HTML stat block from `creatures.display` in a sandboxed frame,
with external resources blocked. Search fields and selected stat blocks are
cached for the app's lifetime; restart the app to pick up database changes.
The DM can add a selected creature to the initiative tracker with a chosen
name, its listed hit points, and a chosen initiative (default 0). The name
defaults to the creature's name. Each click adds a separate combatant; use the
tracker to reorder combatants or edit their values.
Newly added Bestiary combatants have a DM-only open-in-new-tab icon next to
their name in the tracker, which opens a stat-block snapshot; allow popups if blocked.
Existing combatants without a creature identifier must be re-added to use it.

The Public Board stores an ordered `notes` list in the `public_data` document
`public_notes`. Each note contains `header`, `date`, `text`, `visible`, and
`images`; images are references to separate `public_image:<id>` documents in
`public_data`.
Each image document stores its original filename and binary contents. Images
appear after the Markdown text with their filenames as captions.
Notes remain in creation order, including after edits. The DM can add, edit,
delete, upload or remove images, and control visibility for each note. New
notes are hidden by default. Dates are editable strings; new notes start with
the current date in Europe/Amsterdam.

Concurrent edits are rejected rather than overwritten. Copy the draft, cancel,
and reopen the editor if a conflict occurs. Images are written before the note
list; failed or conflicting
saves can leave unreferenced image documents. Removing a note or image does not
delete its image document. Each image document and the notes list document
independently remain subject to MongoDB's 16 MiB BSON document limit.

Start Streamlit:

```bash
uv run streamlit run main.py
```

MongoDB collections used: `logins`, `private_data`, `chats`, `public_data`, and
`initiative` in `game_helper`, plus `basic_list` and `display` in `creatures`.

Before upgrading another database, migrate older data: initiative combatants
need explicit HP and visibility fields; public notes must use `image:` references
to documents in `public_data`; character descriptions and classes must use
`character_description` and `classes`; derived passive insight must be stored as
`passive_insight`; and incoming DM messages need a boolean `dm_read` field. The
old Markdown board, inline images, older image collection, and single-class
character fields are no longer read.

To manually verify Redis connectivity, run:

```bash
uv run python tests/check_redis.py
```

This is a live integration check, not an automated test; it requires working
Redis credentials and writes a unique key that expires after 60 seconds.

To validate every bestiary index entry and stat-block display against the
application models, run the read-only integration test against the MongoDB
configured by `MONGODB_URI`:

```bash
uv run python -m unittest discover -s tests -p test_bestiary_data.py
```

The test fails if either collection is empty, any record is invalid, or an
indexed creature has no display.

## Low-priority TODO

- Replace SHA-256 password hashes with a password-specific scheme or managed
  authentication, with a migration plan.
- Revisit the privacy and availability trade-offs of external screening for
  messages and private notes. External screening is currently intentional.