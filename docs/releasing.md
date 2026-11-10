# ibgedata release preparation

The repository, distribution, and import namespace are `ibgedata`.
The prepared first release is **0.1.0**. This migration builds on the merged
agent-acquisition fixes; it preserves their parser version (`ibge-json-2`),
query bounds, structured errors, raw artifacts, and no-runtime-dependency contract.

The unrelated `ibgepy` project on PyPI is not this client. Change source-install
URLs to `https://github.com/rteoo/ibgedata` and imports to `ibgedata`.
The new wheel does not install an `ibgepy` compatibility namespace.

## GitHub and PyPI

Rename `rteoo/ibgepy` to `rteoo/ibgedata`, preserving its repository ID, private
visibility, refs, and controls. The rollback is renaming the same repository
back to `ibgepy`. Existing checkout directories may keep their current names;
update origins to `https://github.com/rteoo/ibgedata.git`.

Register this pending Trusted Publisher in the intended PyPI account:

| Project | Owner | Repository | Workflow | Environment |
|---|---|---|---|---|
| `ibgedata` | `rteoo` | `ibgedata` | `publish.yml` | `pypi` |

Create and protect the GitHub `pypi` environment before any upload. The patch
does not configure account permissions or prove environment protection. Pending
publishers do not reserve package names. Public-visibility and release decisions
remain separate from the repository rename.

## Verification and release

```bash
python -m pytest
python -m build
python release.py --tag v0.1.0 --dry-run
```

The default test configuration excludes integration tests. Live checks remain
deliberate opt-in actions, not evidence supplied by the offline suite.
The CI package job imports the built wheel outside the source checkout and
verifies metadata/runtime versions and public exports.

The release helper requires clean `main` equal to freshly fetched `origin/main`,
a matching version, and passing tests/builds. Run it after review and merge.
Only a separately authorized final GitHub Release triggers PyPI publication;
normal pushes, bare tags, and prereleases do not publish. Do not replace or
delete immutable releases to perform this migration.
