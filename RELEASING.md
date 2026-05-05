# Releasing a new version

The full process is one `VERSION` bump and two `git push` commands. GitHub Actions handles the rest.

## TL;DR

```bash
# 1. Bump VERSION (patch bump shown — adjust per change, see "Versioning" below)
echo "1.2.2" > VERSION

# 2. Commit your changes (including the VERSION bump)
git add -A
git commit -m "v1.2.2: <one-line summary of what changed>"

# 3. Push main and a matching tag — the tag is what triggers the build
git push origin main
git tag v1.2.2
git push origin v1.2.2
```

That's it. ~6 minutes later the new DMG is live at:
`https://github.com/ktykeson/restaurant-research/releases/latest`

## Versioning

Use semantic versioning: `MAJOR.MINOR.PATCH`.

| Change | Bump | Example |
|---|---|---|
| Bug fix, copy edit, tiny tweak | PATCH | `1.2.1` → `1.2.2` |
| New feature, new screen, new field | MINOR | `1.2.7` → `1.3.0` |
| Breaking change to the cache schema or CSV export header | MAJOR | `1.x.y` → `2.0.0` |

The git tag and the `VERSION` file **must match exactly** (without the `v` prefix). The CI workflow has a guard that fails the build if they disagree, so if you forget to bump `VERSION`, the release won't ship — you'll just see a red X on Actions.

## What happens automatically when you push the tag

1. GitHub Actions sees the `v*.*.*` tag and starts the macOS-14 runner.
2. Runs `./build.sh`: PyInstaller produces the `.app`, signs it ad-hoc inside `/tmp` (so `com.apple.provenance` doesn't invalidate the signature), then `create-dmg` packages it.
3. `softprops/action-gh-release@v2` creates a Release named after the tag and attaches `RestaurantResearch.dmg`.
4. Every running client picks it up on its next launch (or within 90s if the app is open).

Watch the run live at: `https://github.com/ktykeson/restaurant-research/actions`

## What the client sees

- **App is closed when you ship**: next time they open it, the new version is downloaded silently in the background. If they keep the app open for ~30 seconds, a blue banner appears at the top: **"Version X.Y.Z is ready to install — Update now / Later"**. One click to apply, ~2-second window flash, app reopens on the new version.
- **App is open when you ship**: same flow — within 90 seconds of the build finishing, the banner appears.
- **Client is on a pre-1.2.0 version (i.e. v1.0.0 or v1.1.0)**: those builds don't have the popup yet, so they auto-update silently on next launch. The popup kicks in for the FIRST update after they're on v1.2.0+.

## Building a DMG locally (for manual delivery, no CI)

If you need to send a client a DMG before the next CI build finishes — or if Actions is broken — run:

```bash
source .venv/bin/activate
./build.sh
```

Output: `dist/RestaurantResearch.dmg`. Takes ~3 minutes. Verify it before sending:

```bash
MP=$(mktemp -d)
hdiutil attach -nobrowse -noautoopen -quiet -mountpoint "$MP" dist/RestaurantResearch.dmg
codesign --verify --deep --strict "$MP/RestaurantResearch.app" && echo "OK"
hdiutil detach -quiet "$MP" && rm -rf "$MP"
```

`OK` means the bundle inside the DMG is properly signed. (Don't `codesign --verify` against `dist/RestaurantResearch.app` directly — macOS reattaches `com.apple.provenance` after the build copy, which makes it look unsigned even though the DMG-internal copy is fine.)

## Common issues

**Build fails with "VERSION mismatch":** You forgot to bump `VERSION` before tagging. Fix:

```bash
git tag -d v1.2.2                      # delete local tag
git push origin :refs/tags/v1.2.2      # delete remote tag
echo "1.2.2" > VERSION                 # bump
git commit -am "bump VERSION to 1.2.2"
git push origin main
git tag v1.2.2
git push origin v1.2.2                 # re-trigger the build
```

**Build fails on PyInstaller "base_library.zip":** Re-run `./build.sh` once more. PyInstaller occasionally trips over `--clean` semantics on the first attempt.

**Local DMG signature won't verify:** That's expected on `dist/`. Verify against the bundle *inside* the mounted DMG (see "Building a DMG locally" above). Only that copy ships.

**Client opens the app and nothing happens:** They're probably offline at launch, or running from somewhere other than `/Applications`. The launcher only auto-applies staged updates when running from `/Applications` (intentional — protects test runs from being hijacked).

## Rolling back a bad release

GitHub doesn't let you reuse a tag — once `v1.2.5` is published, that version number is permanently associated with that build, even if you delete it. If you ship a bad release:

1. **Bump VERSION higher** — e.g. `1.2.5` → `1.2.6`.
2. **Revert the bad commit** (or commit a fix) on `main`.
3. Tag and push as `v1.2.6`.

Clients on the broken `v1.2.5` will auto-update to `v1.2.6` the same way they would for any other release.

If you must take down `v1.2.5` so it doesn't reach more clients:
```bash
gh release delete v1.2.5 --cleanup-tag --yes
```
But: clients who already downloaded the staged update for v1.2.5 will still apply it on next launch. The staged file lives in `~/Library/Application Support/RestaurantResearch/pending_update/`. Tell them to delete that directory if it matters.

## File map (for orientation)

- `VERSION` — single line with the version number, no `v` prefix
- `.github/workflows/release.yml` — CI workflow that triggers on `v*.*.*` tags
- `build.sh` — local + CI build script (PyInstaller → codesign → DMG)
- `RestaurantResearch.spec` — PyInstaller spec, references `VERSION` for `Info.plist`
- `updater.py` — client-side updater (`GITHUB_OWNER` / `GITHUB_REPO` constants are hardcoded here)
- `launcher.py` — applies staged updates on launch before starting the server
