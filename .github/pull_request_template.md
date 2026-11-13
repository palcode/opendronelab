## Summary

<!-- What does this change, and why? -->

## CLA

I have read `CLA.md` and I will sign the Contributor License Agreement
when the CLA assistant asks on this pull request. I will not include
secrets, credentials, or personal host paths in this pull request.

## Checklist

- [ ] `SCENARIOS=pytest ./scripts/run-regression.sh` (or the CI unit tests) pass locally
- [ ] Scenario fingerprints are unchanged, or the change is explained (worlds, OpenVINS overlays, and the prop mask were touched only if intended)
- [ ] Regression gates in `config/regression_thresholds.yaml` were not loosened
- [ ] No host `/home/…` paths, machine hostnames, or secrets were added
- [ ] Docs / comments updated when behaviour changed
