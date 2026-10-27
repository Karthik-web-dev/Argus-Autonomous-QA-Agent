# Workbench sample app

Workbench is a small, Conduit-inspired RealWorld target used for local Argus development. It keeps the familiar feed, topic filtering, story publishing, and favorite interactions while using original copy and route names. This starter is an independent minimal implementation, not a vendored upstream RealWorld fork.

## Run

From the repository root:

```sh
docker compose up --build sample-app
```

Open <http://localhost:3100>. The app is self-contained and uses only Python's standard library. Its default in-memory stories are restored whenever the container restarts.

## Reset

Reset the app's in-memory stories and signed-in user before each run:

```sh
curl -i -X POST http://localhost:3100/__test/reset
```

The endpoint returns `204 No Content` and resets synchronously.

## Bug flags

Unset `BUGS` (or set it to an empty string) for the clean behavior. Enable one or more comma-separated flags in the environment:

```sh
BUGS=BUG-FN-01 docker compose up --build sample-app
BUGS=BUG-NW-03 docker compose up --build sample-app
BUGS=DEMO docker compose up --build sample-app
```

The registry is `BugRegistry` in `app.py`; `bug("BUG-FN-01")` and equivalent lookups return booleans. `BUG-FN-01` makes a favorite count increment twice. `BUG-NW-03` introduces a delayed duplicate count update. `DEMO` enables all demo defects and displays a banner. `BUGS` is read at process start, so recreate the service after changing it.

## Routes

- `GET /` serves the app.
- `GET /api/stories?topic=<topic>` lists stories.
- `GET /api/topics` lists available topics.
- `POST /api/auth/session` creates an in-memory demo session.
- `POST /api/stories` publishes a story.
- `POST /api/stories/<slug>/favorite` favorites a story.
- `POST /__test/reset` restores the initial state.
- `GET /api/health` is the container health check.
