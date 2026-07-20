from pathlib import Path

from bot import krkn_sync as ks

KRKN = "https://github.com/krkn-chaos/krkn/blob/main/scenarios/openshift/etcd.yml"
HUB = "https://github.com/krkn-chaos/scenarios-hub/blob/main/openshift/app_outage.yaml"
EXT = "https://github.com/redhat-cop/ocp4-helpernode"


# --- link check ---

def test_find_links_only_in_scope():
    text = f"[a]({KRKN}) [b]({HUB}) [c]({EXT})."
    assert ks.find_links(text) == [KRKN, HUB]


def test_check_text_flags_dead_and_unreachable():
    fake = {KRKN: 200, HUB: 404}
    assert ks.check_text(f"[a]({KRKN}) [b]({HUB})", fake.get) == [(HUB, 404)]


# --- link fix (folder-survivor rule) ---

CPU = "https://github.com/krkn-chaos/scenarios-hub/blob/main/openshift/cpu-hog/workflow.yaml"
CPU_FIXED = "https://github.com/krkn-chaos/scenarios-hub/blob/main/openshift/cpu-hog/cpu-hog.yml"


def test_fix_moved_link_folder_survivor():
    # workflow.yaml renamed to cpu-hog.yml in the same folder -> retarget.
    # .yaml and .yml are the same kind; label "cpu-hog.yml" confirms the survivor.
    tree = lambda repo, ref: ["openshift/cpu-hog/cpu-hog.yml", "openshift/other/x.yml"]
    assert ks.fix_moved_link(CPU, tree, link_text="cpu-hog.yml") == CPU_FIXED


def test_fix_moved_link_label_disagrees_returns_none():
    # sole survivor, but the filename-like label names a different file -> report
    tree = lambda repo, ref: ["openshift/cpu-hog/somethingelse.yml"]
    assert ks.fix_moved_link(CPU, tree, link_text="cpu-hog.yml") is None


def test_fix_moved_link_multiple_candidates_returns_none():
    tree = lambda repo, ref: ["openshift/cpu-hog/a.yml", "openshift/cpu-hog/b.yaml"]
    assert ks.fix_moved_link(CPU, tree) is None


def test_fix_moved_link_folder_gone_returns_none():
    tree = lambda repo, ref: ["openshift/other/x.yml"]
    assert ks.fix_moved_link(CPU, tree) is None


# --- config-block sync ---

TAB = """##### Sample scenario config

Example scenario file: [app_outage.yaml]({url})

```yaml
application_outage:
  duration: 600
```
""".format(url=HUB)

TAB_MARKED = TAB.replace(
    "```yaml", f"<!-- krkn-src: {HUB} -->\n```yaml", 1)


def test_block_in_sync_no_drift():
    fetcher = lambda r, ref, p: "application_outage:\n  duration: 600\n"
    assert ks.block_drift(TAB, fetcher) is None


def test_block_drift_unmarked_is_not_safe():
    fetcher = lambda r, ref, p: "application_outage:\n  duration: 900\n"
    drift = ks.block_drift(TAB, fetcher)
    assert drift["safe"] is False and drift["url"] == HUB


def test_block_drift_marked_is_safe_and_applies():
    upstream = "application_outage:\n  duration: 900\n"
    fetcher = lambda r, ref, p: upstream
    drift = ks.block_drift(TAB_MARKED, fetcher)
    assert drift["safe"] is True
    assert "duration: 900" in ks.apply_block_update(TAB_MARKED, drift)


# --- orchestration + walk ---

def test_sync_text_fixes_link_reports_unmarked_drift():
    resolver = lambda u: 404 if u == CPU else 200
    tree = lambda repo, ref: ["openshift/cpu-hog/cpu-hog.yml"]
    fetcher = lambda r, ref, p: "application_outage:\n  duration: 900\n"
    text = TAB + f"\nExample: [cpu-hog.yml]({CPU})\n"
    new_text, entries = ks.sync_text(text, resolver, tree, fetcher)
    assert "cpu-hog/cpu-hog.yml" in new_text             # link auto-fixed
    assert any("config block drifted" in e for e in entries)  # drift reported


def test_sync_tabs_walks_only_krkn_tabs(tmp_path):
    scn = tmp_path / "scenarios" / "demo"
    scn.mkdir(parents=True)
    (scn / "_tab-krkn.md").write_text(f"[x]({KRKN})", encoding="utf-8")
    (scn / "_tab-krkn-hub.md").write_text(f"[y]({KRKN})", encoding="utf-8")  # ignored
    edits, report = ks.sync_tabs(
        tmp_path, {KRKN: 404}.get, lambda repo, ref: [], lambda r, ref, p: None)
    key = (Path("scenarios") / "demo" / "_tab-krkn.md").as_posix()
    assert list(report) == [key]
    assert edits == {}  # dead link, no fix available -> report only


def test_format_report_all_clear():
    assert ks.format_report({}, {}) == "All Krkn tabs are in sync."
