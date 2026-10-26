# Contributing to Garmates

Thanks for helping. Garmates is a small project, so every bug report, idea and pull request
gets read.

## Ways to help

- **Report a bug.** Use the [bug report form](https://github.com/Jamesemf/garmates/issues/new?template=bug_report.yml).
- **Garmin data looks wrong?** Garmin's Personal API is new and its documentation doesn't always
  match what it sends. The [data issue form](https://github.com/Jamesemf/garmates/issues/new?template=garmin_data.yml) asks for
  the output of `garmates verify`, which is the fastest way to pin these down.
- **Suggest a feature.** Open a [feature request](https://github.com/Jamesemf/garmates/issues/new?template=feature_request.yml),
  or start a thread in Discussions if it's still a rough idea.
- **Send a pull request.** Issues labelled `good first issue` are a good start, and so is the
  roadmap in the [README](README.md#roadmap). For anything large, open an issue first so we can
  agree on the approach.
- **Improve the docs.** If a step tripped you up, it'll trip up the next person too.

## Development setup

You need Python 3.12+ and Node 22.

**With conda** (this is what `start.cmd`/`start.sh` use):

```bash
conda env create -f environment.yml
conda activate garmates
```

**With a virtualenv:**

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e "backend[dev]"
```

Then install the frontend dependencies:

```bash
cd frontend && npm ci
```

### Running it

Run the API with auto-reload in one terminal:

```bash
garmates serve --reload
```

And the Vite dev server in another:

```bash
cd frontend && npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to FastAPI on port 8000.

You don't need a Garmin key to work on most things. Create an account, then press **Load demo
profiles** on the People & keys page (or run `garmates demo`). You get two synthetic people with
eight months of data in Garmin's own JSON shapes, GPS tracks included.

Use a separate data directory if you want to keep your real data out of the way:

```bash
garmates --data-dir ./dev-data serve --reload
```

### Checks

Run these before you open a pull request. CI runs the same ones.

```bash
cd backend && ruff check src tests && python -m pytest
```

```bash
cd frontend && npm run lint && npm run build
```

`npm run build` also type-checks.

## How the code is organised

[docs/architecture.md](docs/architecture.md) explains the sync engine, the data model and the
privacy model. [docs/extending.md](docs/extending.md) has step-by-step recipes for the usual
changes: a new metric, a new Garmin field or dataset, a new chart or page, a new insight.

## Style

- Match the code around you: naming, comment density and idiom. Comments explain *why*, not
  *what*.
- Python: ruff with a line length of 100 (`backend/pyproject.toml`). Type hints on public
  functions.
- TypeScript: oxlint and strict `tsc`. Use the shared chart kit in `components/charts.tsx` and the
  palette in `lib/theme.tsx` rather than one-off colours.
- UI text uses UK English ("colour", "normalised") and plain words. Insights describe
  associations in a person's own data, never causes or medical advice.
- Parsers must tolerate missing fields and Garmin's sentinel values. Raw payloads are stored
  verbatim, so a parser fix plus `garmates reparse` repairs existing data without calling Garmin
  again.

## Real Garmin data: keep it private

- Never commit anything from `data/`. It holds health data, encrypted keys and the key that
  decrypts them. It is git-ignored; keep it that way.
- When a real payload helps (a test fixture, an issue), cut it down to the fields that matter and
  replace names, IDs, locations and timestamps that could identify someone.
- Never paste a Personal API key, bearer token or `master.key` anywhere.

## Pull requests

- Keep a PR to one change. Refactors go in their own PR.
- Add or update tests for behaviour changes, especially parsers and sync logic.
- Update docs and `CHANGELOG.md` (under **Unreleased**) when users would notice the change.
- Include a screenshot for UI changes. Demo data is fine for this.

## Releasing (maintainers)

1. Bump the version in `backend/pyproject.toml` and `backend/src/garmates/__init__.py`.
2. Move the **Unreleased** notes in `CHANGELOG.md` under the new version and date.
3. Merge to `main`, then tag and push the tag:

   ```bash
   git tag v0.2.0 && git push origin v0.2.0
   ```

The release workflow checks that the tag matches the package version and then:

- builds `linux/amd64` and `linux/arm64` images and pushes them to
  `ghcr.io/jamesemf/garmates` as `0.2.0`, `0.2` and `latest`;
- creates a GitHub Release from that version's changelog section.

## Code of conduct

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
