# Release Process

Releases are fully automated via GitHub Actions. Pushing a version tag is the only manual step required.

## Versioning

This project uses [Semantic Versioning](https://semver.org/).
Versions are derived automatically from git tags via `hatch-vcs` — there is no version field to update manually.

Tag format: `vX.Y.Z` (e.g. `v1.2.0`)

## Releasing a new version

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

That's it. The CI pipeline takes over from here.

## What CI does

Pushing a tag triggers the release workflow (`.github/workflows/release.yml`), which runs the following in order:

`git tag` → CI Pipeline → Build Artifacts → Publish to All Channels

### PyPI

Builds a wheel and sdist via `uv build`, publishes via `uv publish` using OIDC trusted publishing (no token required).

## Required secrets

| Secret          | Used for     | Where to configure              |
|-----------------|--------------|---------------------------------|
| *(none — OIDC)* | PyPI publish | PyPI trusted publisher settings |

## Verifying a release

After the workflow completes, confirm the new version is available on each channel:

### PyPI

```bash
pipx install mr-manager==X.Y.Z
```

## Troubleshooting

### PyPI Publish Failed

Check the Actions log for OIDC errors. Confirm the trusted publisher is configured correctly on pypi.org
(owner, repo, workflow filename, and environment name must all match exactly).
