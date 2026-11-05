# D&D Campaign Helper

The app reads and writes data in MongoDB database `game_helper`. Configure
`MONGODB_URI` and `JEV_TOKEN` in a root-level `.env` file. Copy
`.env.example` to `.env` and replace the placeholder values. Keep `.env`
private; it is ignored by Git. Existing process environment variables override
values from `.env`.

To initially upload local data and login hashes, run:

```bash
uv run python upload.py
```

Then start Streamlit:

```bash
uv run streamlit run main.py
```

The app uses the `logins`, `private_data`, `chats`, `initiative`, and
`public_data` collections.