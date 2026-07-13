# Website Workflows

Copy these into the website repo's `.github/workflows/`. They are the runtime half of the docs-sync bot ([#320](https://github.com/krkn-chaos/website/issues/320)).

## Files

- `doc-sync.md`: the gh-aw agentic workflow source. It runs the bot on a `/fix` comment or a dispatch from krkn-hub, generates the parameter data files, and opens a draft PR. Run `gh aw compile` to produce `doc-sync.lock.yml`, the file GitHub Actions actually runs. That lock is generated, so it is not committed here.
- `hugo-build.yml`: a render gate that fails a PR if any generated page or shortcode does not build.

## Change these for production

The committed versions are configured for the test fork. For the real deployment:

- `roles: all` to `[admin, maintainer, write]`
- target repo `StrikerEureka34/website_2` to `krkn-chaos/website`
- the krkn-hub clone URL and the bot install URL to the krkn-chaos sources
- recompile with `gh aw compile` after editing `doc-sync.md`
