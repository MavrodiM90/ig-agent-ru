#!/usr/bin/env python3
"""
hookscore.py - score the first line of a Reel on the five things strong hooks
have in common, and rank a batch of them against each other.

Russian edition: every check understands Russian as well as English. The
language is detected per hook (Cyrillic share), and Russian hooks are scored
against Russian vocabulary: stems instead of exact words, because Russian
inflects ("потерял", "потеряла", "потеряли" are one stake), spoken numbers
and rubles, Russian greetings and preambles, and a slower speaking rate.

What this is:  five local heuristics, computed on your machine from the text
alone. They measure properties that hooks which hold attention tend to share -
a length you can say in under three seconds, a concrete marker, something at stake,
the payload at the front rather than the back, and a viewer to aim it at.

What this is NOT:  a view predictor. The original was tested against 74 real
English short-form hooks: separating a real hook from a deliberately bad one
it does well (AUC 0.83), separating a good creator's hits from that same
creator's misses it barely does at all (AUC 0.56). The Russian vocabulary has
not been validated against real view data at all. Trust the retention graph
over this script.

Each check returns 0 to 100. Higher is better.

Usage (on Windows use `py` instead of `python3`)
  python3 hookscore.py hooks.txt              # one hook per line, ranked
  python3 hookscore.py --hook "Я потерял 18 000 рублей из-за одной строчки."
  python3 hookscore.py hooks.txt --json
"""

import argparse
import json
import re
import statistics
import sys

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9$%₽'’-]+")
CYR_RE = re.compile(r"[А-Яа-яЁё]")
LAT_RE = re.compile(r"[A-Za-z]")
NUMBER_RE = re.compile(
    r"[$₽]\s?\d[\d,]*(?:\.\d+)?"                     # money, whole
    r"|\b\d[\d,]*(?:\.\d+)?\s?"                      # a figure, with or
    r"(?:%|k\b|x\b|hrs?\b|hours?\b|mins?\b|minutes?\b"  # without a unit
    r"|days?\b|weeks?\b|months?\b|years?\b|₽)?",
    re.IGNORECASE)
# A capital after a full stop starts a sentence, it is not a name (upstream #4).
PROPER_RE = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-ZА-ЯЁ][a-zа-яё]{2,}(?:[A-Z]\w*)?\b")  # CapCut, ComfyUI
HASHTAG_RE = re.compile(r"(?:^|\s)#\w+")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")

# Spoken hooks say their numbers out loud. "Zero dollars" and "twenty grand"
# are as concrete as "$0" and "$20,000", and counting only digits missed them.
# "one" and "first" are deliberately absent: they are filler far more often
# than they are a quantity.
SPOKEN_NUMBERS = {
    "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "fifteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
    "billion", "dozen", "half", "twice", "triple",
}
MONEY_WORDS = {
    "dollars", "dollar", "bucks", "grand", "percent", "cents",
    "millionaire", "billionaire", "revenue", "profit", "salary", "rent",
}

# Words that put something on the line. A hook with none of these is a
# statement; a hook with one is a reason to keep watching.
STAKES = {
    "stop", "never", "wrong", "mistake", "mistakes", "lost", "lose", "losing",
    "cost", "costs", "broke", "broken", "failed", "failure", "fail", "nobody",
    "no", "not", "don't", "dont", "doesn't", "didn't", "can't", "won't",
    "quit", "quitting", "fired", "deleted", "delete", "killed", "kills", "kill",
    "replaced", "replaces", "cut", "beat", "free", "paid", "charged", "hired",
    "saved", "first",
    "banned", "illegal", "worst", "hate", "hated", "wasted", "waste", "scam",
    "lie", "lied", "lying", "truth", "secret", "hidden", "stole", "stolen",
    "before", "until", "instead", "but", "except", "unless", "problem",
    "risk", "danger", "warning", "regret", "wish", "should", "shouldn't",
    "still", "already", "only", "without", "versus", "vs", "actually",
}

# Openers that spend the first second saying nothing.
WEAK_OPENERS = [
    "so", "ok", "okay", "hey", "hi", "hello", "guys", "yo", "alright",
    "welcome", "today", "basically", "honestly", "look", "listen", "um",
    "just", "let", "lets", "let's", "i wanted", "i want", "one of",
    "have you", "did you", "do you", "are you", "in this", "in today",
    "the thing", "a lot", "there is", "there are", "this is", "it is",
    "as a", "when it", "if you've", "you know",
]

# Imperatives that earn the front position.
IMPERATIVES = {
    "stop", "steal", "copy", "delete", "try", "watch", "read", "save",
    "use", "build", "make", "write", "send", "take", "start", "quit",
    "never", "always", "don't", "dont", "do", "put", "run", "check",
}

# --- Russian. Tokens are lower-cased with "ё" folded to "е" before matching.
# Exact words go in sets; inflecting words go in stem tuples (prefix match).
RU_SPOKEN_NUMBERS = {
    "ноль", "нуля", "два", "две", "двух", "три", "трех", "пять", "шесть",
    "семь", "восемь", "девять", "десять", "сто", "сорок", "двести", "триста",
    "полтора", "полторы", "дважды", "трижды", "вдвое", "втрое",
}
RU_NUMBER_STEMS = (
    "четыр", "пятнадцат", "двадцат", "тридцат", "пятьдесят", "шестьдесят",
    "семьдесят", "восемьдесят", "девяност", "тысяч", "миллион", "миллиард",
    "половин", "десятк", "сотн", "сотен", "дюжин",
)
RU_MONEY_STEMS = (
    "рубл", "руб", "бакс", "доллар", "евро", "процент", "зарплат", "выручк",
    "прибыл", "аренд", "косар", "тыщ", "лям", "₽",
)
RU_STAKES = {
    "не", "нет", "ни", "но", "зато", "хотя", "против", "vs", "без", "вместо",
    "кроме", "пока", "уже", "только", "всего", "даже", "зря", "стоп", "хватит",
    "нельзя", "бан", "ложь", "вру", "врет", "врешь", "врут", "врал", "врала",
    "врали", "наврал", "соврал", "обман",
}
RU_STAKE_STEMS = (
    "потер", "теря", "лишил", "лишит", "стоил", "стоит", "обошл", "обошел",
    "провал", "ошиб", "никто", "никогда", "ничего", "брос", "уволи", "удали", "удаля",
    "слил", "слом", "взлом", "забан", "запрет", "незакон", "худш", "ненави",
    "впуст", "развод", "обман", "правд", "секрет", "скрыв", "скрыт", "украл",
    "краж", "проблем", "риск", "опасн", "предупре", "жале", "пожалел", "бесплат",
    "заплат", "платн", "сэконом", "эконом", "замен", "убил", "убива", "побед",
    "проиграл", "перв", "впервые", "сократ", "должн", "реальн", "налож", "штраф",
    "умер", "мертв", "переплат", "сгорел", "сжег", "сжёг", "перестань", "прекрат",
)
RU_WEAK_OPENERS = [
    "итак", "так", "ну", "ок", "окей", "привет", "всем привет", "здравствуйте",
    "ребят", "ребята", "друзья", "хей", "эй", "йоу", "салют", "сегодня",
    "короче", "в общем", "вообщем", "слушайте", "давайте", "давай", "я хочу",
    "хочу рассказать", "хочу поделиться", "в этом", "в сегодняшнем",
    "это видео", "это ролик", "вот", "знаете", "а вы", "вы знали",
    "есть такая", "как известно", "один из", "одна из", "многие", "кстати",
    "добрый", "доброе", "всем", "честно", "просто",
]
RU_IMPERATIVES = {
    "хватит", "перестань", "перестаньте", "прекрати", "прекратите", "стоп",
    "укради", "кради", "забирай", "забери", "скопируй", "копируй", "удали",
    "удалите", "попробуй", "попробуйте", "смотри", "гляди", "глянь",
    "сохрани", "сохраните", "используй", "используйте", "собери", "сделай",
    "сделайте", "напиши", "напишите", "отправь", "отправьте", "возьми",
    "начни", "начните", "брось", "бросай", "никогда", "всегда", "делай",
    "делайте", "поставь", "ставь", "запусти", "проверь", "проверьте",
    "включи", "выключи", "открой", "купи", "не",
}
RU_YOU_RE = re.compile(r"\b(?:ты|тебя|тебе|тобой|тво[йяеи]\w*|вы|вас|вам|вами|ваш\w*)\b")
RU_ME_RE = re.compile(r"\b(?:я|меня|мне|мной|мо[йяеи]\w*|мы|нас|нам|нами|наш\w*)\b")

DEALBREAKERS = [
    (re.compile(r"(?i)^\s*(?:stop scrolling|don'?t scroll)"),
     "Opens with \"stop scrolling\". Asking for attention proves you have not earned it."),
    (re.compile(r"(?i)\b(?:in (?:this|today'?s) (?:video|reel)|i'?m going to show you|i'?ll show you how)\b"),
     "Video preamble. Delete it and open on the payoff."),
    (re.compile(r"(?i)^\s*(?:hey |hi |what'?s up |welcome )"),
     "Greeting. Nobody came to the feed to be greeted."),
    (re.compile(r"(?i)^\s*(?:стоп,?\s+)?(?:не листай|не пролистывай|не скролль|подожди,? не листай)"),
     "Opens with \"не листай\". Asking for attention proves you have not earned it."),
    (re.compile(r"(?i)\b(?:в этом (?:видео|ролике|рилсе)|в сегодняшнем (?:видео|ролике|рилсе)"
                r"|сегодня (?:я )?(?:вам |тебе )?(?:покажу|расскажу)|я (?:вам |тебе )?(?:сейчас )?(?:покажу|расскажу),? как)"),
     "Video preamble (\"в этом видео\", \"сегодня расскажу\"). Delete it and open on the payoff."),
    (re.compile(r"(?i)^\s*(?:привет|всем привет|здравствуйте|хей|салют|добрый (?:день|вечер)|доброе утро)\b"),
     "Greeting. Nobody came to the feed to be greeted."),
    (HASHTAG_RE,
     "Hashtag in the hook. Hashtags belong at the bottom of the caption, if anywhere."),
    (EMOJI_RE,
     "Emoji in the hook. On-screen text at hook size has room for words or for an emoji, not both."),
]


def clamp(n):
    return max(0.0, min(100.0, n))


def utf8_stdio():
    """Windows consoles default to a legacy code page and print Cyrillic as junk."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def is_russian(text):
    """Cyrillic letters outnumber Latin ones."""
    return len(CYR_RE.findall(text)) > len(LAT_RE.findall(text))


def words(text):
    # "$18,000" and "18 000" are one word when spoken, so one word here too.
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(r"(?<=\d)[   ](?=\d{3}\b)", "", text)
    return WORD_RE.findall(text)


def norm(token):
    return token.lower().replace("ё", "е").strip("'’")


def ru_hit(token, exact, stems=()):
    return token in exact or token.startswith(stems) if stems else token in exact


def opener_hit(opener, weak):
    return opener == weak or opener.startswith(weak + " ")


def check_length(text):
    """A hook has to land before the thumb moves. Roughly two seconds."""
    w = words(text)
    n = len(w)
    ru = is_russian(text)
    # Russian words are longer and spoken slower: ~140 wpm against ~165.
    secs = n / (2.33 if ru else 2.75)
    lo, hi, max_chars = (4, 10, 70) if ru else (5, 12, 60)
    chars = len(text.strip())
    if lo <= n <= hi:
        score = 100.0
    elif n < lo:
        score = clamp(100 - (lo - n) * 20)
    else:
        score = clamp(100 - (n - hi) * 11)
    if chars > max_chars:                # two lines of big on-screen text
        score -= 12
    return clamp(score), f"{n} words, {chars} chars, ~{secs:.1f}s spoken (want {lo}-{hi} words)"


def check_specificity(text):
    """One concrete thing beats three abstract ones."""
    merged = re.sub(r"(?<=\d)[   ](?=\d{3}\b)", "", text)
    nums = [n.strip() for n in NUMBER_RE.findall(merged) if n.strip()]
    propers = set(PROPER_RE.findall(text))
    low = [norm(w) for w in words(text)]
    spoken = [w for w in low if w in SPOKEN_NUMBERS or w in MONEY_WORDS
              or ru_hit(w, RU_SPOKEN_NUMBERS, RU_NUMBER_STEMS + RU_MONEY_STEMS)]
    hits = len(nums) + len(propers) + len(spoken)
    score = 15.0 if hits == 0 else clamp(45 + hits * 30)
    found = ", ".join(nums[:2] + sorted(propers)[:2] + spoken[:2])
    return score, (f"{hits} concrete marker(s)" + (f": {found}" if found else
                   " - no number, no name, nothing checkable"))


def check_stakes(text):
    """Tension, cost, negation. Something the viewer might lose."""
    w = [norm(x) for x in words(text)]
    hits = [x for x in w if x in STAKES or ru_hit(x, RU_STAKES, RU_STAKE_STEMS)]
    markers = sorted(set(hits))
    if re.search(r"[$₽]\s?\d|\d\s?₽|\d[\d\s]*\s?(?:руб|тыс)", text, re.IGNORECASE):
        markers.append("a price")
    n = len(markers)
    score = {0: 20.0, 1: 70.0}.get(n, 100.0)
    detail = f"{n} tension marker(s)" + (f": {', '.join(markers[:4])}" if markers else
                                         " - nothing is at stake in this line")
    return clamp(score), detail


def check_frontload(text):
    """The interesting word cannot be in position nine."""
    w = words(text)
    if not w:
        return 0.0, "empty"
    low = [norm(x) for x in w]
    opener = " ".join(low[:2])
    penalty = 0
    hit_opener = None
    for weak in WEAK_OPENERS + RU_WEAK_OPENERS:
        if opener_hit(opener, weak) or low[0] == weak:
            penalty, hit_opener = 30, weak
            break
    # Names are found in the whole line: PROPER_RE on a lone token can never
    # match, because the token always sits at the start of its string (upstream #29).
    propers = set(PROPER_RE.findall(text))
    payload = None
    for i, token in enumerate(low):
        if (token in STAKES or token in SPOKEN_NUMBERS or token in MONEY_WORDS
                or ru_hit(token, RU_STAKES, RU_STAKE_STEMS)
                or ru_hit(token, RU_SPOKEN_NUMBERS, RU_NUMBER_STEMS + RU_MONEY_STEMS)
                or NUMBER_RE.match(w[i]) or (i and w[i] in propers)):
            payload = i
            break
    if payload is None:
        base = 30.0
        where = "no payload word anywhere in the line"
    elif payload <= 3:
        base = 100.0
        where = f"payload at word {payload + 1}"
    elif payload <= 6:
        base = 70.0
        where = f"payload at word {payload + 1}, could move forward"
    else:
        base = 40.0
        where = f"payload at word {payload + 1}, too late"
    detail = where + (f"; weak opener \"{hit_opener}\"" if hit_opener else "")
    return clamp(base - penalty), detail


def check_address(text):
    """Aimed at one viewer, or floating in the air."""
    low = text.lower().replace("ё", "е")
    w = [norm(x) for x in words(text)]
    if re.search(r"\b(you|your|you're|youre|yourself)\b", low) or RU_YOU_RE.search(low):
        return 100.0, "speaks to the viewer"
    if w and (w[0] in IMPERATIVES or w[0] in RU_IMPERATIVES):
        return 90.0, f"imperative opener (\"{w[0]}\")"
    if re.search(r"\b(i|my|me|we|our)\b", low) or RU_ME_RE.search(low):
        return 70.0, "first person, no viewer named"
    return 35.0, "third person, nobody in the room"


CHECKS = ["LENGTH", "SPECIFICITY", "STAKES", "FRONTLOAD", "ADDRESS"]


def run(text):
    results = {
        "LENGTH": check_length(text),
        "SPECIFICITY": check_specificity(text),
        "STAKES": check_stakes(text),
        "FRONTLOAD": check_frontload(text),
        "ADDRESS": check_address(text),
    }
    flags = [msg for pattern, msg in DEALBREAKERS if pattern.search(text)]
    scores = [results[c][0] for c in CHECKS]
    # The weakest property caps the hook, same logic as detect.py: one bad
    # property is enough for the thumb to keep moving.
    overall = statistics.mean(scores) * 0.6 + min(scores) * 0.4 - len(flags) * 15
    overall = clamp(overall)
    verdict = "STRONG" if overall >= 70 and min(scores) >= 55 and not flags else (
        "OK" if overall >= 50 else "WEAK")
    return results, overall, verdict, flags


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def render_one(text, results, overall, verdict, flags, out=sys.stdout):
    print("\nHOOK SCORE", file=out)
    print("=" * 62, file=out)
    print(f"  \"{text.strip()}\"\n", file=out)
    for name in CHECKS:
        score, detail = results[name]
        print(f"  {name:<13} {bar(score)} {score:5.1f}", file=out)
        print(f"  {'':<13} {detail}", file=out)
    print("-" * 62, file=out)
    print(f"  {'HOOK SCORE':<13} {bar(overall)} {overall:5.1f}   {verdict}", file=out)
    for f in flags:
        print(f"\n  DEALBREAKER  {f}", file=out)
    if verdict != "STRONG":
        weakest = min(CHECKS, key=lambda c: results[c][0])
        print(f"\n  Weakest property: {weakest}. Fix that one and re-run.", file=out)
    print("", file=out)


def render_table(rows, out=sys.stdout):
    print("\nHOOK RANKING\n" + "=" * 78, file=out)
    for i, r in enumerate(rows, 1):
        mark = "->" if i == 1 else "  "
        hook = r["hook"] if len(r["hook"]) <= 62 else r["hook"][:59] + "..."
        print(f"{mark} {r['score']:5.1f} {r['verdict']:<7} {hook}", file=out)
        print(f"        weakest: {r['weakest']} ({r['checks'][r['weakest']]['score']:.0f})", file=out)
        for f in r["flags"]:
            print(f"        dealbreaker: {f}", file=out)
    print("\nShoot the top one. If the top one is under 50, none of these are the hook.\n",
          file=out)


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description="Score a Reel hook on five properties.")
    ap.add_argument("input", nargs="?", default="-", help="file with one hook per line, or -")
    ap.add_argument("--hook", help="score a single hook given on the command line")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.hook:
        lines = [args.hook]
    else:
        raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lines:
        print("nothing to score", file=sys.stderr)
        sys.exit(2)

    payload = []
    for line in lines:
        results, overall, verdict, flags = run(line)
        payload.append({
            "hook": line,
            "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
            "weakest": min(CHECKS, key=lambda c: results[c][0]),
            "flags": flags,
            "score": round(overall, 1),
            "verdict": verdict,
        })

    if args.json:
        print(json.dumps(payload if len(payload) > 1 else payload[0], indent=2, ensure_ascii=False))
        return

    if len(payload) == 1:
        results, overall, verdict, flags = run(lines[0])
        render_one(lines[0], results, overall, verdict, flags)
    else:
        render_table(sorted(payload, key=lambda r: -r["score"]))

    sys.exit(0 if max(p["score"] for p in payload) >= 70 else 1)


if __name__ == "__main__":
    main()
