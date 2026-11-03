"""Tests for ig-agent-ru.

Run from the repository root:
  python3 -m unittest discover -s tests -v      (Windows: py -m unittest ...)

Three groups:
  * Russian behaviour - the reason this edition exists;
  * fixes for bugs reported upstream (issue numbers in the test names);
  * English regression against `upstream_snapshot.json`, recorded from
    Jakeschincariol/instagram-agent-skill@d03c56b on inputs none of the fixes
    touch, so the Russian work cannot quietly change English scores.
"""

import importlib.util
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, "skills")
SNAP = json.load(open(os.path.join(ROOT, "tests", "upstream_snapshot.json"), encoding="utf-8"))


def load(folder, name):
    sys.path.insert(0, os.path.join(SKILLS, folder))
    try:
        spec = importlib.util.spec_from_file_location(name, os.path.join(SKILLS, folder, name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


hook = load("ig-reel", "hookscore")
beats = load("ig-reel", "beats")
cap = load("ig-caption", "caption")
hum = load("ig-human", "humanize")
det = load("ig-human", "detect")
swipe = load("ig-viral", "swipe")

with open(os.path.join(SKILLS, "ig-human", "slop.json"), encoding="utf-8") as fh:
    LEX = json.load(fh)
HOOKS_JSON = os.path.join(SKILLS, "ig-reel", "hooks.json")
with open(HOOKS_JSON, encoding="utf-8") as fh:
    HOOKS = json.load(fh)["hooks"]

RU_SLOP = ("В современном мире крайне важно использовать ИИ — это не просто инструмент, "
           "это настоящий прорыв. Давайте погрузимся в эффективный и бесшовный процесс, "
           "который открывает новые горизонты.\n")
RU_HUMAN = ("Ну, я попал. Три вечера мучил экспорт на своём ноутбуке, и первые два файла "
            "полосили так, что небо выглядело как лестница, которую забыли докрасить. "
            "Помог короткий тест. Вот это реально сработало, хотя я уже почти бросил, "
            "полез смотреть платные плагины, прикинул цены и снова вернулся к настройкам, "
            "потому что жалко 2 000 в месяц. Теперь 12 секунд видео — это секунд 20 экспорта.\n")


def checks(analysis):
    return {c["check"]: c["status"] for c in analysis["checks"]}


# --- Russian behaviour -------------------------------------------------------

class HookScoreRussian(unittest.TestCase):
    def test_strong_russian_hook(self):
        _, overall, verdict, _ = hook.run("Я потерял 18 000 рублей из-за одной строчки в договоре.")
        self.assertGreaterEqual(overall, 70)
        self.assertEqual(verdict, "STRONG")

    def test_greeting_and_preamble_are_dealbreakers(self):
        _, overall, verdict, flags = hook.run("Привет, ребята, сегодня расскажу про нейросети")
        self.assertEqual((verdict, len(flags)), ("WEAK", 2))
        self.assertLess(overall, 30)

    def test_ne_listay_is_a_dealbreaker(self):
        self.assertTrue(any("листай" in f for f in hook.run("Не листай, сейчас будет важное")[3]))

    def test_inflected_stakes_count(self):
        for line in ("Она потеряла подписчиков за неделю.", "Мы потеряли 300 рублей."):
            self.assertGreaterEqual(hook.check_stakes(line)[0], 70, line)

    def test_spaced_thousands_are_one_number(self):
        self.assertEqual(len(hook.words("18 000 рублей")), 2)

    def test_russian_address(self):
        self.assertEqual(hook.check_address("Тебе не нужна дорогая камера.")[0], 100.0)
        self.assertEqual(hook.check_address("Хватит снимать бесплатно.")[0], 90.0)
        self.assertEqual(hook.check_address("Я поменял камеру.")[0], 70.0)

    def test_ranking_order(self):
        good = hook.run("Никто не говорит, что первые 30 рилсов должны провалиться.")[1]
        bad = hook.run("Нейросети это интересно")[1]
        self.assertGreater(good, bad + 20)


class BeatsRussian(unittest.TestCase):
    SCRIPT = ("Я потерял 18 000 рублей из-за одной строчки.\n"
              "Это был договор с клиентом на монтаж.\n"
              "В нём не было даты оплаты.\n"
              "Теперь я пишу её первой строкой.\n"
              "Одна строчка, и 18 000 рублей остались бы у меня.\n")

    def test_counts_russian_words_and_time(self):
        a = beats.analyse(self.SCRIPT, wpm=beats.RU_WPM, target=15)
        self.assertEqual(a["total_words"], 35)
        self.assertAlmostEqual(a["total_seconds"], 15.0, delta=0.5)

    def test_language_detected(self):
        self.assertTrue(beats.is_russian(self.SCRIPT))
        self.assertFalse(beats.is_russian("Proposals used to take me five hours."))

    def test_inflected_loop(self):
        a = beats.analyse("Я потерял три тысячи рублей.\nИ это был урок.\nЭти рубли я вернул.\n", 140)
        self.assertTrue(any(n.startswith("Loops") for n in a["notes"]))


class CaptionRussian(unittest.TestCase):
    def test_russian_asks_and_cyrillic_tags(self):
        text = ("Напиши в комментариях СЛОВО, и я пришлю шаблон.\n\n"
                "Я три месяца снимал ролики на телефон.\n\nСохрани, чтобы не потерять.\n\n"
                "#съёмка #рилсы #reels #viral #fyp #explore\n")
        a = cap.analyse(text, keywords=["ролики"])
        self.assertEqual(len(a["hashtags"]), 6)
        self.assertEqual(sorted(a["asks"]), ["comment a keyword", "save this"])
        self.assertEqual(checks(a)["HASHTAGS"], "FAIL")

    def test_keyword_plus_dm_delivery_is_one_ask(self):
        text = ("Напиши ПРЕСЕТ в комментариях, и я пришлю в директ пресет, которым обработал 40 свадеб.\n\n"
                "Обработка одной свадьбы теперь занимает два дня.\n\n#свадебныйфотограф #пресеты\n")
        a = cap.analyse(text, keywords=["свадьбы"])
        self.assertEqual(a["asks"], ["comment a keyword"])
        self.assertEqual(a["verdict"], "READY")

    def test_question_is_not_a_keyword(self):
        a = cap.analyse("Напиши в комментариях, что думаешь про это.\n")
        self.assertEqual(a["asks"], ["answer a question"])

    def test_quoted_keyword(self):
        a = cap.analyse("Напиши «хочу» в комментариях, и я пришлю гайд.\n")
        self.assertEqual(a["asks"], ["comment a keyword"])

    def test_russian_filler_tags(self):
        self.assertEqual(checks(cap.analyse("Первая строка с цифрой 5.\n\n#рек #втоп\n"))["HASHTAGS"], "WARN")


class HumanizeRussian(unittest.TestCase):
    def test_dash_kept_slop_replaced_flags_raised(self):
        clean, report = hum.humanize(RU_SLOP, LEX)
        self.assertIn("—", clean)
        self.assertNotIn("В современном мире", clean)
        self.assertIn("Сейчас", clean)
        names = " ".join(f["name"] for f in report["structures"])
        self.assertIn("бесшовный", names)
        self.assertIn("Это не просто", names)
        self.assertEqual(report["typographic"], [])

    def test_yo_variant_matches(self):
        clean, _ = hum.humanize("Давайте разберемся, как это работает.\n", LEX)
        self.assertNotIn("Давайте", clean)


class DetectRussian(unittest.TestCase):
    def test_slop_flagged_human_passes(self):
        _, slop_score, slop_verdict = det.run(RU_SLOP, LEX)
        _, human_score, human_verdict = det.run(RU_HUMAN, LEX)
        self.assertEqual(slop_verdict, "FLAGGED")
        self.assertEqual(human_verdict, "PASS", human_score)
        self.assertGreater(human_score, slop_score + 30)

    def test_russian_dash_is_not_a_fingerprint(self):
        self.assertEqual(det.check_fingerprint("Москва — столица. Это — правда, и это — нормально.")[0], 100.0)


class SwipeRussian(unittest.TestCase):
    def test_every_russian_example_names_its_own_formula(self):
        formulas = swipe.load_formulas(HOOKS_JSON)
        for h in HOOKS:
            self.assertEqual(swipe.classify(h["example"], formulas)[0], h["id"], h["example"])

    def test_russian_rows_rank(self):
        rows = [
            {"account": "@a", "followers": 5000, "median": 2000, "views": 90000,
             "hook": "Никто не говорит, что первые 30 рилсов провалятся"},
            {"account": "@b", "followers": 9000, "median": 3000, "views": 4000,
             "hook": "Хватит снимать бесплатно для портфолио"},
        ]
        a = swipe.analyse(rows, swipe.load_formulas(HOOKS_JSON))
        self.assertEqual([r["formula_id"] for r in a["reels"]], [3, 2])
        self.assertEqual(a["unclassified"], 0)


# --- Upstream bug fixes ------------------------------------------------------

class UpstreamFixes(unittest.TestCase):
    def test_4_1_spoken_numbers_are_concrete_in_beats(self):
        a = beats.analyse("Proposals took me five hours.\nI cut them to twenty minutes.\n"
                          "Three pages, one template.\n", 165)
        self.assertTrue(all(b["concrete"] > 0 for b in a["beats"]))
        self.assertFalse(any("nothing concrete" in n or "no number" in n for n in a["notes"]))

    def test_4_2_sentence_capital_is_not_a_name(self):
        self.assertEqual(hook.check_specificity("Proposals took forever. Now they do not.")[0], 15.0)
        a = beats.analyse("This is a line. Never mind the rest.\nAnother plain line here. Honestly nothing.\n"
                          "Third line with nothing. Still nothing.\n", 165)
        self.assertTrue(all(b["concrete"] == 0 for b in a["beats"]))

    def test_4_3_swipe_out_bare_filename(self):
        tmp = os.path.join(ROOT, "tests", "_tmp_swipe")
        os.makedirs(tmp, exist_ok=True)
        tsv = os.path.join(tmp, "c.tsv")
        with open(tsv, "w", encoding="utf-8") as fh:
            fh.write("account\tfollowers\tmedian\tviews\thook\n@a\t1\t1000\t5000\tStop posting daily\n")
        r = subprocess.run([sys.executable, os.path.join(SKILLS, "ig-viral", "swipe.py"), "c.tsv",
                            "--out", "swipe.md"], cwd=tmp, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(tmp, "swipe.md")))
        for f in ("c.tsv", "swipe.md"):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)

    def test_4_4_five_hashtags_are_not_a_wall(self):
        five = hum.humanize("A point worth making here.\n#a #b #c #d #e\n", LEX)[1]["structures"]
        six = hum.humanize("A point worth making here.\n#a #b #c #d #e #f\n", LEX)[1]["structures"]
        self.assertFalse(any("wall" in f["name"] for f in five))
        self.assertTrue(any("wall" in f["name"] for f in six))

    def test_4_6_script_mode_skips_burstiness(self):
        script = "Proposals took five hours.\nNow twenty minutes.\nOne template does it.\nSteal it below.\n"
        self.assertIn("skipped", det.run(script, LEX, script=True)[0]["BURSTINESS"][1])
        flags = hum.humanize(script * 2, LEX, script=True)[1]["structures"]
        self.assertFalse(any("Uniform" in f["name"] for f in flags))

    def test_17_weak_opener_needs_a_whole_word(self):
        self.assertNotIn("weak opener", hook.check_frontload("Your top nine covers lose followers")[1])
        self.assertNotIn("weak opener", hook.check_frontload("Some clients never pay")[1])
        self.assertNotIn("weak opener", hook.check_frontload("Такой провал я не ждал")[1])
        self.assertIn("weak opener", hook.check_frontload("So I lost a client")[1])
        self.assertIn("weak opener", hook.check_frontload("Так вот, я потерял всё")[1])

    def test_29_1_joined_emoji_survive(self):
        text = "Family day 👨‍👩‍👧 and pride 🏳️‍🌈\n"
        self.assertEqual(hum.humanize(text, LEX)[0], text)
        self.assertEqual(det.check_fingerprint("Family day 👨‍👩‍👧 and pride 🏳️‍🌈 with the kids.")[0], 100.0)
        # A lone zero-width space is still removed.
        self.assertEqual(hum.humanize("Hello​ world\n", LEX)[0], "Hello world\n")

    def test_29_2_preamble_is_flagged_not_deleted(self):
        clean, report = hum.humanize("In this video i'm going to show you my setup.\n", LEX)
        self.assertIn("In this video", clean)
        self.assertTrue(any("preamble" in f["name"].lower() for f in report["structures"]))

    def test_29_3_save_this_survives(self):
        self.assertEqual(hum.humanize("Save this for later.\n", LEX)[0], "Save this for later.\n")

    def test_29_4_name_can_be_the_payload(self):
        self.assertEqual(hook.check_frontload("The day Netflix called me back")[0], 100.0)

    def test_29_5_term_ending_in_punctuation_matches(self):
        report = hum.humanize("Great results this month. What are your thoughts?\n", LEX)[1]
        self.assertTrue(any(h["find"] == "what are your thoughts?" for h in report["lexical"]))

    def test_29_6_comment_below_is_not_a_keyword(self):
        self.assertEqual(cap.analyse("Comment below with your favourite tool.\n")["asks"], [])
        self.assertEqual(cap.analyse("Comment CONTRACT and I will send it.\n")["asks"], ["comment a keyword"])

    def test_29_7_nobody_is_talking_keeps_the_claim(self):
        self.assertEqual(hum.humanize("Nobody is talking about this.\n", LEX)[0], "Few people talk about this.\n")

    def test_44_2_styled_unicode_is_flagged(self):
        a = cap.analyse("𝗦𝗢𝗡𝗬 𝗙𝗫𝟯 𝗜𝗡 𝗧𝗛𝗘 𝗛𝗘𝗔𝗧\nShot on a hot day.\n", keywords=["Sony FX3"])
        self.assertEqual(checks(a)["STYLED TEXT"], "WARN")
        self.assertEqual(checks(a)["SEARCH TERMS"], "FAIL")

    def test_utf8_output_without_flags(self):
        r = subprocess.run([sys.executable, os.path.join(SKILLS, "ig-reel", "hookscore.py"),
                            "--hook", "Я потерял 18 000 рублей."], capture_output=True)
        self.assertIn("Я потерял 18 000 рублей.", r.stdout.decode("utf-8"))


# --- English regression against upstream -------------------------------------

class EnglishMatchesUpstream(unittest.TestCase):
    def test_hookscore(self):
        for text, want in SNAP["hookscore"].items():
            _, overall, verdict, _ = hook.run(text)
            self.assertAlmostEqual(overall, want["score"], places=3, msg=text)
            self.assertEqual(verdict, want["verdict"], text)

    def test_beats(self):
        self.assertEqual(beats.analyse(SNAP["beats"]["input"], 165, 15), SNAP["beats"]["output"])

    def test_caption(self):
        c = SNAP["caption"]
        self.assertEqual(cap.analyse(c["input"], keywords=c["keywords"]), c["output"])

    def test_humanize(self):
        self.assertEqual(hum.humanize(SNAP["humanize"]["input"], LEX)[0], SNAP["humanize"]["output"])

    def test_detect(self):
        self.assertAlmostEqual(det.run(SNAP["detect"]["input"], LEX)[1], SNAP["detect"]["score"], places=3)

    def test_classify(self):
        formulas = swipe.load_formulas(HOOKS_JSON)
        for h in HOOKS:
            self.assertEqual(swipe.classify(h["example_en"], formulas)[0],
                             SNAP["classify_en"][h["example_en"]], h["example_en"])


if __name__ == "__main__":
    unittest.main()
