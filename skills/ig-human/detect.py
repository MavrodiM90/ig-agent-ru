#!/usr/bin/env python3
"""
detect.py - a five-check panel that scores how machine-written a draft looks.

What this is:  five local heuristics modelled on the signals public AI
detectors actually measure - sentence-length variation, concreteness, stock
vocabulary, typographic fingerprint, and voice. Every score is computed on
your machine from the text alone. Nothing is uploaded.

What this is NOT:  GPTZero, Originality, Copyleaks, Winston or Turnitin.
It does not call their APIs and it cannot promise their verdict. It catches
the things they all key on, which is why fixing them tends to move their
numbers too - but the only honest claim is the one on this line.

Each check returns a HUMAN score from 0 to 100. Higher is better.

Usage
  python3 detect.py draft.txt                 # on Windows: py detect.py ...
  python3 detect.py draft.txt --json
  python3 detect.py before.txt after.txt      # compare two drafts
  python3 detect.py script.txt --script       # a beat-split Reel script

Russian edition: Russian text is detected by its Cyrillic share. Russian has
no contractions, so VOICE counts colloquial particles instead ("ну", "вот",
"короче"); FINGERPRINT does not count the em dash, en dash or «ёлочки",
which are correct Russian typography; SLOP DENSITY adds the Russian phrases
and the inflecting stock words in `ru_flags`.
"""

import argparse
import json
import os
import re
import statistics
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
LEX = os.path.join(HERE, "slop.json")

SENT_RE = re.compile(r"[^.!?\n]+[.!?]*")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё']+")
CYR_RE = re.compile(r"[А-Яа-яЁё]")
LAT_RE = re.compile(r"[A-Za-z]")
CONTRACTIONS = re.compile(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", re.IGNORECASE)
PRONOUNS = re.compile(r"\b(i|me|my|mine|we|us|our|you|your"
                      r"|я|меня|мне|мой|моя|мои|мы|нас|нам|наш\w*|ты|тебя|тебе|твой|твоя|твои"
                      r"|вы|вас|вам|ваш\w*)\b", re.IGNORECASE)
# Spoken Russian is full of small particles; generated Russian has almost none.
RU_COLLOQUIAL = re.compile(r"\b(?:ну|вот|же|ведь|короче|типа|прям|реально|кстати|блин|вообще"
                           r"|ага|щас|ваще|ч[её]|норм|кароч|чисто|походу|кажется|честно)\b",
                           re.IGNORECASE)
NUMBERS = re.compile(r"\b\d[\d,.]*%?\b|[$₽]\d")
PROPER = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b", re.MULTILINE)


def is_russian(text):
    return len(CYR_RE.findall(text)) > len(LAT_RE.findall(text))


# Emoji glued with ZWJ or tag characters (👨‍👩‍👧, 🏳️‍🌈, 🏴 flags) come from
# phone keyboards. They are not a machine tell and must survive (upstream #29).
PICTO = "\U0001F000-\U0001FAFF☀-➿"
EMOJI_SEQ_RE = re.compile(
    rf"[{PICTO}][️\U0001F3FB-\U0001F3FF]?(?:‍[{PICTO}][️\U0001F3FB-\U0001F3FF]?)+"
    r"|\U0001F3F4[\U000E0020-\U000E007E]+\U000E007F")


def lex_pattern(find):
    """Literal lexicon entry -> regex. Russian "е" also matches "ё"."""
    find = find.replace("ё", "е")
    body = re.escape(find).replace(r"\ ", r"\s+").replace("е", "[её]")
    # \b only on edges that are word characters: "thoughts?" must still match (upstream #29).
    left = r"\b" if re.match(r"\w", find) else ""
    right = r"\b" if re.search(r"\w$", find) else ""
    return re.compile(left + body + right, re.IGNORECASE)


def clamp(n):
    return max(0.0, min(100.0, n))


def scale(value, human, machine):
    """Map value onto 0-100 where `human` -> 100 and `machine` -> 0."""
    if human == machine:
        return 50.0
    return clamp((value - machine) / (human - machine) * 100)


def sentences(text):
    return [s.strip() for s in SENT_RE.findall(text) if len(s.split()) > 2]


def words(text):
    return WORD_RE.findall(text)


def check_burstiness(text):
    """Humans vary sentence length hard. Models write even."""
    lens = [len(s.split()) for s in sentences(text)]
    if len(lens) < 4:
        return 50.0, "too short to judge"
    mean = statistics.mean(lens)
    cv = statistics.pstdev(lens) / mean if mean else 0
    score = scale(cv, human=0.70, machine=0.22)
    return score, f"variation {cv:.2f} across {len(lens)} sentences (want 0.55+)"


def check_specificity(text):
    """Numbers, names and concrete nouns. Slop is abstract."""
    w = words(text)
    if len(w) < 25:
        return 50.0, "too short to judge"
    per100 = 100 / len(w)
    hits = len(NUMBERS.findall(text)) + len(set(PROPER.findall(text)))
    density = hits * per100
    score = scale(density, human=6.0, machine=0.5)
    return score, f"{hits} concrete markers, {density:.1f} per 100 words (want 4+)"


def check_slop(text, lex):
    """Stock vocabulary density against the lexicon."""
    w = words(text)
    if not w:
        return 50.0, "empty"
    hits, found = 0, []
    for entry in lex["words"] + lex["phrases"]:
        n = len(lex_pattern(entry["find"]).findall(text))
        if n:
            hits += n
            found.append(entry["find"])
    for entry in lex.get("ru_flags", []):
        n = len(re.compile(r"\b" + entry["regex"], re.IGNORECASE).findall(text))
        if n:
            hits += n
            found.append(entry["name"])
    density = hits * 100 / len(w)
    score = scale(density, human=0.0, machine=4.0)
    detail = f"{hits} stock terms, {density:.1f} per 100 words"
    if found:
        detail += " (" + ", ".join(sorted(found)[:4]) + (", ..." if len(found) > 4 else "") + ")"
    return score, detail


def check_fingerprint(text):
    """Characters a phone keyboard does not produce."""
    in_emoji = sum(1 for m in EMOJI_SEQ_RE.finditer(text) for c in m.group(0)
                   if unicodedata.category(c) == "Cf")
    invisible = sum(1 for c in text if unicodedata.category(c) == "Cf") - in_emoji
    # In Russian the dash is grammar ("Москва — столица"), not a tell.
    em = 0 if is_russian(text) else text.count("—")
    curly = sum(text.count(c) for c in "‘’“”")
    ellip = text.count("…")
    nbsp = sum(text.count(c) for c in "   ")
    total = invisible * 4 + em * 2 + curly + ellip + nbsp
    per1k = total * 1000 / max(len(text), 1)
    score = scale(per1k, human=0.0, machine=12.0)
    detail = (f"{invisible} invisible, {em} em dash, {curly} curly quote, "
              f"{ellip} ellipsis, {nbsp} hard space")
    return score, detail


def check_voice(text, lex):
    """Contractions, person, and the shapes models default to."""
    w = words(text)
    if len(w) < 25:
        return 50.0, "too short to judge"
    per100 = 100 / len(w)
    ru = is_russian(text)
    spoken_re = RU_COLLOQUIAL if ru else CONTRACTIONS
    contractions = len(spoken_re.findall(text)) * per100
    person = len(PRONOUNS.findall(text)) * per100
    tells = 0
    names = []
    for s in lex["structures"]:
        try:
            n = len(re.compile(s["regex"], re.MULTILINE).findall(text))
        except re.error:
            continue
        if n:
            tells += n
            names.append(s["id"])
    bullets = [len(b.split()) for b in re.findall(r"(?m)^\s*[-*•]\s+(.+)$", text)]
    uniform = (len(bullets) >= 3 and statistics.pstdev(bullets) < 1.6)
    score = (scale(contractions, human=3.0, machine=0.0) * 0.35
             + scale(person, human=8.0, machine=1.0) * 0.35
             + clamp(100 - tells * 22) * 0.30)
    if uniform:
        score -= 12
        names.append("uniform-bullets")
    detail = (f"{contractions:.1f} {'colloquial particles' if ru else 'contractions'}, "
              f"{person:.1f} personal pronouns "
              f"per 100 words, {tells} structural tell(s)")
    if names:
        detail += " [" + ", ".join(names[:4]) + "]"
    return clamp(score), detail


CHECKS = ["BURSTINESS", "SPECIFICITY", "SLOP DENSITY", "FINGERPRINT", "VOICE"]


def run(text, lex, script=False):
    results = {}
    # A Reel script is cut into beats of 3-11 words on purpose, so sentence
    # length cannot vary the way prose does. --script skips the check (upstream #4).
    results["BURSTINESS"] = ((100.0, "skipped: --script, beats are short by design")
                             if script else check_burstiness(text))
    results["SPECIFICITY"] = check_specificity(text)
    results["SLOP DENSITY"] = check_slop(text, lex)
    results["FINGERPRINT"] = check_fingerprint(text)
    results["VOICE"] = check_voice(text, lex)
    scores = [results[c][0] for c in CHECKS if not (script and c == "BURSTINESS")]
    # The weakest check drags the verdict: a detector only needs one signal.
    overall = statistics.mean(scores) * 0.6 + min(scores) * 0.4
    verdict = "PASS" if overall >= 70 and min(scores) >= 55 else (
        "REVIEW" if overall >= 50 else "FLAGGED")
    return results, overall, verdict


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def render(results, overall, verdict, label=None, out=sys.stdout):
    title = "AI DETECTION PANEL" + (f"  -  {label}" if label else "")
    print("\n" + title, file=out)
    print("=" * max(len(title), 62), file=out)
    for name in CHECKS:
        score, detail = results[name]
        print(f"  {name:<13} {bar(score)} {score:5.1f}", file=out)
        print(f"  {'':<13} {detail}", file=out)
    print("-" * 62, file=out)
    print(f"  {'HUMAN SCORE':<13} {bar(overall)} {overall:5.1f}   {verdict}", file=out)
    if verdict != "PASS":
        weakest = min(CHECKS, key=lambda c: results[c][0])
        print(f"\n  Weakest signal: {weakest}. Fix that first.", file=out)
    print("", file=out)


def utf8_stdio():
    """Windows consoles default to a legacy code page and print Cyrillic as junk."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description="Score how machine-written a draft looks.")
    ap.add_argument("input", nargs="?", default="-", help="file, or - for stdin")
    ap.add_argument("compare", nargs="?", help="second file, to show before/after")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--script", action="store_true",
                    help="text is a beat-split Reel script: skip BURSTINESS")
    ap.add_argument("--lexicon", default=LEX)
    args = ap.parse_args()

    lex = json.load(open(args.lexicon, encoding="utf-8"))
    read = lambda p: sys.stdin.read() if p == "-" else open(p, encoding="utf-8").read()

    targets = [(args.input, read(args.input))]
    if args.compare:
        targets.append((args.compare, read(args.compare)))

    payload = []
    for name, text in targets:
        results, overall, verdict = run(text, lex, args.script)
        payload.append({
            "source": name,
            "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
            "human_score": round(overall, 1),
            "verdict": verdict,
        })

    if args.json:
        print(json.dumps(payload if args.compare else payload[0], indent=2))
        return

    for (name, text), p in zip(targets, payload):
        results, overall, verdict = run(text, lex, args.script)
        render(results, overall, verdict, label=os.path.basename(name) if args.compare else None)
    if args.compare:
        a, b = payload
        delta = b["human_score"] - a["human_score"]
        print(f"  {a['human_score']:.1f} {a['verdict']}  ->  "
              f"{b['human_score']:.1f} {b['verdict']}   ({delta:+.1f})\n")

    sys.exit(0 if payload[-1]["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
