# Release Process

Releases are fully automated via GitHub Actions.
Updating the changelog and pushing a version tag are the only manual steps required.

## Versioning

This project uses [Semantic Versioning](https://semver.org/).
Versions are derived automatically from git tags via `hatch-vcs` — there is no version field to update manually.

Tag format: `vX.Y.Z` (e.g. `v1.2.0`)

## Releasing a new version

1. **Update the Changelog:** Open `CHANGELOG.md` and move all items from `[Unreleased]` into a new section
   for the target version (e.g., `## [1.2.0] - YYYY-MM-DD`). Add a new empty `## [Unreleased]` block at the top.
2. **Commit the changes:**

    ```bash
    git commit -am "chore: update changelog for vX.Y.Z"
    git push origin main
    ```

3. **Tag and push:**

    ```bash
    git tag vX.Y.Z
    git push origin vX.Y.Z
    ```

That's it. The CI pipeline takes over from here.

## What CI does

Pushing a tag triggers the release workflow (`.github/workflows/release.yml`), which runs the following in order:

`git tag` → CI Pipeline → Build Artifacts → Publish to All Channels → create GitHub Release

### PyPI

Builds a wheel and sdist via `uv build`, publishes via `uv publish` using OIDC trusted publishing (no token required).

### GitHub Releases

Extracts the newly published release notes directly from `CHANGELOG.md`, appends download and installation instructions,
creates a formal GitHub Release, and attaches the pre-built `sdist` and `wheel` artifacts.

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

### GitHub Release Creation Failed

Verify that the tag exactly matches a section header in `CHANGELOG.md` (e.g., tag `v1.2.0` matches `## [1.2.0]`).
