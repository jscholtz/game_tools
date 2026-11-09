# D&D Campaign Helper

The app stores logins, private data, chats, and public data in MongoDB database
`game_helper`. Initiative tracker state is stored in Redis. Configure
`MONGODB_URI`, `JEV_TOKEN`, `REDIS_USERNAME`, and `REDIS_PASSWORD` in a
root-level `.env` file. Copy `.env.example` to `.env` and replace the
placeholder values. Redis host and port can also be overridden there. Keep
`.env` private; it is ignored by Git. Existing process environment variables
override values from `.env`.

On first initiative load, if Redis has no tracker state, the app copies the
saved tracker and default from MongoDB into Redis. Redis holds live tracker
state. Use the DM's **Save snapshot** button to save the current state to
MongoDB's `initiative` collection as a recovery snapshot; this preserves the
configured default tracker. If Redis loses its state, the saved snapshot is
used to initialize it.

The DM's Character tab shows cards for the player login names listed in
`character_cards.toml`, in the configured order. Names are matched
case-insensitively; missing or ambiguous accounts are reported. The file is
loaded into Streamlit session state once per session, so start a new session
after editing it. This selection affects only character cards, not chat access.
Each card shows the character name, the player login in smaller text, and a
bell when that player has unread messages. The DM can edit each character's name,
passive perception, passive insight, armor class, maximum HP, class and subclass
websites, and picture. Unknown stats can remain blank. If passive insight is not stored,
the card derives it as 10 plus the existing Insight modifier when available.
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
class and subclass links, background, and story on their Character tab. The DM
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
The DM can add a selected creature to the initiative tracker with its listed
hit points and a chosen initiative (default 0). Each click adds a separate
combatant; use the tracker to reorder combatants or edit their values.
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

The old Markdown board remains read-only until the DM selects **Migrate public
board**. The preamble becomes a visible Introduction note, and each section
becomes a note with its previous visibility. Migrated dates are blank because
the old board has no creation dates. Standalone image references are copied
into separate image documents; their alt text remains in the note text. Images then
appear after the text rather than inline. Missing or non-binary images stop
migration; the original documents remain untouched. Existing MongoDB image
documents and the legacy Markdown and settings remain in place after migration.

Existing inline Base64 images remain readable and are moved to separate
documents on the next successful note save. Their original filenames were not
stored, so those images receive generated names. Concurrent edits are rejected
rather than overwritten. Copy the draft, cancel, and reopen the editor if a
conflict occurs. Images are written before the note list; failed or conflicting
saves can leave unreferenced image documents. Removing a note or image does not
delete its image document. Each image document and the notes list document
independently remain subject to MongoDB's 16 MiB BSON document limit.

Start Streamlit:

```bash
uv run streamlit run main.py
```

MongoDB collections used: `logins`, `private_data`, `chats`, `public_data`, and
`initiative` in `game_helper`, plus `basic_list` and `display` in `creatures`.
The viewer also supports older images in `public_images` when that collection
is accessible.

To manually verify Redis connectivity, run:

```bash
uv run python tests/check_redis.py
```

This is a live integration check, not an automated test; it requires working
Redis credentials and writes a unique key that expires after 60 seconds.