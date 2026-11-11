#!/usr/bin/env python3
"""
How the crawler reads its own YAML settings files (filters.yaml, boards.yaml, sources.yaml), so a
missing or broken file ends in one plain sentence saying how to fix it, never a Python traceback.

It also fixes the easy slip of writing a list setting as plain text (`include_titles: paralegal`
instead of a list): Python would read that text one letter at a time. listify() turns it into a
one-item list, the same for every list setting in filters.yaml. A value that can't be used (a word
where a number goes, a list where one choice goes) ends in one plain sentence too: filters.yaml stops
the run, because it decides which jobs you see; sources.yaml only loses that one setting, because the
crawl can go on without it (clean_source_settings()). A true/false setting must be a real true or
false: text such as "maybe" or "no", or a blank, would otherwise run with the wrong meaning.

local_now() is the one clock for every date the crawler writes: your TIMEZONE from scripts/config.py
when that file exists, otherwise this computer's local time.

Run:  python3 config_files.py --selftest
"""
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

# Every setting in filters.yaml that holds a list.
FILTER_LIST_KEYS = ("include_titles", "include_keywords", "exclude_patterns", "flag_patterns",
                    "exclude_companies", "home_metros", "us_markers", "location_block")
# Every setting in filters.yaml that is true or false.
FILTER_BOOL_KEYS = ("require_us", "remote_ok")
# Every setting in sources.yaml that holds a number, and every one that holds text.
SOURCE_NUMBER_KEYS = ("max_queries", "count", "pages", "min_interval_minutes")
SOURCE_TEXT_KEYS = ("country", "geo", "category", "location", "level", "feed_url")
# Larger than any real setting, and small enough that date arithmetic on it can't overflow.
MAX_NUMBER = 10_000_000
# The full release keeps your TIMEZONE here. A crawler used on its own has no such file.
CONFIG_PY = Path(__file__).resolve().parents[2] / "scripts" / "config.py"
NO_YAML = ("PyYAML is not installed, and the crawler needs it to read its settings files. Install it with "
           "`python3 -m pip install -r pipeline/job-crawler/requirements.txt`, then run this again.")


class ConfigError(Exception):
    """A settings file can't be used. str(e) is one plain sentence with the fix."""


def local_now(config_path=None):
    """The current time from scripts/config.py's local_now() when that file can be used, otherwise
    this computer's local time. It is loaded by path, so nothing else named config can answer."""
    try:
        spec = importlib.util.spec_from_file_location("job_crawler_user_config",
                                                      Path(config_path) if config_path else CONFIG_PY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.local_now()
    except Exception:
        return datetime.now().astimezone()


def _rel(path):
    return f"pipeline/job-crawler/{Path(path).name}"


def parse_yaml(text, path):
    """The parsed YAML, or ConfigError saying which line to fix (or how to install PyYAML)."""
    try:
        import yaml
    except ImportError as e:
        raise ConfigError(NO_YAML) from e
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" near line {mark.line + 1}" if mark else ""
        raise ConfigError(f"{_rel(path)} is not valid YAML{where}: fix that line, or restore the "
                          f"shipped copy with `git checkout -- {_rel(path)}` (or, in a Download-ZIP copy, download that file again from the repo's GitHub page), then run this again.") from e


def read_yaml(path):
    """A settings file's parsed YAML, or ConfigError when it is missing, unreadable or broken."""
    try:
        text = Path(path).read_text()
    except FileNotFoundError as e:
        raise ConfigError(f"{_rel(path)} is missing: restore it with `git checkout -- {_rel(path)}` (or, in a Download-ZIP copy, download that file again from the repo's GitHub page), "
                          f"then run this again.") from e
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(f"{_rel(path)} can't be read ({e}): fix the file, or restore it with "
                          f"`git checkout -- {_rel(path)}` (or, in a Download-ZIP copy, download that file again from the repo's GitHub page), then run this again.") from e
    return parse_yaml(text, path)


def as_list(value, key):
    """A filters.yaml value as a list: nothing is an empty list, a single value a one-item list."""
    if value is None:
        return []
    if isinstance(value, dict):
        raise ConfigError(f"filters.yaml: {key} must be a list, like {key}: [\"one\", \"two\"].")
    items = list(value) if isinstance(value, (list, tuple)) else [value]
    if any(isinstance(x, (list, tuple, dict)) for x in items):
        raise ConfigError(f"filters.yaml: every entry under {key} must be plain text, like "
                          f"{key}: [\"one\", \"two\"].")
    return items


def listify(F):
    """A copy of filters.yaml's settings with every list setting read as a list."""
    if F is None:
        F = {}
    if not isinstance(F, dict):
        raise ConfigError("filters.yaml must be a set of settings such as `include_titles: [\"nurse\"]`: "
                          "fix it, or restore the shipped copy with "
                          "`git checkout -- pipeline/job-crawler/filters.yaml` (or, in a Download-ZIP copy, download that file again from the repo's GitHub page), then run this again.")
    F = dict(F)
    for k in FILTER_LIST_KEYS:
        F[k] = as_list(F.get(k), k)
    for k in FILTER_BOOL_KEYS:
        if k in F and not isinstance(F[k], bool):
            raise ConfigError(f"filters.yaml: {k} must be true or false, like {k}: true.")
    if isinstance(F.get("onsite_ok"), (list, tuple, dict)):
        raise ConfigError("filters.yaml: onsite_ok must be one of anywhere, home_metros, none.")
    return F


def in_range(value):
    """True for a real, finite number above 0 and within MAX_NUMBER. YAML's true/false, .inf and .nan
    are all refused."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= MAX_NUMBER


def lookback_hours(value, override=None):
    """The lookback window in hours: --hours (`override`) when given, otherwise filters.yaml's
    lookback_hours (`value`). ConfigError in one plain sentence when it is not a positive number."""
    if override is not None:
        if in_range(override):
            return override
        raise ConfigError(f"--hours must be a positive number of hours, no more than {MAX_NUMBER}.")
    if in_range(value):
        return value
    raise ConfigError(f"filters.yaml: lookback_hours must be a positive number of hours, no more than "
                      f"{MAX_NUMBER}, like lookback_hours: 72.")


def clean_source_settings(cfg, defaults):
    """(cfg, problems): sources.yaml's settings with each unusable number, text or true/false value
    put back to its built-in value (or left out when it has none), plus one plain sentence per
    value. Unset is not a problem, except a blank `enabled:`, which would quietly switch a source
    off. The Muse alone takes a list for its text settings."""
    out, problems = {}, []
    for name, block in cfg.items():
        out[name] = dict(block)

        def reset(key, want):
            problems.append(f"sources.yaml: {key} under {name} must be {want}, so the built-in setting "
                            f"was used for this run.")
            if key in defaults.get(name, {}):
                out[name][key] = defaults[name][key]
            else:
                del out[name][key]
        if "enabled" in block and not isinstance(block["enabled"], bool):
            reset("enabled", "true or false")
        for key in SOURCE_NUMBER_KEYS:
            value = block.get(key)
            if value is not None and not (in_range(value) and value >= 1):
                reset(key, f"a number from 1 to {MAX_NUMBER}")
        for key in SOURCE_TEXT_KEYS:
            value = block.get(key)
            kinds = (str, list) if name == "themuse" else str
            if value is not None and not isinstance(value, kinds):
                reset(key, "text or a list of text" if name == "themuse" else "text")
            elif key == "feed_url" and value and not value.startswith(("http://", "https://")):
                reset(key, "a web address")
    return out, problems


def _selftest():
    import tempfile
    tmp = Path(tempfile.mkdtemp())

    def refused(path):
        try:
            read_yaml(path)
        except ConfigError as e:
            return str(e)
        raise AssertionError(f"{path} should have been refused")

    gone = refused(tmp / "filters.yaml")
    assert "is missing" in gone and "git checkout -- pipeline/job-crawler/filters.yaml" in gone, gone
    (tmp / "boards.yaml").write_text("boards:\n  - {company: Acme\n")
    broken = refused(tmp / "boards.yaml")
    assert "not valid YAML near line" in broken and "boards.yaml" in broken, broken
    (tmp / "ok.yaml").write_text("a: 1\n")
    assert read_yaml(tmp / "ok.yaml") == {"a": 1}
    F = listify({"include_titles": "paralegal", "home_metros": "tulsa", "us_markers": None})
    assert F["include_titles"] == ["paralegal"] and F["home_metros"] == ["tulsa"] and F["us_markers"] == []
    assert listify(None)["flag_patterns"] == [] and listify({"exclude_patterns": ["x"]})["exclude_patterns"] == ["x"]
    assert listify({"include_titles": 7})["include_titles"] == [7]
    for key, bad in (("us_markers", [["a"]]), ("location_block", [{"a": 1}]), ("onsite_ok", ["denver"]),
                     ("onsite_ok", {"a": 1})):
        try:
            listify({key: bad})
            raise AssertionError(f"{key}: {bad} must be refused")
        except ConfigError as e:
            assert str(e).startswith("filters.yaml: ") and key in str(e) and "Error" not in str(e), e
    assert listify({"onsite_ok": "none"})["onsite_ok"] == "none"
    # the lookback window: only a real positive number passes, and --hours replaces the file's value
    assert lookback_hours(72) == 72 and lookback_hours(1.5) == 1.5 and lookback_hours(None, 24) == 24
    for bad in (None, "soon", "72", -5, 0, True, [72], {"a": 1}, float("inf"), float("nan"), 1e300, 10**30):
        try:
            lookback_hours(bad)
            raise AssertionError(f"lookback_hours {bad!r} must be refused")
        except ConfigError as e:
            assert "filters.yaml" in str(e) and "lookback_hours" in str(e) and "Error" not in str(e), e
    for bad in (0, -1, 10**30):
        try:
            lookback_hours(72, bad)
            raise AssertionError(f"--hours {bad} must be refused")
        except ConfigError as e:
            assert "--hours" in str(e), e
    # sources.yaml: a bad value goes back to its built-in setting, a good or unset one is left alone
    builtin = {"acme": {"max_queries": 5, "geo": "usa"}}
    got, why = clean_source_settings({"acme": {"max_queries": "many", "geo": ["usa"], "count": [1], "pages": 3},
                                      "themuse": {"level": ["Entry"], "location": 7}}, builtin)
    assert got == {"acme": {"max_queries": 5, "geo": "usa", "pages": 3}, "themuse": {"level": ["Entry"]}}, got
    assert len(why) == 4 and all(w.startswith("sources.yaml: ") and "Error" not in w for w in why), why
    assert clean_source_settings({"acme": {"max_queries": None, "geo": "", "pages": 2}}, builtin)[1] == []
    assert clean_source_settings({"acme": {"feed_url": "soon"}}, builtin)[0] == {"acme": {}}
    assert clean_source_settings({"acme": {"feed_url": "https://acme.example/f"}}, builtin)[1] == []
    for bad in (-1, 0, 0.5, True, float("inf"), float("nan"), 1e300):
        assert clean_source_settings({"acme": {"min_interval_minutes": bad}}, builtin)[0] == {"acme": {}}, bad
    for bad in (["a"], "text"):
        try:
            listify(bad)
            raise AssertionError("a filters file that isn't settings must be refused")
        except ConfigError:
            pass
    try:
        listify({"include_titles": {"a": 1}})
        raise AssertionError("a mapping is not a list")
    except ConfigError as e:
        assert "must be a list" in str(e)
    # true/false settings: only a real boolean passes. Anything else in filters.yaml stops the run
    assert listify({"require_us": False, "remote_ok": True})["require_us"] is False
    assert "require_us" not in listify({})                  # unset keeps its default where it is read
    for key in FILTER_BOOL_KEYS:
        for bad in ("maybe", "no", "false", None, 0, 1, ["x"]):
            try:
                listify({key: bad})
                raise AssertionError(f"{key}: {bad!r} must be refused")
            except ConfigError as e:
                assert str(e).startswith(f"filters.yaml: {key} must be true or false"), e
    # in sources.yaml a wrong value names the file and goes back to the built-in setting
    on = {"acme": {"enabled": True}}
    for bad in ("no", "false", "", None, 0, 1):
        got, why = clean_source_settings({"acme": {"enabled": bad}}, on)
        assert got == on and len(why) == 1 and why[0].startswith("sources.yaml: enabled under acme"), (bad, why)
    assert clean_source_settings({"acme": {"enabled": False}}, on) == ({"acme": {"enabled": False}}, [])
    assert clean_source_settings({"acme": {"pages": 2}}, on)[1] == []
    assert clean_source_settings({"other": {"enabled": "off"}}, on)[0] == {"other": {}}
    # no PyYAML: one plain sentence with the install line, never a ModuleNotFoundError
    saved_yaml = sys.modules.get("yaml")
    sys.modules["yaml"] = None
    try:
        try:
            parse_yaml("a: 1\n", tmp / "filters.yaml")
            raise AssertionError("no PyYAML must be a ConfigError")
        except ConfigError as e:
            assert "python3 -m pip install -r pipeline/job-crawler/requirements.txt" in str(e), e
    finally:
        if saved_yaml is None:
            del sys.modules["yaml"]
        else:
            sys.modules["yaml"] = saved_yaml
    # the clock: a zone far from any real machine's, proving the config file's answer is the one used
    (tmp / "zoned.py").write_text("from datetime import datetime\nfrom zoneinfo import ZoneInfo\n"
                                  "def local_now():\n    return datetime.now(ZoneInfo('Pacific/Kiritimati'))\n")
    assert local_now(tmp / "zoned.py").utcoffset().total_seconds() == 14 * 3600
    (tmp / "broken.py").write_text("def local_now(:\n")
    (tmp / "no_clock.py").write_text("TIMEZONE = None\n")
    for fallback in (tmp / "absent.py", tmp / "broken.py", tmp / "no_clock.py"):
        got = local_now(fallback)
        assert got.utcoffset() == datetime.now().astimezone().utcoffset(), fallback
    print("config_files.py selftest: OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        try:
            sys.exit(_selftest())
        except ConfigError as err:
            print(str(err), file=sys.stderr)
            sys.exit(2)
    print(__doc__.strip())
