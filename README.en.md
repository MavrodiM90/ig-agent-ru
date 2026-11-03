# ig-agent-ru — Instagram skills for Claude, in Russian

**[Русская версия](README.md)**

A Russian edition of [Jakeschincariol/instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill)
(MIT): 13 Claude skills for Reels scripts with a scored hook, captions with a
linter, carousels, stories, profile review, a weekly plan, comments, DMs,
outlier research and a humanizer.

## Why

Every check in the original is written for the Latin alphabet. On Russian
text the scripts run but return wrong answers: a strong Russian hook scores
45.8 WEAK, a greeting gets no dealbreaker, Russian stock phrases are not
found, Cyrillic hashtags are not counted and a 35-word script is timed as 5
words. This edition makes every script understand Russian and keeps English
results identical where no fix applies (regression-tested against a snapshot
of upstream `d03c56b`).

## Fixes to upstream bugs

It also fixes the bugs reported in upstream issues
[#4](https://github.com/Jakeschincariol/instagram-agent-skill/issues/4),
[#17](https://github.com/Jakeschincariol/instagram-agent-skill/issues/17),
[#29](https://github.com/Jakeschincariol/instagram-agent-skill/issues/29) and
[#44](https://github.com/Jakeschincariol/instagram-agent-skill/issues/44):

- weak-opener check matched prefixes ("yo" hit "your");
- spoken numbers were not concrete in `beats.py`;
- a capital after a full stop counted as a name;
- `swipe.py --out file.md` crashed on a bare filename;
- five hashtags were flagged as a wall;
- new `--script` mode for `detect.py` and `humanize.py`, since a beat-split script cannot reach the BURSTINESS floor;
- ZWJ emoji (👨‍👩‍👧, 🏳️‍🌈) were split and scored as a fingerprint;
- preambles were deleted instead of flagged;
- "Save this for later" was deleted;
- a proper name could never be the FRONTLOAD payload;
- lexicon terms ending in punctuation never matched;
- "Comment below" counted as a keyword ask;
- "Nobody is talking about this" changed meaning;
- `/ig-plan` now asks first whether a plan and an owner already exist;
- `/ig-caption` warns that Unicode "bold" is not searchable text;
- scripts force UTF-8 output, so Windows consoles no longer garble Cyrillic.

Platform facts are updated as of November 2026:

- Reels up to 20 minutes, not recommended to new audiences past 3;
- five-hashtag cap;
- safe zones taken from Meta's Reels ads guide;
- Private Replies API limits for keyword auto-DMs;
- ranking signals as named by Mosseri in January 2025.

## Install

```
/plugin marketplace add MavrodiM90/ig-agent-ru
/plugin install ig-agent-ru@ig-agent-ru
```

or copy `skills/ig-*` into `~/.claude/skills/`. Python 3.9+, standard library
only.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

42 tests, run in CI on Linux, Windows and macOS.

MIT. Credit to Jake Schincariol for the original pack.
