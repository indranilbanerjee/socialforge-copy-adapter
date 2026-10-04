"""Tests for the standalone social-copy-adapter skill. Stdlib unittest only; pytest runs them too.

Run from the repository root:

    python -m pytest tests -q
    python -m unittest discover -s tests -v

Six layers:

  1. The limits table (platforms.json): shape, provenance, and that every entry
     is either sourced or says it is unsourced, with no vendor or price content.
  2. The script on its own: mechanical cut, CTA mechanisms, hashtag caps and
     placement, bilingual structure, --check, the command line, and that the
     limits really are data (edit the file, the script follows).
  3. The skill is self-contained and honest: frontmatter is valid, every file
     SKILL.md points at exists, nothing refers to a plugin, command, agent or
     pipeline this repository does not have, the platform table matches the data,
     the caption craft rules and the framing sentences are present.
  4. The README: the example is a real run (the documented command is executed and
     its output compared byte for byte), exactly one link back to SocialForge.
  5. PARITY with SocialForge. When ../../SocialForge (relative to the repo root;
     override with $SOCIALFORGE_DIR) is present, this script and SocialForge's
     adapt_copy.py must return identical results on a grid of platforms, texts,
     CTAs, keywords and hashtag lists plus seeded random cases, the adaptation
     functions must be the same code, and the command lines must agree. Skipped
     otherwise, so a stand-alone clone still passes.
  6. A stand-alone clone passes: the suite is run from a copy of this repository
     that has no SocialForge beside it.

The parity tests only ever READ SocialForge; bytecode writing is disabled so
importing its module cannot leave .pyc files behind there.
"""
import ast
import copy
import datetime
import importlib.util
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True  # parity imports SocialForge; never write into it

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "social-copy-adapter"
SCRIPT = SKILL / "scripts" / "adapt_copy.py"
PLATFORMS = SKILL / "platforms.json"
SKILL_MD = SKILL / "SKILL.md"
README = ROOT / "README.md"

SF_ROOT = Path(os.environ.get("SOCIALFORGE_DIR") or (ROOT / ".." / ".." / "SocialForge")).resolve()
SF_SCRIPT = SF_ROOT / "scripts" / "adapt_copy.py"
HAVE_SF = SF_SCRIPT.is_file()
NESTED = os.environ.get("COPY_ADAPTER_NESTED_RUN") == "1"

NINE = ["linkedin", "instagram", "x", "facebook", "youtube", "tiktok", "pinterest", "threads", "bluesky"]
UNSOURCED = "SocialForge data, unsourced"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(path):
    return Path(path).read_text(encoding="utf-8")


hero = load_module("hero_adapt_copy", SCRIPT)


def run_cli(args, stdin=None, cwd=None, script=SCRIPT):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for var in ("CLAUDE_PLUGIN_DATA", "PLUGIN_DATA"):
        env.pop(var, None)
    proc = subprocess.run([sys.executable, "-B", str(script), *args],
                          input=stdin, capture_output=True, cwd=cwd, env=env)
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")


# ---------------------------------------------------------------------------
# Fixtures shared by the behaviour tests and the parity grid
# ---------------------------------------------------------------------------

CTA_URL = "Grab the free audit template: https://example.com/audit"

TEXTS = {
    "empty": "",
    "short": "Short.",
    "one_sentence_no_punct": "A single sentence with no terminal punctuation",
    "multi_sentence": "First sentence here. Second sentence follows! Third one asks a question? Fourth closes.",
    "long_sentences": "A sentence that fills space. " * 40,
    "long_no_punct": "word " * 700,
    "paragraphs": "Para one is short.\n\nPara two has more words in it. And another sentence.\n\nPara three?",
    "unicode": "Café ☕ नमस्ते 世界 😀. Second sentence with emoji 😀😀😀! " * 12,
    "urls_inside": "Read the report at https://example.com/report. It covers www.example.org too. " * 15,
    "exactly_280": ("x" * 279) + ".",
    "exactly_281": ("x" * 280) + ".",
}

CTAS = [
    None,
    "",
    CTA_URL,
    "https://example.com/x",
    "Download the guide — https://a.b/c",
    "Subscribe today",
    "Subscribe today: www.example.com/s",
    "  - https://example.com  ",
    "Read the full breakdown: https://example.com/a-very-long-path-" + "x" * 250,
]

KEYWORDS = [None, "", "  ", "AUDIT", " GUIDE "]

HASHTAG_LISTS = [
    None,
    [],
    ["#A"],
    ["#A", "#B", "#C", "#D", "#E", "#F", "#G"],
    ["#Tag%d" % i for i in range(40)],
]

# ---------------------------------------------------------------------------
# 1. The limits table
# ---------------------------------------------------------------------------

LIMIT_KEYS = {"char_limit", "fold_at", "optimal_limit", "hashtag_limit", "hashtag_placement", "link"}


class TestLimitsData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(read(PLATFORMS))
        cls.platforms = cls.data["platforms"]

    def test_the_nine_platforms_are_present(self):
        self.assertEqual(list(self.platforms), NINE)

    def test_limits_are_well_formed(self):
        for name, entry in self.platforms.items():
            limits = entry["limits"]
            with self.subTest(platform=name):
                self.assertLessEqual(set(limits), LIMIT_KEYS)
                self.assertIn("char_limit", limits)
                self.assertIn("link", limits)
                self.assertIn("hashtag_limit", limits)
                for key in ("char_limit", "fold_at", "optimal_limit", "hashtag_limit"):
                    if key in limits:
                        self.assertIsInstance(limits[key], int)
                        self.assertGreater(limits[key], 0)
                self.assertIn(limits["link"], {"direct", "bio"})
                if "hashtag_placement" in limits:
                    self.assertIn(limits["hashtag_placement"], {"first_comment", "tag_facets"})
                if "optimal_limit" in limits:
                    self.assertLessEqual(limits["optimal_limit"], limits["char_limit"])

    def test_every_entry_is_sourced_or_says_it_is_unsourced(self):
        for name, entry in self.platforms.items():
            with self.subTest(platform=name):
                src = entry["source"]
                self.assertTrue(src == UNSOURCED or re.match(r"^https://\S+$", src), src)

    def test_checked_is_a_real_past_date(self):
        for name, entry in self.platforms.items():
            with self.subTest(platform=name):
                day = datetime.date.fromisoformat(entry["checked"])
                self.assertLessEqual(day, datetime.date.today())

    def test_confirmed_differs_unsourced_partition_the_limits(self):
        for name, entry in self.platforms.items():
            keys = set(entry["limits"])
            lists = [set(entry["confirmed"]), set(entry["differs"]), set(entry["unsourced"])]
            with self.subTest(platform=name):
                self.assertEqual(sum(len(s) for s in lists), len(keys), "a key is listed twice")
                self.assertEqual(set().union(*lists), keys)

    def test_a_cited_source_confirms_or_contradicts_something(self):
        for name, entry in self.platforms.items():
            with self.subTest(platform=name):
                if entry["source"] == UNSOURCED:
                    self.assertEqual(entry["confirmed"], [])
                    self.assertEqual(entry["differs"], [])
                else:
                    self.assertTrue(entry["confirmed"] or entry["differs"],
                                    "a source is cited but nothing is marked confirmed or differs")

    def test_a_differing_value_is_explained(self):
        for name, entry in self.platforms.items():
            if entry["differs"]:
                with self.subTest(platform=name):
                    self.assertIn("kept", entry["notes"].lower())

    def test_notes_exist_and_the_file_explains_itself(self):
        for name, entry in self.platforms.items():
            with self.subTest(platform=name):
                self.assertGreater(len(entry["notes"]), 20)
        for key in ("_about", "_data_origin", "_checked_means", "_fields"):
            self.assertIn(key, self.data)

    def test_no_model_ids_or_prices_in_the_data(self):
        raw = read(PLATFORMS)
        self.assertIsNone(re.search(r"\$\s?\d", raw))
        self.assertIsNone(re.search(r"(?i)\b(claude|gpt|gemini|veo|kling|sora|imagen|llama|mistral)[-\s]?\d", raw))

    def test_script_reads_the_table_next_to_skill_md(self):
        self.assertEqual(hero.PLATFORMS_PATH.resolve(), PLATFORMS.resolve())
        self.assertIsNone(hero._DATA_ERROR)
        self.assertEqual(hero.PLATFORM_LIMITS, {n: e["limits"] for n, e in self.platforms.items()})


# ---------------------------------------------------------------------------
# 2. The script on its own
# ---------------------------------------------------------------------------

class TestTruncation(unittest.TestCase):
    def test_text_within_the_limit_is_untouched(self):
        self.assertEqual(hero.truncate_smart("Fits.", 50), "Fits.")
        self.assertEqual(hero.truncate_smart("x" * 50, 50), "x" * 50)

    def test_cuts_at_the_last_sentence_past_halfway(self):
        text = "First sentence ends here. Second one is much longer and runs past the limit."
        self.assertEqual(hero.truncate_smart(text, 40), "First sentence ends here.")

    def test_early_sentence_end_falls_back_to_an_ellipsis(self):
        text = "Hi. " + "word " * 30
        out = hero.truncate_smart(text, 40)
        self.assertTrue(out.endswith("..."))
        self.assertEqual(len(out), 40)

    def test_question_and_exclamation_count_as_sentence_ends(self):
        self.assertEqual(hero.truncate_smart("Really now? Yes indeed it is so, and more words follow here.", 18),
                         "Really now?")
        self.assertEqual(hero.truncate_smart("What a day for it! Then more words follow after that.", 30),
                         "What a day for it!")


class TestCtaMechanism(unittest.TestCase):
    def test_every_platform_carries_the_cta_in_some_form(self):
        for platform, specs in hero.PLATFORM_LIMITS.items():
            with self.subTest(platform=platform):
                out = hero.adapt_for_platform("A post body.", platform, cta=CTA_URL)
                self.assertIsNotNone(out["cta_rendered"])
                if specs.get("link") == "bio":
                    self.assertIn("audit template", out["copy"].lower())
                else:
                    self.assertIn(CTA_URL, out["copy"])

    def test_bio_platforms_strip_the_url_but_keep_the_offer(self):
        for platform in ("instagram", "tiktok"):
            with self.subTest(platform=platform):
                out = hero.adapt_for_platform("Body.", platform, cta=CTA_URL)
                self.assertNotIn("https://", out["copy"])
                self.assertIn("link in bio", out["copy"].lower())
                self.assertEqual(out["cta_mechanism"], "bio-link")

    def test_url_only_cta_on_a_bio_platform_routes_plainly(self):
        out = hero.adapt_for_platform("Body.", "instagram", cta="https://example.com/x")
        self.assertEqual(out["cta_rendered"], "Link in bio.")

    def test_comment_keyword_replaces_bio_routing(self):
        out = hero.adapt_for_platform("Body.", "tiktok", cta=CTA_URL, cta_keyword="AUDIT")
        self.assertEqual(out["cta_mechanism"], "comment-keyword")
        self.assertIn('Comment "AUDIT"', out["copy"])
        self.assertNotIn("link in bio", out["copy"].lower())

    def test_keyword_is_ignored_where_links_work(self):
        out = hero.adapt_for_platform("Body.", "linkedin", cta=CTA_URL, cta_keyword="AUDIT")
        self.assertEqual(out["cta_mechanism"], "direct-link")
        self.assertIn(CTA_URL, out["copy"])
        self.assertNotIn("AUDIT", out["copy"])

    def test_no_cta_adds_nothing(self):
        out = hero.adapt_for_platform("Body.", "instagram")
        self.assertIsNone(out["cta_rendered"])
        self.assertIsNone(out["cta_mechanism"])
        self.assertEqual(out["copy"], "Body.")

    def test_room_for_the_cta_is_reserved_before_the_cut(self):
        long_body = "A sentence that fills space. " * 40
        for platform in ("x", "bluesky", "threads", "pinterest"):
            with self.subTest(platform=platform):
                out = hero.adapt_for_platform(long_body, platform, cta="Read it here: https://example.com/p")
                self.assertTrue(out["within_limit"], out["char_count"])
                self.assertIn("example.com", out["copy"])

    def test_a_cta_that_cannot_fit_is_reported_not_hidden(self):
        out = hero.adapt_for_platform("Body.", "x", cta="Read: https://example.com/" + "p" * 300)
        self.assertFalse(out["within_limit"])

    def test_render_cta_tidies_the_offer(self):
        self.assertEqual(hero.render_cta("Download the guide — https://a.b/c", hero.PLATFORM_LIMITS["instagram"]),
                         "Download the guide — link in bio.")
        self.assertIsNone(hero.render_cta("", hero.PLATFORM_LIMITS["x"]))


class TestHashtagsAndPlacement(unittest.TestCase):
    def test_hashtags_are_capped_in_the_order_given(self):
        tags = ["#a", "#b", "#c", "#d", "#e", "#f", "#g"]
        self.assertEqual(hero.adapt_for_platform("Hi.", "x", tags)["hashtags"], "#a #b")
        self.assertEqual(hero.adapt_for_platform("Hi.", "linkedin", tags)["hashtags"], "#a #b #c #d #e")
        self.assertEqual(hero.adapt_for_platform("Hi.", "bluesky", tags)["hashtags"], "#a #b")

    def test_instagram_hashtags_go_to_the_first_comment(self):
        out = hero.adapt_for_platform("Hi.", "instagram", ["#a", "#b"])
        self.assertEqual(out["hashtags"], "")
        self.assertEqual(out["first_comment"], "#a #b")
        self.assertEqual(out["hashtag_placement"], "first_comment")
        self.assertNotIn("#a", out["copy"])

    def test_other_platforms_leave_first_comment_empty(self):
        for platform in NINE:
            if platform != "instagram":
                with self.subTest(platform=platform):
                    self.assertIsNone(hero.adapt_for_platform("Hi.", platform, ["#a"])["first_comment"])

    def test_placement_labels(self):
        self.assertEqual(hero.adapt_for_platform("Hi.", "bluesky", ["#a"])["hashtag_placement"], "tag_facets")
        self.assertEqual(hero.adapt_for_platform("Hi.", "x", ["#a"])["hashtag_placement"], "inline")

    def test_char_count_excludes_hashtags(self):
        out = hero.adapt_for_platform("Hi.", "x", ["#a", "#b"])
        self.assertEqual(out["char_count"], len("Hi."))


class TestPlatformBehaviour(unittest.TestCase):
    def test_facebook_is_cut_at_its_working_preference_not_its_limit(self):
        out = hero.adapt_for_platform("A sentence that fills space. " * 40, "facebook")
        self.assertLessEqual(out["char_count"], 500)
        self.assertEqual(out["char_limit"], 63206)

    def test_linkedin_reports_the_fold_preview(self):
        out = hero.adapt_for_platform("x" * 400, "linkedin")
        self.assertEqual(out["fold_at"], 140)
        self.assertEqual(out["hook_visible"], "x" * 140)

    def test_platforms_without_a_fold_preview_the_first_100_characters(self):
        out = hero.adapt_for_platform("y" * 150, "threads")
        self.assertIsNone(out["fold_at"])
        self.assertEqual(out["hook_visible"], "y" * 100)

    def test_unknown_platform_is_an_error_dict(self):
        self.assertEqual(hero.adapt_for_platform("Hi.", "myspace"), {"error": "Unknown platform: myspace"})

    def test_result_has_the_documented_keys(self):
        out = hero.adapt_for_platform("Hi.", "x", ["#a"], "Go: https://example.com")
        self.assertEqual(list(out), ["platform", "copy", "char_count", "char_limit", "within_limit",
                                     "cta_mechanism", "cta_rendered", "fold_at", "hook_visible",
                                     "hashtags", "hashtag_placement", "first_comment"])


class TestBilingual(unittest.TestCase):
    def test_no_secondary_language_returns_the_primary_only(self):
        self.assertEqual(hero.generate_bilingual("Hi.", "x"),
                         {"primary": "Hi.", "secondary": None, "mode": "separate_posts"})

    def test_secondary_is_a_loud_placeholder_not_a_translation(self):
        out = hero.generate_bilingual("Hi.", "x", "en", "hi", "bilingual_single_post")
        self.assertEqual(out["secondary"], "[TRANSLATE TO hi]: Hi.")
        self.assertEqual((out["primary_lang"], out["secondary_lang"], out["mode"]),
                         ("en", "hi", "bilingual_single_post"))
        self.assertIn("--check", out["note"])
        for gone in ("MCP", "Claude"):
            self.assertNotIn(gone, out["note"])


class TestCheck(unittest.TestCase):
    def test_boundary_is_inclusive(self):
        self.assertTrue(hero.check_copy("a" * 280, "x")["within_limit"])
        self.assertFalse(hero.check_copy("a" * 281, "x")["within_limit"])

    def test_counts_plain_characters_like_the_adapter_does(self):
        text = "Café ☕ नमस्ते 😀"
        self.assertEqual(hero.check_copy(text, "x")["char_count"], len(text))

    def test_hashtag_counting(self):
        text = "Launch #1 with #Growth and #SaaS2026, in C# and page#top and #_ and #2026"
        out = hero.check_copy(text, "x")
        self.assertEqual(out["hashtags_in_text"], 2)
        self.assertTrue(out["hashtags_within_limit"])
        self.assertFalse(hero.check_copy("#a #b #c", "x")["hashtags_within_limit"])

    def test_unicode_hashtags_are_counted(self):
        self.assertEqual(hero.check_copy("#नमस्ते #café", "x")["hashtags_in_text"], 2)

    def test_facebook_reports_its_working_preference(self):
        out = hero.check_copy("a" * 600, "facebook")
        self.assertTrue(out["within_limit"])
        self.assertFalse(out["within_optimal"])
        self.assertEqual(out["optimal_limit"], 500)
        self.assertIsNone(hero.check_copy("a", "x")["within_optimal"])

    def test_unknown_platform(self):
        self.assertEqual(hero.check_copy("Hi", "myspace"), {"error": "Unknown platform: myspace"})


class TestCommandLine(unittest.TestCase):
    def test_single_platform_prints_that_platforms_object(self):
        code, out, _ = run_cli(["--text", "Body.", "--platform", "instagram", "--cta", CTA_URL,
                                "--cta-keyword", "AUDIT", "--hashtags", "#a", "#b"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), hero.adapt_for_platform("Body.", "instagram", ["#a", "#b"], CTA_URL, "AUDIT"))

    def test_hashtags_come_before_campaign_hashtags(self):
        code, out, _ = run_cli(["--text", "Body.", "--platform", "linkedin",
                                "--hashtags", "#brand", "--campaign-hashtags", "#launch"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["hashtags"], "#brand #launch")

    def test_several_platforms_are_keyed_and_each_matches_a_single_run(self):
        code, out, _ = run_cli(["--text", "Body.", "--platform", "x", "linkedin", "--cta", CTA_URL,
                                "--hashtags", "#a"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(list(data), ["platforms"])
        self.assertEqual(list(data["platforms"]), ["x", "linkedin"])
        for name in ("x", "linkedin"):
            self.assertEqual(data["platforms"][name], hero.adapt_for_platform("Body.", name, ["#a"], CTA_URL))

    def test_all_expands_to_every_platform_once(self):
        code, out, _ = run_cli(["--text", "Body.", "--platform", "x", "all"])
        self.assertEqual(code, 0)
        # "x" was named explicitly and is also part of "all": it appears once.
        self.assertEqual(list(json.loads(out)["platforms"]), ["x"] + [n for n in NINE if n != "x"])

    def test_text_file_matches_text_and_drops_the_trailing_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "post.txt"
            f.write_bytes("Body line one.\n\nBody line two.\n".encode("utf-8"))
            code, out, _ = run_cli(["--text-file", str(f), "--platform", "x"], cwd=tmp)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), hero.adapt_for_platform("Body line one.\n\nBody line two.", "x"))

    def test_crlf_files_are_read_with_single_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "post.txt"
            f.write_bytes(b"One.\r\n\r\nTwo.\r\n")
            code, out, _ = run_cli(["--text-file", str(f), "--platform", "x"], cwd=tmp)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["copy"], "One.\n\nTwo.")

    def test_stdin(self):
        code, out, _ = run_cli(["--text-file", "-", "--platform", "x"], stdin="Café 😀 नमस्ते.\n".encode("utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["copy"], "Café 😀 नमस्ते.")

    def test_non_ascii_survives_the_round_trip(self):
        text = "世界 😀 नमस्ते. Second sentence."
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "post.txt"
            f.write_bytes(text.encode("utf-8"))
            code, out, _ = run_cli(["--text-file", str(f), "--platform", "threads"], cwd=tmp)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["copy"], text)

    def test_missing_file_is_an_error_not_a_traceback(self):
        code, out, err = run_cli(["--text-file", str(ROOT / "definitely-not-here.txt"), "--platform", "x"])
        self.assertEqual(code, 1)
        self.assertIn("error", json.loads(out))
        self.assertNotIn("Traceback", err)

    def test_unknown_platform_exits_1_with_the_adapter_message(self):
        code, out, err = run_cli(["--text", "Body.", "--platform", "twitter"])
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["error"], "Unknown platform: twitter")
        self.assertIn("x", data["recovery"])
        self.assertNotIn("Traceback", err)

    def test_one_unknown_platform_fails_the_run_but_not_the_others(self):
        code, out, _ = run_cli(["--text", "Body.", "--platform", "x", "twitter"])
        self.assertEqual(code, 1)
        data = json.loads(out)["platforms"]
        self.assertIn("copy", data["x"])
        self.assertIn("error", data["twitter"])

    def test_bad_command_lines_exit_2(self):
        for args in ([], ["--text", "Body."], ["--platform", "x"],
                     ["--text", "a", "--text-file", "b", "--platform", "x"],
                     ["--check", "--text", "a", "--platform", "x", "--cta", "Go"],
                     ["--text", "", "--platform", "x"]):
            with self.subTest(args=args):
                code, _, err = run_cli(args)
                self.assertEqual(code, 2)
                self.assertNotIn("Traceback", err)

    def test_empty_file_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "post.txt"
            f.write_bytes(b"\n")
            code, _, _ = run_cli(["--text-file", str(f), "--platform", "x"], cwd=tmp)
            self.assertEqual(code, 2)

    def test_bilingual_block_per_platform(self):
        code, out, _ = run_cli(["--text", "Body.", "--platform", "x", "linkedin", "--secondary-lang", "hi",
                                "--primary-lang", "en", "--bilingual-mode", "language_per_platform"])
        self.assertEqual(code, 0)
        for name, block in json.loads(out)["platforms"].items():
            with self.subTest(platform=name):
                self.assertEqual(block["bilingual"]["secondary"], "[TRANSLATE TO hi]: Body.")
                self.assertEqual(block["bilingual"]["mode"], "language_per_platform")

    def test_check_mode_measures_without_adding_anything(self):
        code, out, _ = run_cli(["--check", "--text", "Hello #one #two #three", "--platform", "x", "bluesky"])
        self.assertEqual(code, 0)
        data = json.loads(out)["platforms"]
        self.assertEqual(data["x"], hero.check_copy("Hello #one #two #three", "x"))
        self.assertFalse(data["x"]["hashtags_within_limit"])
        self.assertTrue(data["x"]["within_limit"])
        self.assertNotIn("copy", data["x"])

    def test_list_platforms_prints_the_limits_the_script_reads(self):
        code, out, _ = run_cli(["--list-platforms"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), hero.PLATFORM_LIMITS)

    def test_sources_prints_the_provenance(self):
        code, out, _ = run_cli(["--sources"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(list(data), NINE)
        for name, entry in data.items():
            self.assertEqual(set(entry), {"source", "checked", "confirmed", "differs", "unsourced", "notes"})
        self.assertEqual(data["x"]["source"], "https://docs.x.com/fundamentals/counting-characters")
        self.assertEqual(data["tiktok"]["source"], UNSOURCED)

    def test_skill_folder_is_relocatable(self):
        # platforms.json is found relative to the script, not the working directory,
        # so the skill works wherever an agent client copies it.
        with tempfile.TemporaryDirectory() as tmp:
            moved = Path(tmp) / "elsewhere" / "social-copy-adapter"
            shutil.copytree(SKILL, moved, ignore=shutil.ignore_patterns("__pycache__"))
            code, out, _ = run_cli(["--text", "Body.", "--platform", "x"], cwd=tmp,
                                   script=moved / "scripts" / "adapt_copy.py")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), hero.adapt_for_platform("Body.", "x"))

    def test_the_limits_really_are_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            moved = Path(tmp) / "social-copy-adapter"
            shutil.copytree(SKILL, moved, ignore=shutil.ignore_patterns("__pycache__"))
            data = json.loads(read(moved / "platforms.json"))
            data["platforms"]["x"]["limits"]["char_limit"] = 60
            del data["platforms"]["facebook"]["limits"]["optimal_limit"]
            (moved / "platforms.json").write_text(json.dumps(data), encoding="utf-8")
            script = moved / "scripts" / "adapt_copy.py"
            code, out, _ = run_cli(["--text", "First sentence is short. " + "More words follow. " * 10,
                                    "--platform", "x"], script=script)
            self.assertEqual(code, 0)
            result = json.loads(out)
            self.assertEqual(result["char_limit"], 60)
            self.assertLessEqual(result["char_count"], 60)
            code, out, _ = run_cli(["--text", "A sentence that fills space. " * 40, "--platform", "facebook"],
                                   script=script)
            self.assertGreater(json.loads(out)["char_count"], 500)

    def test_a_broken_table_is_an_error_not_a_traceback(self):
        for label, broken in (("not json", "{nope"),
                              ("no platforms", json.dumps({"platforms": {}})),
                              ("bad limit", json.dumps({"platforms": {"x": {"limits": {"char_limit": "280"}}}}))):
            with self.subTest(case=label):
                with tempfile.TemporaryDirectory() as tmp:
                    moved = Path(tmp) / "social-copy-adapter"
                    shutil.copytree(SKILL, moved, ignore=shutil.ignore_patterns("__pycache__"))
                    (moved / "platforms.json").write_text(broken, encoding="utf-8")
                    code, out, err = run_cli(["--text", "Body.", "--platform", "x"],
                                             script=moved / "scripts" / "adapt_copy.py")
                    self.assertEqual(code, 1)
                    self.assertIn("platforms.json", json.loads(out)["error"])
                    self.assertNotIn("Traceback", err)


# ---------------------------------------------------------------------------
# 3. Self-containment, framing, craft rules
# ---------------------------------------------------------------------------

# Things that exist in the SocialForge plugin and not in this repository.
PLUGIN_ONLY = [
    r"socialforge:", r"/socialforge", r"CLAUDE_PLUGIN_ROOT", r"CLAUDE_PLUGIN_DATA", r"PLUGIN_DATA",
    r"brand[- ]?profile", r"brand[- ]?config", r"compliance[-_]rules", r"compliance_check",
    r"(?<!social-)copy-adapter", r"adapt-copy", r"quality-reviewer", r"compose-creative", r"c2pa[-_]sign",
    r"monthly", r"pipeline", r"calendar", r"production/copy", r"asset-index", r"workspace",
    r"new-month", r"full-pipeline", r"finalize",
]

FRAMING = [
    (r"never posts", "never posts anything"),
    (r"no claim about reach", "makes no claim about reach"),
    (r"watermark", "no watermark detection or removal"),
]

MARKERS = ("here's the thing", "the thing is,", "here's the kicker", "here's where it gets interesting",
           "that's the part that got me", "which is exactly the problem", "let that sink in", "read that again")

EVASION = ("zero-width", "homoglyph", "watermark removal", "remove the watermark", "strip the watermark",
           "bypass the detector", "evade detection", "pass as human", "discourse fracture")


def frontmatter(text):
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    assert m, "SKILL.md must open with a --- frontmatter block"
    fields = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if km:
            fields[km.group(1)] = km.group(2).strip()
    return fields, text[m.end():]


def table_rows(text, header_start):
    """Cells of each data row of the markdown table whose header row starts with header_start."""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(header_start))
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


class TestSkillHygiene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = read(SKILL_MD)
        cls.fm, cls.body = frontmatter(cls.raw)
        cls.data = json.loads(read(PLATFORMS))["platforms"]

    def test_frontmatter(self):
        self.assertEqual(self.fm["name"], "social-copy-adapter")
        self.assertEqual(self.fm["name"], SKILL.name)  # must match the folder
        self.assertRegex(self.fm["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertEqual(self.fm["license"], "MIT")
        desc = self.fm["description"]
        self.assertTrue(desc.startswith('"') and desc.endswith('"'), "quote the description")
        desc = json.loads(desc)  # a double-quoted YAML scalar is valid JSON here
        self.assertTrue(0 < len(desc) <= 1024, len(desc))
        low = desc.lower()
        for needle in ("use when", "cta", "hashtag", "character limit"):
            self.assertIn(needle, low)
        for platform in ("linkedin", "instagram", "x", "bluesky"):
            self.assertIn(platform, low)

    def test_no_triggers_field(self):
        head = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", self.raw, re.S).group(1)
        self.assertNotIn("triggers", {k.lower() for k in self.fm})
        self.assertIsNone(re.search(r"(?im)^triggers\s*:", head))

    def test_description_does_not_claim_detection_or_bypass_or_outcomes(self):
        low = json.loads(self.fm["description"]).lower()
        for banned in ("bypass", "undetect", "evade", "beat ", "viral", "boost", "guarantee", "higher engagement"):
            self.assertNotIn(banned, low)

    def test_every_file_skill_md_points_at_exists(self):
        refs = set(re.findall(r"(?<![\w/.-])((?:scripts|references)/[\w./-]+)", self.body))
        refs |= set(re.findall(r"(?<![\w/.-])(platforms\.json)", self.body))
        self.assertIn("scripts/adapt_copy.py", refs)
        self.assertIn("platforms.json", refs)
        for ref in sorted(refs):
            with self.subTest(ref=ref):
                self.assertTrue((SKILL / ref.rstrip(".,")).exists(), ref)

    def test_no_plugin_only_references(self):
        # The closing credit names the project and links it once; take it out, then
        # nothing else may point at the plugin's commands, agents, files or workflow.
        body = re.sub(r"(?m)^Part of SocialForge.*$", "", self.raw)
        for pattern in PLUGIN_ONLY:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, body, re.I), f"SKILL.md mentions plugin-only thing: {pattern}")

    def test_one_closing_credit_with_the_project_link(self):
        lines = [l for l in self.raw.splitlines() if l.startswith("Part of SocialForge")]
        self.assertEqual(len(lines), 1)
        self.assertIn("https://github.com/indranilbanerjee/socialforge", lines[0])

    def test_no_vendor_model_or_price_content_and_no_org_name(self):
        for name, text in (("SKILL.md", self.raw), ("README.md", read(README))):
            with self.subTest(file=name):
                self.assertIsNone(re.search(r"\$\s?\d", text))
                self.assertIsNone(re.search(
                    r"(?i)\b(claude|gpt|gemini|veo|kling|sora|imagen|llama|mistral)[-\s]?\d", text))

    def test_nothing_in_the_repository_names_the_source_organisation(self):
        needle = "tech" + "shu"
        for path in ROOT.rglob("*"):
            if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts:
                with self.subTest(file=path.relative_to(ROOT).as_posix()):
                    self.assertNotIn(needle, path.read_text(encoding="utf-8", errors="replace").lower())

    def test_script_is_stdlib_only_and_offline(self):
        src = read(SCRIPT)
        tree = ast.parse(src)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, {"__future__", "argparse", "json", "re", "sys", "pathlib"})
        for needle in ("os.environ", "getenv", "Path.home", "CLAUDE_PLUGIN", "workspace", "brand-config",
                       "registry", "api_key", "urlopen", "socket"):
            self.assertNotIn(needle, src, f"script mentions {needle}")

    def test_framing_sentence_in_skill_md_and_readme(self):
        for label, text in (("SKILL.md", self.body), ("README.md", read(README))):
            flat = " ".join(text.split())
            for pattern, what in FRAMING:
                with self.subTest(file=label, claim=what):
                    self.assertRegex(flat, re.compile(pattern, re.I))

    def test_skill_md_has_the_sections_a_single_agent_needs(self):
        for heading in ("## The split", "## What you need", "## Ground rules", "## Method",
                        "## Craft rules", "## Running the script", "## What the script does not do",
                        "## What this is not"):
            self.assertIn(heading, self.body)

    def test_platform_table_matches_the_data(self):
        rows = table_rows(self.body, "| Platform | Tone |")
        names = {"LinkedIn": "linkedin", "Instagram": "instagram", "X": "x", "Facebook": "facebook",
                 "YouTube": "youtube", "TikTok": "tiktok", "Pinterest": "pinterest",
                 "Threads": "threads", "Bluesky": "bluesky"}
        self.assertEqual([r[0] for r in rows], list(names))
        for cells in rows:
            key = names[cells[0]]
            limits = self.data[key]["limits"]
            with self.subTest(platform=key):
                self.assertEqual(int(re.match(r"[\d,]+", cells[2]).group(0).replace(",", "")), limits["char_limit"])
                if "fold_at" in limits:
                    self.assertIn(str(limits["fold_at"]), cells[2])
                if "optimal_limit" in limits:
                    self.assertIn(str(limits["optimal_limit"]), cells[2])
                self.assertEqual(int(cells[3].split("/")[1]), limits["hashtag_limit"])
                placement = limits.get("hashtag_placement", "inline")
                expected = {"first_comment": "first comment", "tag_facets": "tag facets", "inline": None}[placement]
                if expected:
                    self.assertEqual(cells[4], expected)
                else:
                    self.assertIn(cells[4], {"inline", "end of post"})
                if limits["link"] == "bio":
                    self.assertIn("link in bio", cells[5])
                else:
                    self.assertEqual(cells[5], "direct link")

    def test_caption_craft_rules_survive(self):
        low = self.body.lower()
        for marker in MARKERS:
            self.assertIn(marker, low, f"SKILL.md must name {marker!r} as forbidden")
        # The markers appear only inside a prohibition.
        start = low.index("**no significance markers.**")
        paragraph = low[start:low.index("\n\n", start)]
        self.assertIn("never write", paragraph)
        self.assertIn("Approvals went from 14 days to 31", self.body)
        for phrase in ("honestly", "never two in one sentence", "no ai-tell scanner",
                       "no document structure to measure", "writing rule, not a scan"):
            self.assertIn(phrase, low)

    def test_the_pairing_rule_is_present(self):
        low = " ".join(self.body.lower().split())
        for phrase in ("the pairing rule", "do different jobs and never echo each other",
                       "stops the scroll", "pays it off"):
            self.assertIn(phrase, low)

    def test_ai_disclosure_is_platform_native_and_honest(self):
        low = " ".join(self.body.lower().split())
        for phrase in ("platform's own label", "human authorship", "current policy"):
            self.assertIn(phrase, low)

    def test_no_evasion_vocabulary_anywhere(self):
        for name, text in (("SKILL.md", self.raw), ("README.md", read(README)), ("script", read(SCRIPT))):
            low = text.lower()
            self.assertEqual([t for t in EVASION if t in low], [], name)


# ---------------------------------------------------------------------------
# 4. The README
# ---------------------------------------------------------------------------

class TestRepoFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(README)

    def test_readme_basics(self):
        self.assertGreaterEqual(len(self.text.split()), 200)
        self.assertIn("npx skills add indranilbanerjee/socialforge-copy-adapter", self.text)
        self.assertIn("skills/social-copy-adapter", self.text)
        self.assertIn("## Part of SocialForge", self.text)

    def test_exactly_one_link_back_to_socialforge(self):
        links = re.findall(r"https://github\.com/indranilbanerjee/socialforge(?![-\w])", self.text)
        self.assertEqual(len(links), 1, links)
        self.assertIn("[SocialForge](https://github.com/indranilbanerjee/socialforge)", self.text)

    def test_license_and_gitignore(self):
        lic = read(ROOT / "LICENSE")
        self.assertIn("MIT License", lic)
        self.assertIn("Copyright (c) 2026 Indranil Banerjee", lic)
        self.assertTrue((ROOT / ".gitignore").is_file())
        self.assertIn("MIT", self.text)

    def test_readme_example_is_a_real_run(self):
        post = re.search(r"```text\n(.*?)\n```", self.text, re.S)
        command = re.search(r"```bash\n(python skills/.*?)\n```", self.text, re.S)
        output = re.search(r"```json\n(.*?)\n```", self.text, re.S)
        self.assertTrue(post and command and output, "README needs a ```text post, a ```bash command and a ```json output")
        argv = shlex.split(command.group(1).replace(chr(92) + chr(10), " "))
        self.assertEqual(argv[0], "python")
        self.assertEqual(argv[1], "skills/social-copy-adapter/scripts/adapt_copy.py")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "post.txt").write_bytes(post.group(1).encode("utf-8"))
            code, out, _ = run_cli(argv[2:], cwd=tmp)
        self.assertEqual(code, 0)
        # Windows prints CRLF; the README holds LF. Content must match exactly.
        printed = out.replace("\r\n", "\n").rstrip("\n")
        self.assertEqual(printed, output.group(1), "the README output is not what the command prints")

    def test_readme_limits_table_matches_the_data(self):
        data = json.loads(read(PLATFORMS))["platforms"]
        section = self.text.split("## The limits are data")[1].split("\n## ")[0]
        names = {"LinkedIn": "linkedin", "Instagram": "instagram", "X": "x", "Facebook": "facebook",
                 "YouTube": "youtube", "TikTok": "tiktok", "Pinterest": "pinterest",
                 "Threads": "threads", "Bluesky": "bluesky"}
        rows = {m.group(1): (m.group(2), m.group(3)) for m in
                re.finditer(r"(?m)^\| ([A-Za-z]+) \| ([\d,]+) \| (.+) \|$", section)}
        self.assertEqual(list(rows), list(names))
        for label, (number, status) in rows.items():
            entry = data[names[label]]
            with self.subTest(platform=label):
                self.assertEqual(int(number.replace(",", "")), entry["limits"]["char_limit"])
                if "char_limit" in entry["confirmed"]:
                    self.assertTrue(status.startswith("confirmed"), status)
                elif "char_limit" in entry["differs"]:
                    self.assertTrue(status.startswith("differs"), status)
                else:
                    self.assertTrue(status.startswith("unsourced"), status)


# ---------------------------------------------------------------------------
# 5. Parity with SocialForge (skipped when it is not alongside)
# ---------------------------------------------------------------------------

def _function(path, name):
    tree = ast.parse(read(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {path}")


def _assignment(path, name):
    tree = ast.parse(read(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node
    raise AssertionError(f"{name} not found in {path}")


def _code_dump(node, mask_prefix=None):
    """ast.dump with docstrings removed: logic must match, prose may not.
    mask_prefix blanks any string constant that starts with it (the one sentence
    that was deliberately reworded)."""
    node = copy.deepcopy(node)
    for n in ast.walk(node):
        if isinstance(n, ast.FunctionDef) and n.body:
            first = n.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                n.body = n.body[1:] or [ast.Pass()]
    if mask_prefix:
        for n in ast.walk(node):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith(mask_prefix):
                n.value = "<MASKED>"
    return ast.dump(node)


def _random_cases(count, seed=20261004):
    """Seeded cases that lean on the boundaries: texts a few characters either
    side of a platform's working limit, with and without a CTA of every shape."""
    rng = random.Random(seed)
    words = ["growth", "the", "checklist", "dashboard", "Café", "नमस्ते", "😀", "https://example.com/p",
             "14", "steps", "we", "cut", "it", "?", "!", "."]
    terminators = [". ", "! ", "? ", ", ", " ", "\n\n", ". "]
    platforms = list(hero.PLATFORM_LIMITS)
    for _ in range(count):
        platform = rng.choice(platforms)
        spec = hero.PLATFORM_LIMITS[platform]
        base = spec.get("optimal_limit", spec["char_limit"])
        target = max(1, min(base, 6000) + rng.randint(-40, 80))
        parts = []
        while sum(len(p) for p in parts) < target:
            sentence = " ".join(rng.choice(words) for _ in range(rng.randint(1, 12)))
            parts.append(sentence + rng.choice(terminators))
        text = "".join(parts)[:target + rng.randint(-3, 3)]
        cta = rng.choice(CTAS)
        keyword = rng.choice(KEYWORDS)
        tags = rng.choice(HASHTAG_LISTS)
        yield text, platform, tags, cta, keyword


@unittest.skipUnless(HAVE_SF, "SocialForge not found alongside this repo (../../SocialForge)")
class TestParityWithSocialForge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sf = load_module("sf_adapt_copy", SF_SCRIPT)

    def test_platform_limits_are_identical(self):
        self.assertEqual(hero.PLATFORM_LIMITS, self.sf.PLATFORM_LIMITS)
        self.assertEqual(list(hero.PLATFORM_LIMITS), list(self.sf.PLATFORM_LIMITS))
        for name in hero.PLATFORM_LIMITS:
            self.assertEqual(list(hero.PLATFORM_LIMITS[name]), list(self.sf.PLATFORM_LIMITS[name]), name)

    def test_adapt_for_platform_on_the_full_grid(self):
        mismatches, total = [], 0
        for tname, text in TEXTS.items():
            for platform in list(hero.PLATFORM_LIMITS) + ["myspace"]:
                for cta in CTAS:
                    for keyword in KEYWORDS:
                        for tags in HASHTAG_LISTS:
                            total += 1
                            mine = hero.adapt_for_platform(text, platform, tags, cta, cta_keyword=keyword)
                            theirs = self.sf.adapt_for_platform(text, platform, tags, cta, cta_keyword=keyword)
                            if json.dumps(mine) != json.dumps(theirs):
                                mismatches.append((tname, platform, cta, keyword, tags))
        self.assertGreater(total, 5000)
        self.assertEqual(mismatches[:3], [], f"{len(mismatches)} of {total} cases differ")

    def test_adapt_for_platform_on_seeded_random_cases(self):
        mismatches, total = [], 0
        for text, platform, tags, cta, keyword in _random_cases(4000):
            total += 1
            mine = hero.adapt_for_platform(text, platform, tags, cta, cta_keyword=keyword)
            theirs = self.sf.adapt_for_platform(text, platform, tags, cta, cta_keyword=keyword)
            if json.dumps(mine) != json.dumps(theirs):
                mismatches.append((platform, len(text), cta, keyword))
        self.assertEqual(total, 4000)
        self.assertEqual(mismatches[:3], [], f"{len(mismatches)} of {total} random cases differ")

    def test_lengths_straddling_every_limit(self):
        for platform, spec in hero.PLATFORM_LIMITS.items():
            base = min(spec.get("optimal_limit", spec["char_limit"]), 6000)
            for n in range(max(0, base - 6), base + 7):
                for text in ("a" * n, ("Sentence number one. " * 400)[:n]):
                    for cta in (None, CTA_URL):
                        with self.subTest(platform=platform, n=n, cta=bool(cta)):
                            self.assertEqual(hero.adapt_for_platform(text, platform, None, cta),
                                             self.sf.adapt_for_platform(text, platform, None, cta))

    def test_truncate_smart_matches_for_many_limits(self):
        rng = random.Random(7)
        corpus = list(TEXTS.values()) + ["Hi. " + "word " * 30, "A! B? C. " * 20]
        for text in corpus:
            for limit in list(range(1, 80)) + [rng.randint(80, 3000) for _ in range(20)]:
                self.assertEqual(hero.truncate_smart(text, limit), self.sf.truncate_smart(text, limit),
                                 (text[:20], limit))

    def test_render_cta_matches_for_every_spec(self):
        for platform, spec in hero.PLATFORM_LIMITS.items():
            for cta in CTAS:
                for keyword in KEYWORDS:
                    with self.subTest(platform=platform):
                        self.assertEqual(hero.render_cta(cta, spec, keyword), self.sf.render_cta(cta, spec, keyword))

    def test_generate_bilingual_differs_only_in_its_note(self):
        for secondary in (None, "hi", "de"):
            for mode in ("separate_posts", "bilingual_single_post", "language_per_platform"):
                mine = hero.generate_bilingual("Hi there.", "x", "en", secondary, mode)
                theirs = self.sf.generate_bilingual("Hi there.", "x", "en", secondary, mode)
                self.assertEqual(list(mine), list(theirs))
                if secondary:
                    self.assertNotEqual(mine.pop("note"), theirs.pop("note"))
                self.assertEqual(mine, theirs)

    def test_adaptation_code_is_the_same_code(self):
        for name in ("truncate_smart", "render_cta", "adapt_for_platform"):
            with self.subTest(function=name):
                self.assertEqual(_code_dump(_function(SCRIPT, name)), _code_dump(_function(SF_SCRIPT, name)))
        self.assertEqual(ast.dump(_assignment(SCRIPT, "_URL_RE")), ast.dump(_assignment(SF_SCRIPT, "_URL_RE")))
        # generate_bilingual: the same code once the one reworded sentence is masked.
        prefix = "Secondary copy requires translation."
        self.assertEqual(_code_dump(_function(SCRIPT, "generate_bilingual"), prefix),
                         _code_dump(_function(SF_SCRIPT, "generate_bilingual"), prefix))

    def _both(self, sf_args, hero_args=None):
        c_sf, o_sf, _ = run_cli(sf_args, script=SF_SCRIPT)
        c_h, o_h, _ = run_cli(hero_args if hero_args is not None else sf_args)
        return (c_sf, json.loads(o_sf)), (c_h, json.loads(o_h))

    def test_cli_list_platforms_is_identical(self):
        (c1, sf_out), (c2, h_out) = self._both(["--list-platforms"])
        self.assertEqual((c1, c2), (0, 0))
        self.assertEqual(sf_out, h_out)

    def test_cli_single_platform_runs_are_identical(self):
        text = "Deliverability improved this quarter. We moved to dedicated sending domains! Did it help? " * 8
        cases = []
        for platform in hero.PLATFORM_LIMITS:
            cases.append(["--text", text, "--platform", platform])
            cases.append(["--text", text, "--platform", platform, "--cta", CTA_URL,
                          "--campaign-hashtags", "#a", "#b", "#c", "#d", "#e", "#f"])
            cases.append(["--text", "Short body.", "--platform", platform, "--cta", "Join us — https://example.com/j",
                          "--cta-keyword", "JOIN"])
        for args in cases:
            with self.subTest(args=args[2:4] + args[4:6]):
                (c1, sf_out), (c2, h_out) = self._both(args)
                self.assertEqual((c1, c2), (0, 0))
                self.assertEqual(sf_out, h_out)

    def test_cli_hashtags_flag_matches_the_originals_campaign_hashtags(self):
        sf_args = ["--text", "Body.", "--platform", "linkedin", "--campaign-hashtags", "#brand", "#launch"]
        hero_args = ["--text", "Body.", "--platform", "linkedin", "--hashtags", "#brand", "--campaign-hashtags", "#launch"]
        (c1, sf_out), (c2, h_out) = self._both(sf_args, hero_args)
        self.assertEqual((c1, c2), (0, 0))
        self.assertEqual(sf_out, h_out)

    def test_cli_bilingual_runs_differ_only_in_the_note(self):
        for mode in ("separate_posts", "bilingual_single_post", "language_per_platform"):
            args = ["--text", "Body copy here.", "--platform", "x", "--secondary-lang", "hi", "--bilingual-mode", mode]
            (c1, sf_out), (c2, h_out) = self._both(args)
            self.assertEqual((c1, c2), (0, 0))
            self.assertNotEqual(sf_out["bilingual"].pop("note"), h_out["bilingual"].pop("note"))
            self.assertEqual(sf_out, h_out)

    def test_cli_unknown_platform_same_message_but_hero_exits_1(self):
        (_, sf_out), (c2, h_out) = self._both(["--text", "Body.", "--platform", "myspace"])
        self.assertEqual(c2, 1)  # the one deliberate CLI difference: a failure is not exit 0
        for key, value in sf_out.items():
            self.assertEqual(h_out[key], value)


# ---------------------------------------------------------------------------
# 6. A stand-alone clone passes
# ---------------------------------------------------------------------------

@unittest.skipIf(NESTED, "already inside the stand-alone clone run")
class TestStandaloneClone(unittest.TestCase):
    def test_suite_passes_from_a_copy_with_no_socialforge_beside_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "a" / "b" / "socialforge-copy-adapter"
            shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
            self.assertFalse((dest / ".." / ".." / "SocialForge").exists())
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", COPY_ADAPTER_NESTED_RUN="1")
            env.pop("SOCIALFORGE_DIR", None)
            proc = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
                                  cwd=dest, capture_output=True, env=env)
            out = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
            self.assertEqual(proc.returncode, 0, out[-3000:])
            skipped = re.search(r"skipped=(\d+)", out)
            self.assertTrue(skipped and int(skipped.group(1)) > 0, "parity tests should have skipped:\n" + out[-500:])


if __name__ == "__main__":
    unittest.main()
