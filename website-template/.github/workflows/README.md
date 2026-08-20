# Website Workflows

Copy these into the website repo's `.github/workflows/`. They are the runtime half of the docs-sync bot ([#320](https://github.com/krkn-chaos/website/issues/320)).

## Files

- `doc-sync.md`: the gh-aw agentic workflow source. It runs the bot on a `/fix` comment, a `/resync` on a bot PR, or a dispatch from a source repo, generates the parameter data files, and opens a draft PR. Run `gh aw compile` to produce `doc-sync.lock.yml`, the file GitHub Actions actually runs. That lock is generated, so it is not committed here.
- `drift-report.yml`: a weekly report-only scan. It opens or updates one rolling `docs-drift` issue and opens no PRs. A plain workflow, not gh-aw: the report is derived from the sources with no judgement involved. Fixing is done by commenting the `/fix` the issue names, which drives `doc-sync.md`.
- `hugo-build.yml`: a render gate that fails a PR if any generated page or shortcode does not build.

Both workflows clone all three sources. krkn-hub and krkn go together because a per-scenario table can only be built once the bot knows which params are global; krkn-operator supplies the CRDs behind the api-reference pages.

## Targets

`doc-sync.md` routes one target per iteration:

| Target | Runs |
| --- | --- |
| a scenario id, e.g. `node-scenarios` | `bot.doc_bot` |
| `globals` | `bot.globals` |
| `operator` | `bot.operator`, all CRDs at once |

`/resync` derives them from the PR's changed files with `bot.targets`, not a grep, because a CRD plural is a group under `data/params/` but only `bot.operator` regenerates it.

## Change these for production

The source URLs, the bot install URL, the target repo and `roles` already point at production. What is left:

- set one secret, `DOC_SYNC_BOT_LLM_API_KEY`, for the endpoint named on the generation step. It ships pointed at NVIDIA NIM, with GitHub Copilot commented beside it. Any OpenAI-compatible `/v1` endpoint works
- recompile with `gh aw compile` after editing `doc-sync.md`. Only the workflow needs it: the bot installs from `@main` at run time, so a Python change ships without a recompile, at the cost of tracking that branch rather than a pinned commit

## The model key

`DOC_SYNC_BOT_LLM_API_KEY` is the only model credential, and **its power follows the endpoint**:

| `DOC_SYNC_BOT_LLM_BASE_URL` | What the key has to be | If it leaked |
| --- | --- | --- |
| an inference provider, the shipped default | an inference key | that provider's quota. No GitHub scope |
| `https://api.githubcopilot.com` | a GitHub token with Copilot access | **a GitHub credential** |

**Rotate `DOC_SYNC_BOT_LLM_API_KEY` when you change the endpoint.** One secret name holds both kinds of credential, so leaving the old value in place points a GitHub token at an inference provider, or the reverse.

`DOC_SYNC_BOT_LLM_BASE_URL` must be `https`. The key travels on it as a bearer header, and `describe.py` refuses a plaintext base rather than sending it. It also refuses to follow a redirect: urllib keeps the bearer header across a hop and allows `https` -> `http`, so an endpoint could otherwise hand the key to any host in the clear.

### Checking the key works

A wrong key fails exactly like a missing one: the run stays green and the cells come out blank. **"The run passed" is not the check.** Look at the gap table in the commit message:

| | |
| --- | --- |
| Working | rows sourced `llm` |
| Dead, or unset | `model unavailable: endpoint returned HTTP 401: ...`, or `no DOC_SYNC_BOT_LLM_API_KEY set` |
| Unreachable, or redirecting | `model unavailable: endpoint unreachable (URLError)`, or an `HTTP 30x` the bot refused to follow |

Check it after setting the secret and after any provider change. The krkn-operator target is unaffected either way, because it never calls the model.

Background, including which NVIDIA models clear gh-aw's api-proxy and why: [docsync-bot#24](https://github.com/krkn-chaos/docsync-bot/issues/24).

Both workflows need the GitHub App: `DOC_SYNC_BOT_APP_ID` as a repository variable and `DOC_SYNC_BOT_APP_PRIVATE_KEY` as a secret. `drift-report.yml` uses it so the rolling issue has a stable author instead of `github-actions[bot]`.
