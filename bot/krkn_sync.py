"""Krkn source: link integrity and config-block sync for the Krkn tab files.

The Krkn tab (_tab-krkn.md) is human-written prose, unlike the krkn-hub / krknctl
tabs which are generated tables. So this module never rewrites free prose. It does
three deterministic, report-only-or-draft-PR things:

  1. Link check   - find dead github.com/krkn-chaos links.
  2. Link fix     - a moved file with one clear new path -> a corrected-link edit.
  3. Config sync  - an "Example scenario file: [link]" anchor whose embedded YAML
                    block differs from its upstream source. Splits this into a wrong
                    anchor (the block names a scenario the linked file never mentions)
                    and real drift. Only auto-replaces a block that carries a
                    `<!-- krkn-src: url -->` provenance marker (proof it is a verbatim
                    mirror), so a hand-customized or mismatched block is never clobbered.

All network I/O (link resolver, repo tree, upstream fetcher) is injected, so the
whole module is unit-testable offline. The CLI wires in stdlib defaults.

Nothing here touches data/params or the emitter, so it shares no code path or
output file with the krkn-hub / krknctl sources.

TODO: no _tab-krkn.md carries a `krkn-src` marker yet, so capability 3 only
reports drift today. The one-time anchor-marking cleanup turns on the safe
auto-replace path, one tab at a time.
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

_IN_SCOPE = ("github.com/krkn-chaos/",)
_URL_RE = re.compile(r"https?://[^\s<>()\[\]]+")
_MDLINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
# github.com/krkn-chaos/<repo>/blob/<ref>/<path>
_BLOB_RE = re.compile(r"github\.com/krkn-chaos/([^/]+)/blob/([^/]+)/(.+)")
_ANCHOR_RE = re.compile(
    r"Example scenario file:\s*\[[^\]]*\]\((https?://[^)\s]+)\)", re.IGNORECASE)
_FENCE_RE = re.compile(r"```ya?ml\n(.*?)\n```", re.DOTALL)
_MARKER_RE = re.compile(r"<!--\s*krkn-src:\s*(\S+)\s*-->")


# --- link check -----------------------------------------------------------

def find_links(text):
    """Sorted, de-duped in-scope URLs in a markdown string."""
    urls = set()
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:")
        if any(host in url for host in _IN_SCOPE):
            urls.add(url)
    return sorted(urls)


def check_text(text, resolver):
    """[(url, status), ...] for in-scope links that do not resolve."""
    dead = []
    for url in find_links(text):
        status = resolver(url)
        if status == 0 or status >= 400:
            dead.append((url, status))
    return dead


def link_texts(text):
    """url -> display text for in-scope markdown links, used to confirm a fix."""
    out = {}
    for m in _MDLINK_RE.finditer(text):
        url = m.group(2).rstrip(".,;:")
        if any(host in url for host in _IN_SCOPE):
            out.setdefault(url, m.group(1))
    return out


# --- link fix -------------------------------------------------------------

def _blob_parts(url):
    m = _BLOB_RE.search(url)
    return m.groups() if m else None  # (repo, ref, path) or None


def _blob_url(repo, ref, path):
    return f"https://github.com/krkn-chaos/{repo}/blob/{ref}/{path}"


def _kind(path):
    """File kind for retarget matching. .yml and .yaml count as the same kind."""
    base = path.rsplit("/", 1)[-1]
    ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
    return "yaml" if ext in ("yml", "yaml") else ext


def fix_moved_link(url, tree, link_text=None):
    """A dead blob link -> its corrected URL, or None when the fix is not
    unambiguous. `tree(repo, ref)` returns every blob path in the repo.

    Rule: if the linked folder still exists and now holds exactly one file of the
    same kind (a rename in place), retarget to it. Deterministic, one candidate,
    no guessing. When the link text names a specific file, it must match the
    survivor, else we report rather than retarget to the wrong file."""
    parts = _blob_parts(url)
    if not parts:
        return None
    repo, ref, path = parts
    paths = tree(repo, ref)
    if path in paths:
        return None  # not actually moved
    dirpath = path.rpartition("/")[0]
    siblings = [p for p in paths
                if p.rpartition("/")[0] == dirpath and _kind(p) == _kind(path)]
    if len(siblings) != 1:
        return None  # folder gone, or several candidates: report, do not guess
    survivor = siblings[0]
    label = (link_text or "").strip()
    names_a_file = "." in label and " " not in label
    if names_a_file and label != survivor.rsplit("/", 1)[-1]:
        return None  # label points at a different specific file: report
    return _blob_url(repo, ref, survivor)


# --- config-block sync ----------------------------------------------------

def find_anchor(text):
    """The (url, block, marker_url) of the first "Example scenario file" anchor,
    or None. `marker_url` is the krkn-src provenance URL if the block carries one,
    else None. `block` is the YAML fence that follows the anchor line."""
    a = _ANCHOR_RE.search(text)
    if not a:
        return None
    f = _FENCE_RE.search(text, a.end())
    if not f:
        return None
    marker = _MARKER_RE.search(text[a.end():f.start()])
    return a.group(1), f.group(1), (marker.group(1) if marker else None)


def _norm(block):
    """Whitespace-tolerant form for verbatim comparison: strip trailing spaces
    per line, drop blank leading/trailing lines."""
    lines = [ln.rstrip() for ln in block.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


# Keys that structure a scenario file but are not the scenario name itself.
_STRUCTURAL = {"scenarios", "kraken", "parameters", "config", "input_list", "spec"}


def _block_ids(block):
    """Scenario identifiers a doc block claims to document: the `scenario:` plugin
    id and any top-level scenario key. Used to tell a wrong anchor (none of these
    appear in the linked file) from real drift (they do, but the content moved)."""
    ids = set(re.findall(r"scenario:\s*['\"]?([a-z][a-z0-9_-]{3,})", block))
    for m in re.finditer(r"^([a-z][a-z0-9_]{3,}):\s*$", block, re.MULTILINE):
        if m.group(1) not in _STRUCTURAL:
            ids.add(m.group(1))
    return ids


def block_drift(text, fetcher):
    """None if there is no anchor or the block matches upstream. Otherwise a dict
    describing the drift, whether the anchor points at the wrong file, and whether
    it is safe to auto-replace."""
    anchor = find_anchor(text)
    if not anchor:
        return None
    url, block, marker_url = anchor
    parts = _blob_parts(url)
    if not parts:
        return None
    upstream = fetcher(*parts)
    if upstream is None or _norm(block) == _norm(upstream):
        return None  # unreachable, or already in sync
    # Wrong source: the block names a scenario that the linked file never mentions,
    # so this is a bad anchor, not drift. Never auto-replace against the wrong file.
    ids = _block_ids(block)
    mismatch = bool(ids) and not any(i in upstream for i in ids)
    # Auto-replace only a block whose marker names this same upstream file: that
    # marker is the proof the block is a verbatim mirror, not a hand-edited copy.
    # TODO: no tab carries this marker yet, so `safe` is always False until the
    # anchor-marking cleanup lands. Until then this path reports, never rewrites.
    safe = (marker_url == url) and not mismatch
    return {"url": url, "safe": safe, "mismatch": mismatch,
            "ids": sorted(ids), "old": block, "new": upstream}


def apply_block_update(text, drift):
    """Replace the drifted block with the upstream text. Caller must check
    drift['safe'] first."""
    return text.replace(drift["old"], drift["new"], 1)


# --- orchestration --------------------------------------------------------

def sync_text(text, resolver, tree, fetcher):
    """Run all three checks on one tab. Returns (new_text_or_None, entries) where
    entries is a list of human-readable report lines for what could not be auto-
    applied. new_text is None when nothing was safely edited."""
    new_text = text
    entries = []
    texts = link_texts(text)

    for url, status in check_text(text, resolver):
        # Only a genuine 404 (moved/removed) or unreachable (0) is worth a fix
        # attempt; a 403/5xx is transient, so leave it for the next run.
        fixed = fix_moved_link(url, tree, texts.get(url)) if status in (404, 0) else None
        if fixed:
            new_text = new_text.replace(url, fixed)
        else:
            label = "unreachable" if status == 0 else str(status)
            entries.append(f"dead link [{label}]: {url}")

    drift = block_drift(text, fetcher)
    if drift:
        if drift["safe"]:
            new_text = apply_block_update(new_text, drift)
        elif drift["mismatch"]:
            named = ", ".join(drift["ids"]) or "block"
            entries.append(
                f"anchor mismatch: {named} is not in {drift['url']} "
                "(wrong source file, review)")
        else:
            entries.append(
                f"config block drifted from {drift['url']} "
                "(no krkn-src marker: review, not auto-updated)")

    return (new_text if new_text != text else None, entries)


def sync_tabs(content_root, resolver, tree, fetcher):
    """Walk _tab-krkn.md under content_root. Returns (edits, report) where edits
    is {relpath: new_text} and report is {relpath: [entries]}."""
    root = Path(content_root)
    edits, report = {}, {}
    for path in sorted(root.rglob("_tab-krkn.md")):
        rel = path.relative_to(root).as_posix()
        new_text, entries = sync_text(
            path.read_text(encoding="utf-8"), resolver, tree, fetcher)
        if new_text is not None:
            edits[rel] = new_text
        if entries:
            report[rel] = entries
    return edits, report


def format_report(edits, report):
    lines = []
    if edits:
        lines.append("Auto-fixed (draft PR):")
        for rel in edits:
            lines.append(f"- `{rel}`")
        lines.append("")
    if report:
        lines.append("Needs review:")
        for rel, entries in report.items():
            lines.append(f"- `{rel}`")
            for e in entries:
                lines.append(f"  - {e}")
    return "\n".join(lines) if lines else "All Krkn tabs are in sync."


# --- stdlib default boundaries + CLI --------------------------------------

def _http_status(url):
    # ponytail: fixed 10s timeout, no retry/backoff in v1.
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(
            url, method=method, headers={"User-Agent": "krkn-docs-bot"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405):
                continue
            return e.code
        except urllib.error.URLError:
            return 0
    return 0


def _github_tree(repo, ref):
    """Every blob path in the repo. One GitHub API call.
    ponytail: unauthenticated, so subject to the 60/hr rate limit; add a token
    header if we start hitting it."""
    api = f"https://api.github.com/repos/krkn-chaos/{repo}/git/trees/{ref}?recursive=1"
    req = urllib.request.Request(api, headers={"User-Agent": "krkn-docs-bot"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            tree = json.load(resp).get("tree", [])
    except (urllib.error.URLError, json.JSONDecodeError):
        return []
    return [n["path"] for n in tree if n.get("type") == "blob"]


def _raw_fetcher(repo, ref, path):
    raw = f"https://raw.githubusercontent.com/krkn-chaos/{repo}/{ref}/{path}"
    req = urllib.request.Request(raw, headers={"User-Agent": "krkn-docs-bot"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.URLError:
        return None


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    edits, report = sync_tabs(root, _http_status, _github_tree, _raw_fetcher)
    print(format_report(edits, report))


if __name__ == "__main__":
    main()
