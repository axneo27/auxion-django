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
python3 manage.py import_playersdata --truncate
```

Notes:
- `--truncate` clears existing `Card` rows before import.
- If your CSV’s unique identifier column differs, specify it with `--id-column <columnname>`.
- You can also set `PLAYER_DATA_CSV_PATH` and `PLAYER_DATA_ID_COLUMN` as env vars:

```zsh
export PLAYER_DATA_CSV_PATH="$(pwd)/resources/FutBinCards19.csv"
export PLAYER_DATA_ID_COLUMN="id"
python3 manage.py import_playersdata --truncate
```

## Run the app
Start the development server:

```zsh
python3 manage.py runserver
```

Open the browser at `http://127.0.0.1:8000/`.

