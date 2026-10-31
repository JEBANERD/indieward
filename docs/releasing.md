# Releasing IndieWard

Releases come from `.github/workflows/release.yml`. Pushing a tag `vX.Y.Z` runs the tests, then builds the sdist and wheel. It attests their provenance with Sigstore and writes a CycloneDX SBOM. Then it creates the GitHub release. It publishes to PyPI only after the one-time setup below.

## Each release

1. In `CHANGELOG.md`, give the version's heading a date, e.g. `## [0.1.0] - 2026-11-02`. For a later version, add a new section, and set the same version in `pyproject.toml`.
2. Merge that to `main`. The pull request runs the release workflow as a dry run (build, test and SBOM; nothing is published).
3. Tag the merge commit and push the tag:

   ```bash
   git tag v0.1.0 origin/main
   ```

   ```bash
   git push origin v0.1.0
   ```

The workflow stops before building anything if the tag doesn't match the `pyproject.toml` version, or if the changelog has no section for it.

## One-time PyPI setup (Jasper)

Until this is done, tagged releases still go to GitHub, and the PyPI job is skipped.

1. On PyPI, add a **pending trusted publisher** for a new project (Account settings → Publishing): project `indieward`, owner `JEBANERD`, repository `indieward`, workflow `release.yml`, environment `pypi`. Steps: https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
2. On GitHub, create the environment `pypi` (Settings → Environments). Adding yourself as a required reviewer means every PyPI upload waits for your click.
3. Set the repository variable `PYPI_PUBLISH` to `true` (Settings → Secrets and variables → Actions → Variables).

No API token is stored anywhere: PyPI trusts this workflow directly.

## Checking a download came from this repo

Each wheel, sdist and SBOM on a release has a signed build-provenance attestation. With the GitHub CLI:

```bash
gh attestation verify indieward-0.1.0-py3-none-any.whl --repo JEBANERD/indieward
```

The SBOM (`indieward-vX.Y.Z.cdx.json`) lists every package a clean `pip install indieward` pulled in, with versions and licences.
