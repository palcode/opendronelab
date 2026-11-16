# Public-launch flip checklist

Maintainer steps for opening [palcode/opendronelab](https://github.com/palcode/opendronelab). Agents must not change repository visibility or settings. Do not create a GitHub Release or tag as part of this flip. Do not loosen regression gates.

Run these in order on flip day.

## 1. Pre-flight

- [ ] From a clone of the new repository, run `scripts/check-preflip.sh`.
  It must report that a known-good commit (`bccb5a1…`) is present and
  that the pre-rewrite SHA `04d2c43` is not. The GitHub API may return
  HTTP 404 or 422 (“No commit found”) for the missing SHA. Authenticate
  with `gh` (or `GH_TOKEN`) for the API check while the repository is
  still private; the script also probes `origin` over git. An
  unauthenticated API 404 is inconclusive until visibility is public.
- [ ] Confirm the latest gitleaks scan of this repository’s history was
  clean (or that any finding was reviewed). The scan is read-only. Do
  not delete GitHub Actions workflow runs.

## 2. Visibility

- [ ] GitHub → Settings → General → Danger Zone → Change repository
  visibility → **Public**.

## 3. Social preview

- [ ] GitHub → Settings → General → Social preview → Upload
  `docs/media/social-preview.png` from this repository.

## 4. Private vulnerability reporting

- [ ] GitHub → Settings → Code security → Private vulnerability
  reporting → **Enable**.
- [ ] Confirm [SECURITY.md](https://github.com/palcode/opendronelab/blob/main/SECURITY.md) still points reporters at
  GitHub private advisories.

Tracked in issue #17.

## 5. Branch protection

- [ ] GitHub → Settings → Branches → Add rule (or ruleset) for `main`.
- [ ] At minimum: **do not allow force pushes**, do not allow
  deletions.
- [ ] Choose the rest of the policy yourself (required reviewers,
  required CI status checks, signed commits). This document does not
  invent those rules.

Tracked in issue #17.

## 6. CLA signatures branch

- [x] **Done 2026-11-17 (IST).** Pallab approved moving signatures to a
  dedicated `cla-signatures` branch (#15). `.github/workflows/cla.yml`
  now sets `branch: cla-signatures`. Permissions stay on the job. The
  workflow does not check out a pull-request head.
- [x] Orphan branch `cla-signatures` starts at
  `b2c16c4d23d49bcbdc44065f25c0be081a0e03cf` with
  `signatures/version1/cla.json` (`signedContributors` is empty). That
  file was never present on `main`, so there was nothing to `git rm`.
- [ ] Leave `cla-signatures` **unprotected** so `GITHUB_TOKEN` can
  append signatures. Add a `repo`-scoped PAT as
  `PERSONAL_ACCESS_TOKEN` only if that branch is later protected.

## 7. Discussions

- [ ] GitHub → Settings → General → Features → **Discussions**.
- [ ] Keep or create the categories you want for public use
  (recommended: Announcements, Q&A, Show and tell, Ideas).
- [ ] Optional: replace the “Discussions pending” badge in the README
  with a live badge once Discussions is on.

## 8. After the flip (optional, same day)

- [x] Re-run `scripts/check-preflip.sh` unauthenticated now that the
  repository is public. Recorded in [Post-public verification](#post-public-verification-2026-11-17).
  (The pre-rewrite SHA returned HTTP 422, which the script treats as
  “not served”, same as 404.)
- [ ] Pin a short “we are public / build in public” announcement in
  Discussions if you want one. A draft is in
  [docs/community/welcome-discussion.md](community/welcome-discussion.md).

## Deferred (not part of the flip)

- **GHCR images.** The dispatch-only workflow (`.github/workflows/ghcr.yml`)
  is in the tree and has not been run. Publishing `opendronelab-dev` is
  still a maintainer decision (issue #13). Review
  [NVIDIA_REDISTRIBUTION.md](NVIDIA_REDISTRIBUTION.md) before a `dev`
  publish; a CPU/base image (`ODL_WITH_NVIDIA=0`) is available.
- **v0.1.0 GitHub Release or tag.** Release notes and a trimmed sample
  bag are prepared; do not tag or publish until the maintainer agrees.
- **Docs site / GitHub Pages.** A Zensical draft lives on the
  `docs-site` branch. Do not enable Pages until the maintainer agrees.
- **Discussions, About text, topics, and Website.** Drafts and
  suggested settings are in [docs/community/](community/).

## Post-public verification (2026-11-17)

Recorded after [palcode/opendronelab](https://github.com/palcode/opendronelab)
was already public. Times are Asia/Calcutta (IST, UTC+5:30). This section
is a results note, not a settings change.

### `scripts/check-preflip.sh`

Re-run at **2026-11-17 00:21 IST (Asia/Calcutta)** (and again after the
script was taught to probe the public API). Exit code 0.

- `origin` served known-good `bccb5a1d651a7783ce6a8c624754b38e43c1a22c`.
- `origin` refused pre-rewrite `04d2c4351d2a8d74930c4e751924542926ca0789`.
- Local note only: `04d2c43` exists as an unreachable object in this
  clone (for example a reflog entry) and is not an ancestor of
  `origin/main`.
- GitHub REST, unauthenticated, public repository:
  - `GET /repos/palcode/opendronelab/commits/bccb5a1d651a7783ce6a8c624754b38e43c1a22c` → HTTP 200
  - `GET /repos/palcode/opendronelab/commits/04d2c43` → HTTP 422 (`No commit found for SHA: 04d2c43`)

### gitleaks

`gitleaks` v8.28.0 (`detect --source=... --log-opts=--all`) is run on
the full history before each push to `origin`. The scans recorded
around this verification reported **no leaks found**. The commit count
in the scanner output grows with each new commit; a clean result is
what matters.
