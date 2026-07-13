# Website Workflows

Copy these into the website repo's `.github/workflows/`. They are the runtime half of the docs-sync bot ([#320](https://github.com/krkn-chaos/website/issues/320)).

## Files

- `doc-sync.md` and `doc-sync.lock.yml`: the gh-aw agentic workflow. It runs the bot on a `/fix` comment or a dispatch from krkn-hub, generates the parameter data files, and opens a draft PR. `doc-sync.md` is the source, `doc-sync.lock.yml` is compiled from it by `gh aw compile` and is the file that actually runs.
- `hugo-build.yml`: a render gate that fails a PR if any generated page or shortcode does not build.

## Change these for production

The committed versions are configured for the test fork. For the real deployment:

- `roles: all` to `[admin, maintainer, write]`
- target repo `StrikerEureka34/website_2` to `krkn-chaos/website`
- the krkn-hub clone URL and the bot install URL to the krkn-chaos sources
- recompile with `gh aw compile` after editing `doc-sync.md`
