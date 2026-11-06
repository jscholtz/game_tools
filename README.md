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

Start Streamlit:

```bash
uv run streamlit run main.py
```

MongoDB collections used: `logins`, `private_data`, `chats`, `public_data`, and
`initiative`.

To manually verify Redis connectivity, run:

```bash
uv run python tests/check_redis.py
```

This is a live integration check, not an automated test; it requires working
Redis credentials and writes a unique key that expires after 60 seconds.