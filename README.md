## Setup
1. Create and activate a virtual environment:

```zsh
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```zsh
pip install -r requirements.txt
```

3. Apply database migrations:

```zsh
python3 manage.py migrate
```

## Import CSV data
This repo ships with `resources/FutBinCards19.csv`. The app provides a management command `import_playersdata` to load rows into the `Card` model.

Defaults are configured in `auxion/settings.py`:
- `PLAYER_DATA_CSV_PATH`: defaults to `resources/FutBinCards19.csv`
- `PLAYER_DATA_ID_COLUMN`: defaults to `id`

You can override these via environment variables or CLI flags. To import using the included CSV:

```zsh
# Optional: ensure virtualenv active
source .venv/bin/activate

# Seed database from the included CSV
python3 manage.py import_playersdata 
```

Notes:
- `--truncate` clears existing `Card` rows before import.
- If your CSV’s unique identifier column differs, specify it with `--id-column <columnname>`.
- You can also set `PLAYER_DATA_CSV_PATH` and `PLAYER_DATA_ID_COLUMN` as env vars:

```zsh
export PLAYER_DATA_CSV_PATH="$(pwd)/resources/FutBinCards19.csv"
export PLAYER_DATA_ID_COLUMN="id"
```

## Run the app
Start the development server:

```zsh
python3 manage.py runserver
```

Open the browser at `http://127.0.0.1:8000/` (or localhost:8000).

## Docker
Build and run the app in Docker:

```zsh
docker build -t auxion-django .
docker run --rm -p 8000:8000 auxion-django
```

To seed the database in the container using the included CSV, enable the opt-in seeding flag:

```zsh
docker run --rm -p 8000:8000 -e SEED_CSV=true auxion-django
```

Notes:
- The image includes `resources/FutBinCards19.csv`, and the command `import_playersdata` reads it by default (`PLAYER_DATA_CSV_PATH`).
- Seeding on every start can be destructive with `--truncate`; use the `SEED_CSV=true` flag only when you want to seed.
- Alternatively, you can exec into a running container and run the command manually:

```zsh
docker exec -it <container_id_or_name> sh -c "python manage.py import_playersdata --truncate"
```

