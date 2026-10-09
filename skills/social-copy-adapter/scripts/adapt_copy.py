#!/usr/bin/env python3
"""
adapt_copy.py
=============
The deterministic half of adapting one piece of social copy for several
platforms. Stdlib only. No network, no model calls, no credentials, no files
read except the limits table next to SKILL.md and the text you point it at.

This is SocialForge's copy-adapter script, extracted so the skill can run on
its own. The adaptation functions (truncate_smart, render_cta,
adapt_for_platform, generate_bilingual) and the limits loader and counting
code are deliberately the same code, apart from one sentence:
generate_bilingual's `note` no longer points at tools this skill does not
have. tests/test_adapt_copy.py proves the rest against SocialForge whenever
the two repositories sit side by side. What differs: the limits come from
../platforms.json (SocialForge: scripts/platform_limits.json), brand profiles
are gone (pass hashtags and the comment keyword on the command line),
unknown platforms exit 1, and four conveniences were added around the
unchanged core: several platforms in one run, --text-file, --check and
--sources.

What it does, per platform:
    * reserves room for the CTA, then cuts the copy to the limit at the last
      sentence boundary that fits (a mechanical cut, not a rewrite);
    * counts length the way the platform does where that is known: X by
      weight (emoji and CJK count 2, every URL counts 23), everyone else by
      plain characters (Python len);
    * turns the CTA into the platform's mechanism: kept as written where links
      work, or "Comment KEYWORD" / "link in bio" where they do not;
    * keeps at most `hashtag_limit` hashtags, says where they go (Instagram:
      first comment) and lists the ones it left out in `hashtags_dropped`;
    * reports `char_count`, `char_limit`, `within_limit` and `count_method`.
What it does not do: write, translate, rewrite for tone, check compliance, or
post anything. See SKILL.md, "What the script does not do".

Usage:
    python adapt_copy.py --text "Post body." --platform x
    python adapt_copy.py --text-file post.txt --platform x instagram linkedin \\
        --cta "Get the guide: https://example.com/guide" --cta-keyword GUIDE \\
        --hashtags "#Onboarding" "#SaaS"
    python adapt_copy.py --text-file post.txt --platform all
    python adapt_copy.py --check --text-file final-post.txt --platform x bluesky
    python adapt_copy.py --list-platforms
    python adapt_copy.py --sources

Output: JSON on stdout. One platform prints that platform's object; several
print {"platforms": {name: object, ...}}. Exit 0, or exit 1 when any result
carries an "error" key (unknown platform, unreadable file or limits table).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# The limits table ships one level up from scripts/, inside the skill folder.
PLATFORMS_PATH = Path(__file__).resolve().parent.parent / "platforms.json"

_COUNT_METHODS = ("x_weighted",)


def _x_weighted_config(raw):
    """The X counting rules recorded in the data file (`counting.x_weighted.config`,
    field names as in twitter-text's config/v3.json), checked and unpacked."""
    cfg = raw["counting"]["x_weighted"]["config"]
    ranges = []
    for item in cfg["ranges"]:
        start, end, weight = item["start"], item["end"], item["weight"]
        if (not all(isinstance(v, int) and not isinstance(v, bool) for v in (start, end, weight))
                or start > end or weight < 0):
            raise ValueError("counting.x_weighted.config.ranges needs integer start <= end and weight >= 0")
        ranges.append((start, end, weight))
    scale, default, url_len = cfg["scale"], cfg["defaultWeight"], cfg["transformedURLLength"]
    if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in (scale, default, url_len)):
        raise ValueError("counting.x_weighted.config needs positive integer scale, "
                         "defaultWeight and transformedURLLength")
    return {"scale": scale, "default_weight": default, "url_length": url_len, "ranges": ranges}


def _load_platforms(path):
    """Read the limits table. Returns (limits_by_platform, raw_data, error)."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        platforms = raw["platforms"]
        limits = {}
        for name, entry in platforms.items():
            spec = entry["limits"]
            if not isinstance(spec.get("char_limit"), int) or spec["char_limit"] < 1:
                raise ValueError(f"{name}: limits.char_limit must be a positive integer")
            method = spec.get("count_method")
            if method is not None and method not in _COUNT_METHODS:
                raise ValueError(f"{name}: limits.count_method must be one of {', '.join(_COUNT_METHODS)}")
            if method == "x_weighted":
                _x_weighted_config(raw)
            limits[name] = spec
        if not limits:
            raise ValueError("no platforms listed")
        return limits, raw, None
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {}, {}, f"could not load {path}: {exc}"


PLATFORM_LIMITS, _RAW_DATA, _DATA_ERROR = _load_platforms(PLATFORMS_PATH)
_X_WEIGHTED = _x_weighted_config(_RAW_DATA) if any(
    spec.get("count_method") == "x_weighted" for spec in PLATFORM_LIMITS.values()) else None


def _provenance(raw):
    """What --sources prints: per platform, where each number came from."""
    out = {}
    for name, entry in raw["platforms"].items():
        confirmed = entry.get("confirmed", [])
        differs = entry.get("differs", [])
        out[name] = {
            "source": entry.get("source"),
            "checked": entry.get("checked"),
            "status": {key: ("confirmed" if key in confirmed else "differs" if key in differs else "unsourced")
                       for key in entry["limits"]},
            "confirmed": confirmed,
            "differs": differs,
            "unsourced": entry.get("unsourced", []),
            "also_read": entry.get("also_read", []),
            "notes": entry.get("notes"),
        }
    return out


# A URL as X counts it for weighting: starts with http://, https:// or www.,
# is not glued to a word, and does not end in sentence punctuation (that
# stays ordinary text, which can only make the count higher than X's).
_X_URL_RE = re.compile(
    r"(?<![\w@#$.\-/])(?:https?://|www\.)\S*[^\s.,;:!?)\]}'\"”’»]", re.IGNORECASE)


def _plain_weight(text, default, ranges):
    total = 0
    for char in text:
        code = ord(char)
        for start, end, weight in ranges:
            if start <= code <= end:
                total += weight
                break
        else:
            total += default
    return total


def weighted_length(text, config):
    """X's weighted length of `text` under `config` (see _x_weighted_config),
    rounded up to whole characters.

    The text is normalised to NFC first, as X does. A code point inside a
    configured range then weighs that range's weight, every other code point
    the default (so emoji and CJK weigh 2), and every URL weighs the
    transformed URL length (23) however long it is. One thing the reference
    counter does is left out on purpose: it parses an emoji sequence as one
    emoji (2), while here each code point of the sequence is weighed, which can
    only make the count higher.
    """
    text = unicodedata.normalize("NFC", text)
    scale, default, ranges = config["scale"], config["default_weight"], config["ranges"]
    total = 0
    position = 0
    for match in _X_URL_RE.finditer(text):
        total += _plain_weight(text[position:match.start()], default, ranges)
        total += config["url_length"] * scale
        position = match.end()
    total += _plain_weight(text[position:], default, ranges)
    return -(-total // scale)


def _measurer(specs):
    """The length function for a platform: len() unless its limits say otherwise."""
    if specs.get("count_method") == "x_weighted":
        return lambda text: weighted_length(text, _X_WEIGHTED)
    return len


def _fit(text, budget, measure):
    """The longest prefix length whose measure is within budget (0 if none)."""
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if measure(text[:mid]) <= budget:
            low = mid
        else:
            high = mid - 1
    return low


def truncate_smart(text, limit, measure=len):
    """Truncate at last complete sentence that fits.

    `measure` is how the platform counts length: len for most platforms, X's
    weighted count for X. With the default, the slicing is exactly what it
    always was.
    """
    if measure(text) <= limit:
        return text
    if measure is len:
        keep, keep_ellipsis = limit, limit - 3
    else:
        keep, keep_ellipsis = _fit(text, limit, measure), _fit(text, limit - 3, measure)
    truncated = text[:keep]
    last_period = truncated.rfind(".")
    last_excl = truncated.rfind("!")
    last_quest = truncated.rfind("?")
    best_break = max(last_period, last_excl, last_quest)
    if best_break > keep * 0.5:
        candidate = truncated[:best_break + 1]
        if measure(candidate) <= limit:
            return candidate
    return truncated[:keep_ellipsis] + "..."


def _as_hashtag(value):
    """One hashtag with its '#': brand configs and --campaign-hashtags are
    written both ways ("#AcmeCorp" and "AcmeCorp"), and a bare word posted as a
    hashtag is just a word."""
    tag = str(value or "").strip().replace(" ", "")
    if not tag.lstrip("#"):
        return ""
    return "#" + tag.lstrip("#")


_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def render_cta(cta, specs, cta_keyword=None):
    """Turn the intended call-to-action into the platform's actual mechanism.

    A CTA is not a string you append; it is a mechanism that differs per
    platform. On link platforms the CTA (URL and all) works as written. On
    bio-link platforms (Instagram, TikTok) a pasted URL is dead weight: the
    link lives in the profile, and the caption's job is to name the offer and
    route the reader there, or, when a comment-keyword automation is running,
    to ask for the keyword.
    """
    if not cta:
        return None
    if specs.get("link") != "bio":
        return cta

    keyword = (cta_keyword or "").strip()
    if keyword:
        # A comment-keyword automation is running: the keyword IS the mechanism.
        return f'Comment "{keyword}" and we\'ll send you the link.'

    offer = _URL_RE.sub("", cta).strip(" \t-–—:,.")
    if offer:
        return f"{offer} — link in bio."
    # The CTA was only a URL; nothing to name, so route to the bio plainly.
    return "Link in bio."


def adapt_for_platform(copy_text, platform, brand_hashtags=None, cta=None, cta_keyword=None):
    """Adapt copy for a specific platform."""
    specs = PLATFORM_LIMITS.get(platform)
    if not specs:
        return {"error": f"Unknown platform: {platform}"}

    # Length is counted the way the platform counts it: X by weight (URLs
    # count 23, emoji and CJK 2), every other platform by plain len().
    count = _measurer(specs)

    # Render the CTA first: the room it needs must be reserved BEFORE
    # truncation. It used to be appended after, so a limit-length post plus its
    # CTA overflowed the platform limit and the script shipped copy it had
    # itself just measured as too long.
    rendered_cta = render_cta(cta, specs, cta_keyword)
    cta_block = f"\n\n{rendered_cta}" if rendered_cta else ""

    # Hashtags, normalised ("LinkRot" -> "#LinkRot"). Whatever the cap leaves out
    # is reported, never lost silently.
    all_hashtags = [_as_hashtag(h) for h in (brand_hashtags or []) if _as_hashtag(h)]
    hashtag_limit = specs.get("hashtag_limit", 5)
    hashtag_text = " ".join(all_hashtags[:hashtag_limit])
    hashtags_dropped = all_hashtags[hashtag_limit:]
    placement = specs.get("hashtag_placement", "inline")
    # Inline hashtags (and Bluesky's tag facets) are part of the post's text, so
    # their room is reserved like the CTA's. They used to be measured apart: a
    # 255-character X post plus "#LinkRot #ContentMarketing" was reported within
    # the 280 limit and published at 282.
    in_text = placement != "first_comment" and bool(hashtag_text)
    hashtag_block = f"\n\n{hashtag_text}" if in_text else ""

    adapted = copy_text

    # Truncate to fold point (for preview visibility) or optimal limit
    fold_at = specs.get("fold_at")
    limit = specs.get("optimal_limit", specs["char_limit"])
    body_limit = max(1, limit - count(cta_block) - count(hashtag_block))

    if fold_at and len(copy_text) > fold_at:
        # For platforms with "see more" fold: ensure hook is in first N chars
        # Full copy still saved, but first fold_at chars must be compelling
        adapted = copy_text  # Keep full copy
        if count(adapted) > body_limit:
            adapted = truncate_smart(adapted, body_limit, count)
    else:
        adapted = truncate_smart(adapted, body_limit, count)

    adapted += cta_block

    # Instagram first-comment strategy: hashtags go in first comment, not caption
    first_comment = None
    if placement == "first_comment":
        first_comment = hashtag_text or None
        hashtag_text = ""  # Don't include in main copy

    # What actually gets published: the copy plus any in-text hashtags.
    post_text = adapted + hashtag_block
    fold_at_val = specs.get("fold_at")
    result = {
        "platform": platform,
        "copy": adapted,
        "post_text": post_text,
        "char_count": count(adapted),
        "post_char_count": count(post_text),
        "char_limit": specs["char_limit"],
        "within_limit": count(post_text) <= specs["char_limit"],
        "count_method": specs.get("count_method", "code_points"),
        "cta_mechanism": ("comment-keyword" if (cta and cta_keyword and specs.get("link") == "bio")
                          else "bio-link" if (cta and specs.get("link") == "bio")
                          else "direct-link" if cta else None),
        "cta_rendered": rendered_cta,
        "fold_at": fold_at_val,
        "hook_visible": adapted[:fold_at_val] if fold_at_val else adapted[:100],
        "hashtags": hashtag_text,
        "hashtag_placement": specs.get("hashtag_placement", "inline"),
        "first_comment": first_comment,
        "hashtags_dropped": hashtags_dropped,
    }

    return result


def generate_bilingual(copy_text, platform, primary_lang="en", secondary_lang=None, mode="separate_posts"):
    """Generate bilingual copy variants."""
    if not secondary_lang:
        return {"primary": copy_text, "secondary": None, "mode": mode}

    # In actual use, the agent writes the translation. This function structures the output.
    return {
        "primary": copy_text,
        "primary_lang": primary_lang,
        "secondary": f"[TRANSLATE TO {secondary_lang}]: {copy_text}",
        "secondary_lang": secondary_lang,
        "mode": mode,
        "note": "Secondary copy requires translation. Replace the bracketed placeholder with the real translation, then run --check on it."
    }


# A hashtag for --check: "#" not glued to a word before it (so "C#" and URL
# fragments like "page#top" are not counted) and with at least one letter in
# it (so "#1" and "#2026" are not counted).
_HASHTAG_RE = re.compile(r"(?<!\w)#(?=\w*[^\W\d_])\w+")


def check_copy(text, platform):
    """Measure FINISHED text against a platform's limits. Adds nothing, cuts nothing.

    Use it on the exact string you will post: the assembled caption with its
    CTA and any inline hashtags, or a translated variant. Length is counted
    the same way adapt_for_platform counts it: X by weight, the rest by len().
    """
    specs = PLATFORM_LIMITS.get(platform)
    if not specs:
        return {"error": f"Unknown platform: {platform}"}
    count = _measurer(specs)(text)
    char_limit = specs["char_limit"]
    optimal = specs.get("optimal_limit")
    tags = _HASHTAG_RE.findall(text)
    cap = specs.get("hashtag_limit", 5)
    fold_at = specs.get("fold_at")
    return {
        "platform": platform,
        "char_count": count,
        "char_limit": char_limit,
        "within_limit": count <= char_limit,
        "count_method": specs.get("count_method", "code_points"),
        "optimal_limit": optimal,
        "within_optimal": (count <= optimal) if optimal else None,
        "hashtags_in_text": len(tags),
        "hashtag_limit": cap,
        "hashtags_within_limit": len(tags) <= cap,
        "hashtag_placement": specs.get("hashtag_placement", "inline"),
        "fold_at": fold_at,
        "hook_visible": text[:fold_at] if fold_at else text[:100],
    }


def _ensure_utf8_stdout() -> None:
    """Force UTF-8 (errors=replace) on stdout/stderr.

    Windows consoles default to cp1252; printing JSON containing em dashes or
    non-Latin text would otherwise raise UnicodeEncodeError.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _finish(result, failed=None) -> None:
    """Print the result JSON and exit: 1 when it carries an error, 0 otherwise,
    so shell callers can trust $?."""
    _ensure_utf8_stdout()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if failed is None:
        failed = isinstance(result, dict) and "error" in result
    sys.exit(1 if failed else 0)


def _read_text_source(args):
    """The post text: --text, or --text-file (a path, or - for stdin)."""
    if args.text is not None:
        return args.text
    if args.text_file == "-":
        _ensure_utf8_stdout()
        try:
            raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        except OSError as exc:
            _finish({"error": f"could not read stdin: {exc}"})
        text = raw.replace("\r\n", "\n").replace("\r", "\n")
    else:
        path = Path(args.text_file).expanduser()
        if not path.is_file():
            _finish({"error": f"file not found: {path}",
                     "recovery": "Pass the path to a text file holding the post, or use --text."})
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _finish({"error": f"could not read {path}: {exc}"})
    # Editors end files with a newline that is not part of the post.
    return text.rstrip("\r\n")


def main():
    parser = argparse.ArgumentParser(
        description="Adapt one piece of social copy for platform limits, CTA mechanism "
                    "and hashtag placement (the deterministic half; the writing is yours)")
    # Required for an adaptation, but must stay optional so --list-platforms works
    parser.add_argument("--text", default=None, help="Source copy text")
    parser.add_argument("--text-file", default=None,
                        help="Read the copy from a file instead (a path, or - for stdin)")
    parser.add_argument("--platform", nargs="+", metavar="PLATFORM", default=None,
                        help="Target platform(s), or 'all'. One platform prints its object; "
                             "several print {\"platforms\": {...}}")
    parser.add_argument("--cta", default=None, help="Call-to-action text or URL")
    parser.add_argument("--cta-keyword", default=None,
                        help="Comment keyword for bio-link platforms when you run a comment "
                             "automation (e.g. GUIDE). Without one, the CTA names the offer "
                             "+ 'link in bio'.")
    parser.add_argument("--hashtags", nargs="*", default=None,
                        help="Always-on hashtags, in priority order (extras past the "
                             "platform's hashtag_limit come back in hashtags_dropped)")
    parser.add_argument("--campaign-hashtags", nargs="*", default=None,
                        help="Campaign-specific hashtags, added after --hashtags")
    parser.add_argument("--primary-lang", default="en", help="Language of the source copy")
    parser.add_argument("--secondary-lang", default=None,
                        help="Secondary language for bilingual posts")
    parser.add_argument("--bilingual-mode", default="separate_posts",
                        choices=["separate_posts", "bilingual_single_post", "language_per_platform"])
    parser.add_argument("--check", action="store_true",
                        help="Measure finished text against the platform(s) instead of "
                             "adapting it: adds no CTA, cuts nothing")
    parser.add_argument("--list-platforms", action="store_true",
                        help="Print the limits the script reads")
    parser.add_argument("--sources", action="store_true",
                        help="Print where each platform's limits came from and what is "
                             "confirmed, differs or unsourced")
    args = parser.parse_args()

    if _DATA_ERROR:
        _finish({"error": _DATA_ERROR,
                 "recovery": "Restore platforms.json next to SKILL.md, or fix the field named above."})

    if args.list_platforms:
        _ensure_utf8_stdout()
        print(json.dumps(PLATFORM_LIMITS, indent=2, ensure_ascii=False))
        return
    if args.sources:
        _ensure_utf8_stdout()
        print(json.dumps(_provenance(_RAW_DATA), indent=2, ensure_ascii=False))
        return

    if args.text is not None and args.text_file is not None:
        parser.error("use --text or --text-file, not both")
    missing = []
    if not (args.text or args.text_file):
        missing.append("--text or --text-file")
    if not args.platform:
        missing.append("--platform")
    if missing:
        parser.error("the following arguments are required: " + ", ".join(missing))
    if args.check and any(v is not None for v in (args.cta, args.cta_keyword, args.hashtags,
                                                  args.campaign_hashtags, args.secondary_lang)):
        parser.error("--check measures finished text; it does not take --cta, --cta-keyword, "
                     "--hashtags, --campaign-hashtags or --secondary-lang")

    text = _read_text_source(args)
    if not text:
        parser.error("the post text is empty")

    platforms = []
    for name in args.platform:
        for expanded in (list(PLATFORM_LIMITS) if name == "all" else [name]):
            if expanded not in platforms:
                platforms.append(expanded)

    brand_hashtags = list(args.hashtags or [])
    if args.campaign_hashtags:
        brand_hashtags.extend(args.campaign_hashtags)

    results = {}
    for platform in platforms:
        if args.check:
            result = check_copy(text, platform)
        else:
            result = adapt_for_platform(text, platform, brand_hashtags, args.cta,
                                        cta_keyword=args.cta_keyword)
            # Bilingual variants when a secondary language is requested
            if args.secondary_lang and "error" not in result:
                result["bilingual"] = generate_bilingual(
                    result["copy"], platform, args.primary_lang, args.secondary_lang,
                    args.bilingual_mode)
        if "error" in result:
            result["recovery"] = "Known platforms: " + ", ".join(PLATFORM_LIMITS) + ", or 'all'."
        results[platform] = result

    failed = any("error" in r for r in results.values())
    if len(results) == 1:
        _finish(next(iter(results.values())), failed=failed)
    _finish({"platforms": results}, failed=failed)


if __name__ == "__main__":
    main()
