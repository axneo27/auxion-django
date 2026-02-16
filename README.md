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


## Firebase Auth Setup (Web + Django)

This app uses Firebase Web Auth on the client and Firebase Admin SDK on the server. These brief steps ensure popups/redirect work and the ID token POST succeeds.

- **COOP header (popups):** Add middleware to set `Cross-Origin-Opener-Policy: same-origin-allow-popups`.

```python
# core/middleware.py
class COOPSameOriginAllowPopupsMiddleware:
		def __init__(self, get_response):
				self.get_response = get_response

		def __call__(self, request):
				response = self.get_response(request)
				response["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
				return response
```

Register it:

```python
# auxion/settings.py
MIDDLEWARE = [
		'django.middleware.security.SecurityMiddleware',
		'django.contrib.sessions.middleware.SessionMiddleware',
		'django.middleware.common.CommonMiddleware',
		'django.middleware.csrf.CsrfViewMiddleware',
		'django.contrib.auth.middleware.AuthenticationMiddleware',
		'django.contrib.messages.middleware.MessageMiddleware',
		'django.middleware.clickjacking.XFrameOptionsMiddleware',
		'core.middleware.COOPSameOriginAllowPopupsMiddleware',
]
```

- **CSRF allowlist (ID token POST):** Ensure your site origin is trusted so the client can POST the Firebase ID token.

```python
# auxion/settings.py
CSRF_TRUSTED_ORIGINS = [
		'https://your-domain.example',
]
```

- **Client fallback (popup → redirect):** Use redirect when popups are blocked and handle the redirect result on load.

```html
<!-- core/templates/core/layout.html -->
<script type="module">
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js";
import { getAuth, GoogleAuthProvider, signInWithPopup, signInWithRedirect, getRedirectResult } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js";

const app = initializeApp({ /* public firebaseConfig */ });
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

getRedirectResult(auth).then(async (result) => {
	if (result && result.user) {
		const idToken = await result.user.getIdToken();
		await fetch('/auth/google/', {
			method: 'POST',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams({ id_token: idToken })
		});
		location.reload();
	}
}).catch(console.error);

document.getElementById('googleLoginBtn')?.addEventListener('click', async () => {
	try {
		const r = await signInWithPopup(auth, provider);
		const idToken = await r.user.getIdToken();
		await fetch('/auth/google/', {
			method: 'POST',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams({ id_token: idToken })
		});
		location.reload();
	} catch (e) {
		const code = e?.code || '';
		if (code === 'auth/popup-blocked' || code === 'auth/popup-closed-by-user' || code === 'auth/cancelled-popup-request') {
			await signInWithRedirect(auth, provider);
		} else {
			console.error(e);
		}
	}
});
</script>
```

- **Authorized domains:** Add your site domain in Firebase Console → Authentication → Settings → Authorized domains.

- **Cross-origin (optional):** If the frontend is on a different origin than Django, enable CORS.

```bash
pip install django-cors-headers
```

```python
# auxion/settings.py
INSTALLED_APPS += ['corsheaders']
MIDDLEWARE = ['corsheaders.middleware.CorsMiddleware'] + MIDDLEWARE
CORS_ALLOWED_ORIGINS = [
		'https://your-frontend.example',
]
```

Notes:
- Firebase Web SDK config keys are public by design; keep Admin SDK credentials server-side.
- See also [core/README.md](core/README.md) for the same snippets near the middleware.

