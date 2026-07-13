# Param-Table Template

A Hugo shortcode and data-file schema that renders scenario parameter tables on the [krkn-chaos website](https://github.com/krkn-chaos/website) from data files. It lets the docs-sync bot ([#320](https://github.com/krkn-chaos/website/issues/320)) keep tables current by writing data only, never editing human-written markdown.

## What is here

```
website-template/
  layouts/shortcodes/param-table.html            # the shortcode
  examples/data/params/<scenario>/<source>.yaml  # example data files
```

## How it works

A tab file renders its table with one call:

```
{{< param-table scenario="node-scenarios" source="krkn-hub" >}}
```

- reads `data/params/<scenario>/<source>.yaml`
- Parameter and Description always show; Type, Possible Values, Default, and Required show only when a row uses them
- missing or empty data renders nothing and emits a Hugo `WARN`, so the build stays green
- inherits the site's table styling, no CSS changes

Data file shape:

```yaml
source_repo: krkn-hub
source_ref: 9f3c1a2
params:
  - name: ACTION                        # required
    description: Action to run.         # required
    type: enum                          # optional
    default: node_stop_start_scenario   # optional
    possible_values: [a, b]             # optional
    required: false                     # optional
```

`name`, `type`, and `default` come deterministically from the source; only `description` may come from the LLM.

## Installing into the website

1. Copy `layouts/shortcodes/param-table.html` into the website's `layouts/shortcodes/`.
2. Add the `data/params/<scenario>/<source>.yaml` files.
3. Replace each markdown table in `_tab-<source>.md` with the shortcode call. Surrounding prose stays untouched.

## Tests

`tests/` holds a Hugo build harness with 14 edge-case tests (column auto-hide, numeric-zero default, missing and empty data, markdown descriptions, and the shipped example files). Run with `pytest`.

The bot's own unit tests (added with the bot package) live in the same `tests/` folder, they coexist.
