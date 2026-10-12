# Releases

`main` holds tagged releases. The shared [branch and release policy](https://github.com/adidshaft/grok-gadgets/blob/main/CONTRIBUTING.md#branches-and-releases)
covers release and hotfix PRs.

## Publish a release

1. Run the repository checks and `uv build`.
2. Merge the release PR into `main`. Tag it, for example `v0.1.0-alpha.7`, and publish the
   GitHub release. The owner approves each step.
3. In **Actions → release packages → Run workflow**, choose `main` and enter the tag. The
   workflow checks that the tag matches the package version. It builds the wheel and the
   source archive and writes `SHA256SUMS` with plain file names. It checks that file in a
   fresh folder and attaches all three files to the release. It never replaces an asset.
4. To upload to PyPI, run it again with **Also upload to PyPI**. The upload uses trusted
   publishing: GitHub gives the job a short-lived identity, and no PyPI token is stored.
   The `pypi` environment waits for the owner's approval.

## Check a download

```sh
mkdir release-check
cd release-check
gh release download v0.1.0-alpha.7 --repo adidshaft/grok-gadgets-linux-sdk
shasum -a 256 -c SHA256SUMS
```

Releases made before this workflow may list `dist/` paths in `SHA256SUMS`
([hub #151](https://github.com/adidshaft/grok-gadgets/issues/151)).

## One-time PyPI setup (owner)

1. Sign in to [pypi.org](https://pypi.org) with two-factor authentication on.
2. Open **Your projects → Publishing → Add a new pending publisher → GitHub**. Enter
   PyPI project `grok-gadgets-linux-sdk`, owner `adidshaft`, repository `grok-gadgets-linux-sdk`, workflow
   `release.yml` and environment `pypi`.
3. In GitHub, open **Settings → Environments → New environment**, name it `pypi`. Add
   `adidshaft` as a required reviewer. Under deployment branches, allow only `main`.

The first approved upload creates the PyPI project. After that, the pending publisher
becomes a normal trusted publisher for `grok-gadgets-linux-sdk`.
