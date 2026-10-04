---
name: social-copy-adapter
description: "Adapt one piece of social copy into native variants for LinkedIn, Instagram, X, Facebook, YouTube, TikTok, Threads, Bluesky and Pinterest: per-platform tone and structure, character limits measured by a script instead of guessed, hashtag counts and placement (Instagram first comment), the right CTA mechanism (direct link, comment keyword, or link in bio, never dropped), a bilingual second variant and a cross-post set. Ships a stdlib-only script (scripts/adapt_copy.py) and a limits table (platforms.json) that records where each number came from. Use when asked to adapt, shorten, rewrite or cross-post a caption for several platforms, fit copy to a character limit, split hashtags out of a caption, write the LinkedIn, X or Instagram version of a post, or turn a link CTA into a comment-keyword or link-in-bio CTA. Not a scheduler or publisher; it never posts anything."
license: MIT
compatibility: "Needs Python 3.9+ (standard library only) to run the script; the writing method works without it."
metadata:
  author: Indranil Banerjee
  version: "1.0.0"
---

# Social copy adapter

This skill rewrites a writer's post for each platform and measures every variant against a limits table with a small offline script. It never posts, schedules or fetches anything, and it makes no claim about reach or engagement.

## The split

Only one half of this job is a measurement. Keep them apart.

| The script does (`scripts/adapt_copy.py`; same input, same output) | You do (judgment) |
|---|---|
| Counts length the way the platform does (X by weight, the rest by characters) against the limit | Rewrite for each platform's tone, structure and hook |
| Reserves room for the CTA, then cuts mechanically at the last sentence that fits | Decide what to tighten or drop; a rewrite beats a cut |
| Turns the CTA into the platform's mechanism (direct link, comment keyword, link in bio) | Choose the offer and the CTA wording |
| Keeps up to a per-platform number of hashtags, says where they go (Instagram: first comment) and lists the ones it left out | Choose which hashtags matter, and tell the writer which were dropped |
| Structures a bilingual variant with a placeholder | Write the translation |
| `--check`: measures finished text (length, hashtag count) | Claims, compliance, disclosure |

## What you need

- **The source copy** (a file path, or pasted text; save pasted text to a file and pass `--text-file`, which avoids shell quoting trouble).
- **The target platforms.** Nine are in the table: linkedin, instagram, x, facebook, youtube, tiktok, pinterest, threads, bluesky.
- **Ask for these if they would change the copy:**
  - the CTA (wording and URL), and whether a **comment-keyword automation** is actually running for Instagram or TikTok (a keyword nothing answers is a broken promise);
  - hashtags: always-on first, then campaign ones, in priority order;
  - the voice (professional, conversational, witty) and any writing sample;
  - on-image text for the post (overlay, carousel cover, video hook line);
  - the second language, if any, and terms that must not be translated;
  - banned phrases, required disclaimers, regulated-field rules;
  - whether the post's text or media was made with AI, and any disclosure rule the writer follows.

## Ground rules

1. **Never invent a fact to make copy fit or hit harder.** Numbers, names, quotes, dates, prices and claims in every variant come from the source copy or from what the writer told you. A shorter version drops detail; it never adds any.
2. **The CTA is never dropped.** It changes mechanism by platform (below). If it does not fit, shorten the body.
3. **Never count characters by eye.** Run the script. Counting by eye is unreliable, and the limit is the one thing a platform enforces.
4. **A mechanical cut is a last resort.** If the script had to cut your text, tighten the prose and run again. Ship the cut only if the writer accepts it.
5. **Hashtags come from the writer.** Use the supplied list first. If none was given, propose a few relevant ones and label them as suggestions. Never invent a branded hashtag.
6. **Keep what must not change.** Quotes, names, figures, product terms and URLs survive every variant verbatim (and any terms the writer marked do-not-translate).
7. **Say what you could not check.** If no banned-phrase list or disclaimer was supplied, say so in the report; do not call the copy compliant.

## Method

### Step 1. Find the one point

Reduce the source to the single thing a reader should take away and the one action you want. Every variant carries that point; platforms differ in how they get there, not in what is claimed.

### Step 2. Write each variant by hand

One variant per platform, from the table. Tone and shape, not just length: a 3,000-character LinkedIn post is a different piece of writing from a 280-character X post, not the same text trimmed.

| Platform | Tone | Limit (chars) | Hashtags: aim / script cap | Hashtags go | CTA |
|---|---|---|---|---|---|
| LinkedIn | Professional | 3,000 (hook inside the first 140) | 3-5 / 5 | end of post | direct link |
| Instagram | Conversational | 2,200 | 3-5 / 5 | first comment | comment keyword, else link in bio |
| X | Punchy, concise | 280 (counted by weight: emoji and CJK 2, any URL 23) | 1-2 / 2 | inline | direct link |
| Facebook | Casual | 63,206 (script cuts at 500) | 1-3 / 3 | inline | direct link |
| YouTube | Description format | 5,000 | 3-5 / 5 | inline | direct link |
| TikTok | Casual, trend-aware | 2,200 | 3-5 / 10 | inline | comment keyword, else link in bio |
| Pinterest | Search-friendly description | 800 | 5-10 / 20 | inline | direct link |
| Threads | Conversational | 500 | 1 / 1 | inline | direct link |
| Bluesky | Concise, community-first | 300 | 1-2 / 2 | tag facets | direct link |

The numbers live in `platforms.json`, and not all of them are confirmed: run `--sources` before you tell anyone a limit is official. "Aim" is a working range from SocialForge's platform notes, not a platform rule; the script cap is how many hashtags it keeps. The rest come back in `hashtags_dropped`, so a cap never removes a tag without a record.

Write the variant **without** the CTA and without hashtags. The script adds the CTA in the right mechanism and returns the hashtags separately; putting them in the text as well duplicates them.

Emojis follow the voice: professional means few, conversational means moderate. Put the hook where it is seen: the first line on Instagram, the first 140 characters on LinkedIn (`hook_visible` in the output shows what that preview contains; the fold position is a working assumption, not a measured one).

### Step 3. The CTA is a mechanism

Where links work, the CTA is kept exactly as written, URL and all. Where they do not (Instagram, TikTok captions), a pasted URL is dead weight, so the script routes the reader instead:

| Situation | What the script writes | `cta_mechanism` |
|---|---|---|
| Link platform | the CTA, unchanged | `direct-link` |
| Bio platform, comment keyword given | `Comment "KEYWORD" and we'll send you the link.` | `comment-keyword` |
| Bio platform, no keyword | the offer with the URL removed, then ` — link in bio.` | `bio-link` |
| Bio platform, the CTA was only a URL | `Link in bio.` | `bio-link` |
| No CTA given | nothing added | `null` |

A keyword is ignored on link platforms; asking for a comment where the link simply works is cargo cult. When the CTA is a **conversation** (a keyword that opens a DM or a messaging thread): ask for one tiny action, put one offer in the post, and do not promise what the responder cannot answer (price, stock, a delivery date). If the reply is automated, the first message should say so. Messaging platforms have their own opt-in and timing rules; check the current policy before promising a flow.

### Step 4. Run the script

```bash
python <skill-dir>/scripts/adapt_copy.py --text-file post.txt --platform x instagram linkedin \
    --cta "Get the checklist: https://example.com/checklist" --cta-keyword CHECKLIST \
    --hashtags "#Onboarding" "#SaaS"
```

Run it once per distinct variant (each platform gets its own text), or once for several platforms when the text is the same. Read `within_limit`, `cta_mechanism`, `hashtags`, `first_comment` and `hashtags_dropped`, and compare `copy` with what you wrote: if the body was shortened, the script cut it (see rule 4). On X, `char_count` is X's weighted count (`count_method` says `x_weighted`), so it is not the length of `copy`.

For inline platforms the hashtags are a separate string, not part of `copy` or `char_count`. Assemble the final post yourself (`copy`, a blank line, `hashtags`), save it, and measure it:

```bash
python <skill-dir>/scripts/adapt_copy.py --check --text-file final-x.txt --platform x
```

`--check` measures finished text and changes nothing. It is how you verify a translation, a hand-assembled post, or a variant you edited after the first run.

### Step 5. Bilingual

Pass `--secondary-lang <code>` and the script returns a `bilingual` block whose `secondary` is a bracketed placeholder, `[TRANSLATE TO <code>]: ...`, followed by the adapted primary copy. The translation is yours:

- Replace the placeholder entirely. A post that still contains the bracket is not finished.
- Translate meaning and voice, not word for word. Keep URLs, product names, hashtags and any do-not-translate terms as they are. Use translated hashtags only if the writer supplied them.
- The secondary is built from the already-cut primary with its CTA already rendered, and translations change length. Run `--check` on the translated text for the same platform.
- Modes (`--bilingual-mode`, recorded in the output, not enforced): `separate_posts` is one post per language; `bilingual_single_post` puts both languages in one post, so the limit applies to the two together (check the combined text); `language_per_platform` gives each platform one language, as the writer decides.
- For anything high-stakes, say the translation should be reviewed by a native speaker. Do not claim it has been.

### Step 6. Cross-post set

A cross-post is the same point in different shapes, not the same text pasted. Check the set before you hand it over: each variant opens with a platform-native hook; links follow the platform (direct link versus bio versus keyword); hashtag counts and placement follow the table; no variant contains a claim the others lack. Name which platform got which.

### Step 7. Compliance and disclosure

If the writer supplied banned phrases, required disclaimers or regulated-field rules (health, finance, legal), check every variant against them before you finish. A required disclaimer that does not fit is a reason to shorten the copy, never to drop the disclaimer. A banned phrase is rewritten, not disguised. A claim in the source with no source behind it is flagged to the writer, not made punchier. Treat a hard violation as a block and a soft one as a noted warning.

**AI disclosure.** If the post's text or media was made with AI and the writer, the platform or the market requires a label: use the platform's own label or toggle where it has one, and add a plain visible line to the copy only when the writer's rule calls for it (for example, "Image made with AI"). Do not state a particular platform's or country's disclosure rule as fact; those change, so point the writer to the platform's current policy page. Never word a post to imply human authorship of something AI made.

### Step 8. Report

Give the variants, then a short table of what was measured:

```
Post: <name>
  linkedin   847 chars (limit 3000) ok | 4 hashtags (cap 5) | CTA: direct-link
  instagram  1203 chars (limit 2200) ok | 25 hashtags in first comment | CTA: comment-keyword
  x          267 chars (limit 280) ok | 2 hashtags inline | CTA: direct-link
Cut by the script: none | Dropped hashtags (from hashtags_dropped): none | Not checked: banned phrases (none supplied)
```

## Craft rules

**No significance markers.** Never write a line whose only job is to announce that the next line matters: "here's the thing", "the thing is,", "here's the kicker", "here's where it gets interesting", "that's the part that got me", "which is exactly the problem", "let that sink in", "read that again". They read as machine-written to anyone who has scrolled a feed this year, and on a 280-character platform they spend the budget the point needs. Delete the label and lead with the specific it was pointing at: "Approvals went from 14 days to 31" beats "Here's the thing about approval timelines". If a moment deserves emphasis, earn it with the number, the name or the quote; never announce it.

**Soft adverbs.** At most one of honestly, genuinely, truly, literally, actually or basically in a caption, and never two in one sentence. A line that needs force needs a specific, not an adverb.

This is a writing rule, not a scan. There is no AI-tell scanner here on purpose: caption-length copy has no document structure to measure, and per-1000-word metrics are noise at 280 characters. The judgment belongs where the caption is written.

**The pairing rule.** If the post ships with text on the image (an overlay, a carousel cover, a video hook line), the overlay and the caption do different jobs and never echo each other. The overlay stops the scroll: a promise, a number, a tension. The caption pays it off: context, proof and the CTA. When both say the same sentence one is wasted, and it is usually the caption's first line, the one line guaranteed to be visible. Ask for the on-image text; if the caption's first line repeats it, keep the stronger of the two where it is and rewrite the other to do its own job.

**A worked example.** The writer's notes: *onboarding went from 14 steps to 6; median time to first dashboard fell from 3 days to 4 hours; checklist at https://example.com/checklist; the Instagram image carries the overlay "14 steps → 6".*

- **X:** "Onboarding went from 14 steps to 6. Median time to first dashboard: 3 days down to 4 hours." CTA `Get the checklist: https://example.com/checklist` is passed separately and kept as a direct link.
- **Instagram:** the caption opens "Median time to first dashboard fell from 3 days to 4 hours." (the overlay already said 14 steps to 6, so the caption does not repeat it), then one line of context, then the script's CTA: `Comment "CHECKLIST" and we'll send you the link.` The hashtags come back in `first_comment`.

Every figure above is in the notes. Nothing was added.

## Running the script

`<skill-dir>` is the folder that contains this SKILL.md. Use `python3` where `python` is not Python 3.

```bash
python <skill-dir>/scripts/adapt_copy.py --text "Post body." --platform x
python <skill-dir>/scripts/adapt_copy.py --text-file post.txt --platform all --hashtags "#Tag"
python <skill-dir>/scripts/adapt_copy.py --check --text-file final.txt --platform x bluesky
python <skill-dir>/scripts/adapt_copy.py --list-platforms
python <skill-dir>/scripts/adapt_copy.py --sources
```

One platform prints that platform's object; several (or `all`) print `{"platforms": {name: object}}`. `--text-file -` reads stdin. Exit code 0 on success; exit 1 with an `error` key for an unknown platform, an unreadable file or a broken `platforms.json`; exit 2 for a bad command line. It reads only the text you give it and `platforms.json`, runs offline and writes nothing.

| Field | Meaning |
|---|---|
| `copy` | The adapted text: body (cut to fit if it had to be), a blank line, the rendered CTA |
| `char_count`, `char_limit`, `within_limit` | Length of `copy` against the hard limit, counted the way `count_method` says. `false` means over; shorten the CTA or the body |
| `count_method` | `code_points` (plain characters) or, for X, `x_weighted`: emoji and CJK count 2, every URL counts 23 |
| `cta_mechanism`, `cta_rendered` | How the CTA was turned into the platform's mechanism (table in Step 3) |
| `hashtags` | The hashtags to put in the post, joined by spaces, capped per platform. Empty where they go elsewhere |
| `hashtag_placement`, `first_comment` | `inline`, `first_comment` or `tag_facets`; on Instagram the hashtags are in `first_comment` |
| `hashtags_dropped` | The hashtags the platform's cap left out, in the order given; an empty list when none. Tell the writer which they were |
| `fold_at`, `hook_visible` | The assumed "see more" position and the text before it (first 100 characters where none is set) |
| `bilingual` | With `--secondary-lang`: `primary`, `secondary` (a placeholder), `mode`, `note` |

`--check` returns `char_count`, `char_limit`, `within_limit`, `count_method`, `optimal_limit` and `within_optimal` (both `null` unless a platform has a working preference below its limit, as Facebook does), `hashtags_in_text`, `hashtag_limit`, `hashtags_within_limit` and `hook_visible`. It counts a hashtag as a `#` that is not glued to a word and has at least one letter, so `C#`, `page#top` and `#1` are not counted.

**The limits are data.** `platforms.json` holds each platform's numbers and, per platform, a `source`, a `checked` date and three lists: `confirmed` (a primary page says this), `differs` (the page says something else; the number is kept and `notes` explains), and `unsourced`. `also_read` lists further primary pages that were read, each with what it says and the limits key it bears on. A top-level `counting` block records X's weighting rules, with the field names of twitter-text's own configuration. Edit a number in `limits` and the script uses it. When a `source` is the text "SocialForge data, unsourced", this skill has no source for those numbers, except any key an `also_read` entry carries. `--sources` prints all of it, with a `status` for every limit.

## What the script does not do

- **Everything but X is counted in plain characters** (Python `len`). X is counted by weight, from twitter-text's own configuration: the text is normalised to NFC, then most characters weigh 1, emoji and CJK 2, and every URL that starts with `http://`, `https://` or `www.` weighs 23 however long it is. Three differences remain. An emoji sequence (a family emoji, a flag) is weighed code point by code point, so it counts more than X's 2 (the safe direction). A bare domain without `http://`, `https://` or `www.` is counted as plain text although X links it, so a long bare domain counts low. And Bluesky's limit is 300 graphemes where this counts code points, so an emoji sequence can make the count look larger than it is (also the safe direction). Threads counts an emoji as its number of UTF-8 bytes; the script counts it as 1, so it undercounts emoji on Threads and that is not implemented.
- **`char_count` covers `copy` only.** Inline hashtags and the Instagram first comment are separate strings, so assemble the final post and run `--check`.
- **Hashtags past the cap are left out, in the order given, and listed in `hashtags_dropped`.** Put the ones that must survive first, and tell the writer which were dropped.
- **The cut is mechanical.** It breaks at the last sentence end past halfway, or else mid-text with `...`. If the CTA alone nearly fills the limit, almost no body is left and `within_limit` can still be `false`; shorten the CTA.
- **The limits are not all confirmed, and platforms change them.** Run `--sources`. For anything that matters, check the platform's current documentation.
- **It does not translate, rewrite for tone, check banned phrases, or judge a claim.** The bilingual `secondary` is a placeholder, and nothing checks its length until you run `--check`.

## What this is not

- **Not a publisher or scheduler.** It writes nothing to any platform and holds no credentials.
- **Not a compliance or legal check.** It cannot know a platform's or a market's current rules. Disclosure and claim-substantiation duties stay with the writer.
- **Not an AI detector, and no watermark handling.** It does not judge who or what wrote a text, never tunes copy to beat any detector, and does not detect, strip or defeat watermarks or content credentials.
- **No performance claims.** Nothing here says a variant will reach, engage or convert better.
- **Not a brand-voice engine.** It uses the voice notes and samples the writer gives it.

Part of SocialForge, which runs the wider social production workflow: https://github.com/indranilbanerjee/socialforge
