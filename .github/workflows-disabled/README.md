# Disabled GitHub Actions

Workflows in this directory are **not** run by GitHub. Only files under
`.github/workflows/` are active.

`cla.yml` is a prepared CLA-assistant workflow, pinned to a release SHA.
Do not move it into `.github/workflows/` or enable it until Pallab
Sarkar has approved a final CLA text. `CLA.md` is the official Harmony
HA-CLA-I v1.0 (outbound Option Five). It is not yet in force and still
needs lawyer review, plus fill-in of jurisdiction and any Media
licenses, before it is activated.

The upstream action repository (`contributor-assistant/github-action`)
is archived. Existing release `v2.6.1` remains usable, pinned by
commit SHA rather than a floating tag.
