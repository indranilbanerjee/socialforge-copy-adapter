# socialforge-copy-adapter

One skill: adapt one piece of social copy for each platform you post to, with a small offline script that measures every variant against the platform's limit, turns your call to action into the right mechanism per platform, and keeps hashtags where they belong.

This skill rewrites a writer's post for each platform and measures the result with a deterministic script; it never posts, schedules or fetches anything, it makes no claim about reach or engagement, and it neither detects nor removes watermarks.

It is the copy adapter from SocialForge, pulled out as a single Agent Skill that runs on any post with no pipeline around it.

## What it does

- Adapts one post into native variants for **LinkedIn, Instagram, X, Facebook, YouTube, TikTok, Pinterest, Threads and Bluesky**: tone, structure, hook, and the character limit for each.
- Treats the **CTA as a mechanism, not a string**. A direct link where links work; on Instagram and TikTok the URL is dropped and the reader is routed by a comment keyword or "link in bio". The CTA is never silently discarded, and room for it is reserved before the copy is cut.
- Keeps **hashtags in their place**: capped per platform, and on Instagram returned separately for the first comment.
- Structures a **bilingual** second variant and a **cross-post set**, with the translation and the final check left explicit rather than faked.
- Keeps the **caption craft rules** that make short copy good: no "here's the thing" significance markers, at most one soft adverb, and the pairing rule (on-image text and the caption do different jobs and never echo each other).
- Handles **AI-disclosure** the platform-native way: use the platform's own label where it has one, add a visible line only when the writer's rule calls for it, never imply human authorship of AI-made material.
- Ships `adapt_copy.py`, a **standard-library-only** script. No network, no model calls, no credentials, no dependencies. Its limits live in `platforms.json`, which records where each number came from.

## Install

With [skills.sh](https://skills.sh):

```bash
npx skills add indranilbanerjee/socialforge-copy-adapter
```

Or copy it by hand. The skill is the folder `skills/social-copy-adapter`; keep the folder name `social-copy-adapter`, because the Agent Skills standard requires it to match the skill's `name`.

```bash
git clone https://github.com/indranilbanerjee/socialforge-copy-adapter
# Claude Code, for all your projects:
cp -r socialforge-copy-adapter/skills/social-copy-adapter ~/.claude/skills/social-copy-adapter
# or for one project:
cp -r socialforge-copy-adapter/skills/social-copy-adapter .claude/skills/social-copy-adapter
```

Any other Agent Skills client: copy `skills/social-copy-adapter` into that client's skills directory. The script needs Python 3.9 or newer; the writing method works without it.

## Use

Ask in plain language: "adapt this for LinkedIn, Instagram and X", "write the X version of this post", "cross-post this announcement", "fit this caption to 280 characters", "turn this link CTA into a link-in-bio CTA". Give it the CTA, your hashtags in priority order, the voice, any on-image text, and any banned phrases or disclaimers; it only uses what you give it. You get back the variants plus a short report of what was measured and what could not be checked.

## The script

Save the post as `post.txt`:

```text
We cut our onboarding checklist from 14 steps to 6. New teams now reach their first dashboard in one sitting, and the median time to get there fell from 3 days to 4 hours. The biggest change was removing every step that only existed to collect information we already had. If your setup guide has a step nobody can explain, start there.
```

then run:

```bash
python skills/social-copy-adapter/scripts/adapt_copy.py --text-file post.txt --platform x instagram linkedin \
    --cta "Get the checklist: https://example.com/checklist" --cta-keyword CHECKLIST \
    --hashtags "#Onboarding" "#SaaS" "#CustomerSuccess"
```

It prints (a real run, unedited):

```json
{
  "platforms": {
    "x": {
      "platform": "x",
      "copy": "We cut our onboarding checklist from 14 steps to 6. New teams now reach their first dashboard in one sitting, and the median time to get there fell from 3 days to 4 hours.\n\nGet the checklist: https://example.com/checklist",
      "char_count": 221,
      "char_limit": 280,
      "within_limit": true,
      "cta_mechanism": "direct-link",
      "cta_rendered": "Get the checklist: https://example.com/checklist",
      "fold_at": null,
      "hook_visible": "We cut our onboarding checklist from 14 steps to 6. New teams now reach their first dashboard in one",
      "hashtags": "#Onboarding #SaaS",
      "hashtag_placement": "inline",
      "first_comment": null
    },
    "instagram": {
      "platform": "instagram",
      "copy": "We cut our onboarding checklist from 14 steps to 6. New teams now reach their first dashboard in one sitting, and the median time to get there fell from 3 days to 4 hours. The biggest change was removing every step that only existed to collect information we already had. If your setup guide has a step nobody can explain, start there.\n\nComment \"CHECKLIST\" and we'll send you the link.",
      "char_count": 385,
      "char_limit": 2200,
      "within_limit": true,
      "cta_mechanism": "comment-keyword",
      "cta_rendered": "Comment \"CHECKLIST\" and we'll send you the link.",
      "fold_at": null,
      "hook_visible": "We cut our onboarding checklist from 14 steps to 6. New teams now reach their first dashboard in one",
      "hashtags": "",
      "hashtag_placement": "first_comment",
      "first_comment": "#Onboarding #SaaS #CustomerSuccess"
    },
    "linkedin": {
      "platform": "linkedin",
      "copy": "We cut our onboarding checklist from 14 steps to 6. New teams now reach their first dashboard in one sitting, and the median time to get there fell from 3 days to 4 hours. The biggest change was removing every step that only existed to collect information we already had. If your setup guide has a step nobody can explain, start there.\n\nGet the checklist: https://example.com/checklist",
      "char_count": 385,
      "char_limit": 3000,
      "within_limit": true,
      "cta_mechanism": "direct-link",
      "cta_rendered": "Get the checklist: https://example.com/checklist",
      "fold_at": 140,
      "hook_visible": "We cut our onboarding checklist from 14 steps to 6. New teams now reach their first dashboard in one sitting, and the median time to get the",
      "hashtags": "#Onboarding #SaaS #CustomerSuccess",
      "hashtag_placement": "inline",
      "first_comment": null
    }
  }
}
```

What happened, field by field:

- **X.** The post did not fit once the CTA's room was reserved, so the script cut at the last sentence that fit and kept the CTA as a direct link. It also kept two of the three hashtags, X's cap in the limits table, and dropped `#CustomerSuccess` without comment. That cut is mechanical. In real use you rewrite the X version yourself, run it again, and ship the script's cut only if you accept it.
- **Instagram.** The URL is gone from the caption, replaced by the comment-keyword ask, and all three hashtags are in `first_comment`.
- **LinkedIn.** Untouched. `hook_visible` is the text before the assumed "see more" fold.

`--check` measures finished text and changes nothing (`--check --text-file final.txt --platform x bluesky`); it is how you verify a translation or a post you assembled by hand. The script also reads from stdin (`--text-file -`). `SKILL.md` explains every field, the full method, and the places where the script's measure differs from a platform's.

## What is code and what is judgment

| The script does | You (or your agent) do |
|---|---|
| Counts characters against the limit | Rewrites for tone, structure and hook |
| Reserves room for the CTA, then cuts mechanically | Decides what to tighten; a rewrite beats a cut |
| Renders the CTA mechanism per platform | Chooses the offer and the wording |
| Caps hashtags and says where they go | Chooses which hashtags matter |
| Structures the bilingual variant | Writes and reviews the translation |
| Measures finished text with `--check` | Claims, compliance, disclosure |

## The limits are data, and not all of them are confirmed

`skills/social-copy-adapter/platforms.json` carries each platform's numbers with a `source`, a `checked` date and a record of what the source confirms. SocialForge's data had no sources, so on 2026-10-04 each limit was compared against the platform's own documentation where a readable page could be found. The character limit, by platform:

| Platform | Limit | Status |
|---|---|---|
| LinkedIn | 3,000 | confirmed (LinkedIn help page) |
| Instagram | 2,200 | unsourced (no readable primary page) |
| X | 280 | confirmed (X docs); X counts URLs as 23 and emoji and CJK as 2 each |
| Facebook | 63,206 | unsourced (script cuts at 500 anyway) |
| YouTube | 5,000 | confirmed (YouTube help page) |
| TikTok | 2,200 | unsourced; third-party pages report 4,000, unconfirmed here |
| Pinterest | 500 | differs: Pinterest's page says 800; the 500 is kept as a conservative cap |
| Threads | 500 | confirmed (Threads API docs) |
| Bluesky | 300 | confirmed (300 graphemes, from the post lexicon) |

Hashtag caps and the "see more" position are working values with no source anywhere. Run `python skills/social-copy-adapter/scripts/adapt_copy.py --sources` for the full record, and edit a number in `limits` if you know better. Platforms change their limits without notice; check the platform's current documentation before relying on any number for something that matters.

## What this is not

- **Not a publisher or scheduler.** It writes nothing to any platform and holds no credentials.
- **Not a compliance or legal check.** It cannot know a platform's or a market's current rules. Disclosure and claim-substantiation duties stay with the writer.
- **Not an AI detector, and no watermark handling.** It does not judge who or what wrote a text, never tunes copy to beat any detector, and does not detect, strip or defeat watermarks or content credentials.
- **No performance claims.** Nothing here says a variant will reach, engage or convert better.
- **Not a translator.** The bilingual `secondary` is a placeholder until the translation replaces it.

## Tests

```bash
python -m pytest tests -q
```

The tests cover the script (limits, mechanical cut, CTA mechanisms, hashtag caps and placement, bilingual structure, `--check`, the command line), the limits table (every entry sourced or marked unsourced, dated, and consistent with its own confirmed/differs/unsourced lists), the skill (frontmatter, links, no references to anything this repository does not have, the platform table matching the data), and that the example above is a real run. When this repository sits next to a SocialForge checkout (`../../SocialForge`, or set `SOCIALFORGE_DIR`), they also prove **parity**: the hero and SocialForge's `adapt_copy.py` return identical results across a grid of platforms, texts, CTAs and hashtag lists plus thousands of seeded random cases, the adaptation functions are the same code, and the command lines agree. Without a SocialForge checkout those tests skip, and a test runs the whole suite from a copy of this repository with no sibling to prove a standalone clone passes.

## Part of SocialForge

This is the copy-adaptation core of [SocialForge](https://github.com/indranilbanerjee/socialforge), a plugin for the wider social production workflow. Everything you need to adapt copy is in this folder.

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Indranil Banerjee.
