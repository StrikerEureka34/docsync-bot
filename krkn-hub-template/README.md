# krkn-hub Trigger

Copy `.github/workflows/trigger-docs-sync.yml` into the krkn-hub repo's `.github/workflows/`.

When a PR that changes a scenario's `env.sh` or `krknctl-input.json` is merged, it dispatches the website's doc-sync workflow for every changed scenario, so one source PR produces one docs PR. It authenticates with a short-lived GitHub App token, not a PAT.

## Change these for production

- the target owner and repo `StrikerEureka34` / `website_2` to `krkn-chaos` / `website`
