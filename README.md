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
`initiative`. The viewer also supports older images in `public_images` when
that collection is accessible.

To manually verify Redis connectivity, run:

```bash
uv run python tests/check_redis.py
```

This is a live integration check, not an automated test; it requires working
Redis credentials and writes a unique key that expires after 60 seconds.