# Architecture decision records

Short records of design choices that shape the project, so a later change
can see why things are the way they are.

- One file per decision: `NNNN-short-title.md` (e.g.
  `0001-use-ubuntu-24-container.md`), numbered in order, never renumbered.
- Sections: **Context** (the problem and constraints), **Decision** (what
  was chosen), **Consequences** (what follows, including the downsides).
- A superseded record stays in place with a line pointing to the record
  that replaces it.

Until a record exists for a topic, the current decisions live in the
topic docs, e.g. [localization.md](../localization.md) for the VIO gates,
GPS-default EKF2 and scoring, and [licensing.md](../licensing.md) for the
OpenVINS process boundary.
