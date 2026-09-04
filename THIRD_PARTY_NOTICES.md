# Third-party notices and provenance

This repository is distributed under GPL-3.0-only; see [LICENSE](LICENSE).
This notice is a provenance record, not legal advice.

## `references/pvztoolkit`

[`pvztoolkit`](https://github.com/lmintlcx/pvztoolkit) is included as a Git
submodule solely as a reverse-engineering research reference. It remains a
separate upstream work under GPL-3.0 and retains its own copyright and license
files in the submodule. It is not the runtime engine for this project.

The Python reader, controller, environment, and runtime layers in this
repository were independently implemented around documented observations and
testable behavior. A source/provenance audit for v0.1.0 found no copied
`pvztoolkit` implementation files in the shipped Python packages. The
submodule's GPL-3.0 provenance and inclusion nevertheless make GPL-3.0-only
the appropriate conservative license for this repository.

## Python dependencies

- [NumPy](https://numpy.org/) — BSD-3-Clause.
- [psutil](https://github.com/giampaolo/psutil) — BSD-3-Clause.
- [pymem](https://github.com/srounet/Pymem) — MIT.

These packages are installed from their respective distributions and are not
vendored here. Their complete license texts remain available from their
upstream projects and installed package metadata.

## Game assets and trademarks

Plants vs. Zombies, its executable, artwork, assets, and trademarks are not
included, licensed, or redistributed by this repository. Users must supply a
lawfully installed, supported Windows game client for any live operation.
