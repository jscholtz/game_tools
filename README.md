# D&D Campaign Helper

The app stores logins, private data, chats, and public data in MongoDB database
`game_helper`. Initiative tracker state is stored in Redis. Configure
`MONGODB_URI`, `JEV_TOKEN`, `REDIS_USERNAME`, and `REDIS_PASSWORD` in a
root-level `.env` file. Copy `.env.example` to `.env` and replace the
placeholder values. Redis host and port can also be overridden there. Keep
`.env` private; it is ignored by Git. Existing process environment variables
override values from `.env`.

DM and player screens use separate service operations. Player initiative
projections omit hidden combatants and hit points; player board reads return
only visible notes and images. Character and private-note operations enforce
ownership, and DM character edits are limited to shared character fields.
These checks use the authenticated server-side session principal; storage
modules remain internal to the application, not independently authenticated APIs.

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