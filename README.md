# D&D Campaign Helper

The app reads and writes data in MongoDB database `game_helper`. Configure
`MONGODB_URI` or `tokens.mongodb.mongo_db_login` in
`.streamlit/secrets.toml`.

To initially upload local data and login hashes, run:

```bash
uv run python upload.py
```

Then start Streamlit:

```bash
uv run streamlit run main.py
```

The app uses the `logins`, `personal_data`, `chats`, `initiative`, and
`public_data` collections.