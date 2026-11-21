# Rajudesktop application collection: repository guide

Source review: 21 November 2026. This is a source map, not a claim about live deployment health.

Independent Windows desktop applications share this repository. Always select the app before choosing dependencies, tests or downloads.

## Source map

| Path | Purpose |
| --- | --- |
| [`APP_INDEX.md`](../APP_INDEX.md) | App catalogue and canonical source locations |
| [`Z_BUILDER.md`](../Z_BUILDER.md) | Current Z Builder contract and labelled history |
| [`scene_desktop/`](../scene_desktop/) | Scene Desktop Studio MVP |
| [`tests/`](../tests/) | Application regressions |
| [`.github/workflows/`](../.github/workflows/) | App-specific Windows tests and packages |

## Development and validation

Choose an app in APP_INDEX.md, then use its own README and workflow. The root requirements.txt and launch.py belong to Scene Desktop Studio, not every app. Validate Windows packages on Windows and keep actual CapCut playback acceptance separate from synthetic draft tests.

## Build and storage policy

The target retention policy is 3 days for PR/test packages, 7 days for ordinary development candidates and sanitized failure diagnostics, and versioned GitHub Releases for supported downloads. The workflow's explicit retention-days is authoritative; this document alone does not change expiry. Release evidence consumed by another workflow needs its own retention exception.

Before retiring any artifact, identify its full source SHA and active consumers. Preserve active integration candidates and the current and previous verified release outside short-lived Actions storage. A candidate that needs longer testing must be copied to a named prerelease with checksums before expiry. No automatic artifact, branch, release or package deletion is introduced by this guide.

Heavy Windows/container packaging should use explicit release or manual triggers where source tests can run independently. Existing frozen-binary, media and compatibility tests remain release gates. Do not cancel an in-progress publication or deployment just to save CI minutes.

## Release record

For each release record: component/version, full source SHA, package SHA256 or container digest, relevant dependency/model versions, exact verification results, unresolved platform acceptance, and previous verified version/rollback procedure. Use sanitized screenshots from the actual app when available; no fabricated UI or unverified production claims.

## Maintenance checklist

- Keep README setup instructions and app/version mappings aligned with the source.
- Review dependency updates with the affected tests; do not enable blind automatic merges.
- Keep workflow token permissions scoped to the job that needs them.
- Inspect repository rules, environment protection and available security features before proposing account-setting changes.
- Keep historical research labelled and separate from the current source contract.
- Use the [contribution guide](../CONTRIBUTING.md) and issue/PR templates for review.
