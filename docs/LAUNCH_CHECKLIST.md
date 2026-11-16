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
- [ ] Confirm [SECURITY.md](../SECURITY.md) still points reporters at
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

- [ ] Re-run `scripts/check-preflip.sh` unauthenticated and confirm
  `04d2c43` is still 404 now that the repository is public.
- [ ] Pin a short “we are public / build in public” announcement in
  Discussions if you want one.

## Deferred (not part of the flip)

- **GHCR images.** Publishing `opendronelab-dev` is a post-launch item
  (issue #13). Review NVIDIA CUDA/cuDNN wheel redistribution before the
  first publish.
- **v0.1.0 sample bag / release assets**, and a GitHub Release or tag.
- **Excalidraw / SVG architecture diagram** (the README uses Mermaid
  until then).
- **Docs site / GitHub Pages.**
