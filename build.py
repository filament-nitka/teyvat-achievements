"""Собирает achievements.json из открытых данных.

Источники:
  - paimon.moe (github.com/MadeBaruna/paimon-moe): src/data/achievement/ru.json и en.json —
    русские/английские тексты, версии, награды, поручения.
  - genshin-db (npm genshin-db): флаг скрытости, порядок, группы.
Плюс ручные подсказки из pilot_hints.py.

Запуск из корня репозитория: python3 scripts/build.py
Исходники лежат в data/source/, результат — data/achievements.json.
"""
import json, re, datetime
from pilot_hints import PILOT
from hidden_hints import HIDDEN, DESC_OK
from translate_en import translate
from wiki_maps import WIKI_MAPS
import urllib.parse

from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "source"
pm_ru = json.load(open(SRC / "pm_ru.json", encoding="utf-8"))
pm_en = json.load(open(SRC / "pm_en.json", encoding="utf-8"))
GDB = json.load(open(SRC / "gdb_achievements.json", encoding="utf-8"))  # {id: {hidden, sort}} — выжимка из genshin-db

hidden_ids, sort_of = set(), {}
for k, v in GDB.items():
    sort_of[int(k)] = v.get("sort", 0)
    if v.get("hidden"):
        hidden_ids.add(int(k))

WIKI_EN = "https://genshin-impact.fandom.com"
pm_en_desc = {}
en_name = {}
for g in pm_en.values():
    for a in g["achievements"]:
        for x in (a if isinstance(a, list) else [a]):
            en_name[x["id"]] = x["name"]
            pm_en_desc[x["id"]] = x["desc"]

# Грубая авто-разметка по описанию и группе. Это стартовая точка, не истина.
DESC_RULES = [
    ("сюжет", r"заверш\w* (задани|главу|акт)|в задании «"),
    ("коллекция", r"соберите (все|полн)|коллекци|прочитайте все"),
    ("исследование", r"сундук|откройте|телепорт|статуй|окул|исследуйте|найдите все"),
    ("бой", r"победите|одолейте|уничтожьте|нанесите"),
    ("быт", r"рыб|чайник|приготовьте|блюд"),
]
GROUP_RULES = [
    ("бой", r"^Победитель|^Дуэлянт"),
    ("бездна", r"Бездна|Театр|Воображариум"),
    ("быт", r"рыбалке|Бессмертная обитель"),
    ("сюжет", r"Воспоминания сердца|Путешествие героя"),
    ("карты", r"Священный призыв"),
]

import os, collections
wiki = json.load(open(SRC / "wiki_notes.json", encoding="utf-8")) if (SRC / "wiki_notes.json").exists() else {}

# Таблицы Fandom-вики (собраны через браузер): wiki_achievements.json, CC BY-SA.
WT = json.load(open(SRC / "wiki_achievements.json", encoding="utf-8")) if (SRC / "wiki_achievements.json").exists() else {"ru": [], "en": []}
def wnorm(s):
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"\(\s*й?ка\s*\)|\(ца\)|\(а\)", "", s)
    return re.sub(r"[^\w]+", " ", s).strip()
WRU, WEN = collections.defaultdict(list), collections.defaultdict(list)
for r in WT["ru"]: WRU[wnorm(r["n"])].append(r)
for r in WT["en"]: WEN[wnorm(r["n"])].append(r)

def wiki_pick(index, name, group, desc):
    rows = index.get(wnorm(name), [])
    same = [r for r in rows if r.get("g") == group] or rows
    exact = [r for r in same if wnorm(r.get("d")) == wnorm(desc)]
    best = (exact or same or [None])[0]
    req = next((r["r"] for r in (exact + same) if re.sub(r"[\s\-–—?]|n/?a", "", (r.get("r") or "").lower())), "")
    return best, req

CAT_TAGS = {
    "Задания Архонтов": ["сюжет"], "Задания мира": ["задание мира"], "Исследование": ["исследование"],
    "Бой": ["бой"], "Поручения": ["поручение", "irl"], "Репутация": ["irl"], "Рыбалка": ["быт"], "Волноход": ["исследование"],
    "Quest": ["задание мира"], "Quests": ["задание мира"], "Quest/Exploration": ["задание мира", "исследование"],
    "Exploration": ["исследование"], "Boss": ["бой"], "Commission": ["поручение", "irl"],
}
UNTAGGED_RULES = [
    ("сюжет", r"получите силу элемента"),
    ("задание мира", r"^(выполните|завершите) (задание )?«|завершите историю|выполните поручение|добудьте|познакомьтесь с|устраните помехи|разрешите ситуацию|завершите приключение|завершите ритуал|завершите араньяку|завершите восстановление"),
    ("исследование", r"фе[ийя]\b|феями|повысьте|развейте|симфони|маниту|граффити|ограниченн\w* по времени испытани|печат|усыпальниц|тайник|статую|до макс|максимальн\w* уров|подношени|благосклонност|колонну|разблокируйте|фотографии|диковин"),
    ("бой", r"^Мастер элементов|^Первоклассный стрелок|^Край пробудившихся"),
    ("кооп", r"^Встреча в другом мире"),
    ("быт", r"^Репертуар мириад мелодий|изготовьте"),
]
# ---------- регионы ----------
REGIONS = ["Мондштадт", "Ли Юэ", "Инадзума", "Сумеру", "Фонтейн", "Натлан", "Нод-Край", "Снежная"]
GROUP_REGION = {4: "Мондштадт", 16: "Мондштадт", 67: "Мондштадт",
    5: "Ли Юэ", 30: "Ли Юэ", 47: "Ли Юэ",
    24: "Инадзума", 26: "Инадзума", 27: "Инадзума", 28: "Инадзума",
    31: "Сумеру", 35: "Сумеру", 38: "Сумеру", 41: "Сумеру",
    42: "Фонтейн", 45: "Фонтейн", 46: "Фонтейн", 48: "Фонтейн",
    51: "Натлан", 55: "Натлан", 60: "Натлан", 62: "Натлан",
    63: "Нод-Край", 66: "Нод-Край", 68: "Нод-Край",
    69: "Снежная", 70: "Снежная"}
KW = {
    "Мондштадт": r"мондштадт|драконь\w* хребт|спрингвейл|винокурн|мыс\w* веры|звездопад|сесили|барбатос|анемо архонт|пик\w* ветров|храм\w* пространства|шепчущ\w* лес",
    "Ли Юэ": r"ли юэ|цинъюн|гуйли|ваншу|разлом|чэньюй|гуй цзан|уван|лиша|минлин|тяньцю|цзюэюнь|хуагуан|бишуй|нефритов\w* двор|гуйчжун",
    "Инадзума": r"инадзум|наруками|каннадзук|ясиори|ватацуми|сэйрай|цуруми|энканоми|\bрито\b|татарасун|тэнсюкаку",
    "Сумеру": r"сумеру|ванаран|хадрамавет|дешрет|пустын|авидья|апам|ашаван|асипаттраван|араньяк|аранар|хамад|сетех|колоннад|махавайпуль|аару|караван-рибат",
    "Фонтейн": r"фонтейн|кур-де|эрини|белло|берилл|лиффи|морте|ипсиссим|аквабус|ностой|море древности|пухлен|ксенохромн",
    "Натлан": r"натлан|маниту|тецкатепетонк|атокпан|толлан|юмказавр|завр|ночн\w* дух|печ\w* огненного пламени|кукузавр|тепетлизавр|граффити",
    "Нод-Край": r"нод-кра|куувяк|куувахк|куухенк|морозн\w* лун|дунанн|древних лун",
    "Снежная": r"\bснежн(ой|ая|ую)\b|шатанай|сфер\w* теней|ранкова|заполярн",
}
COMM_REGION = {"mondstadt": "Мондштадт", "liyue": "Ли Юэ", "inazuma": "Инадзума", "sumeru": "Сумеру",
               "fontaine": "Фонтейн", "natlan": "Натлан", "nodkrai": "Нод-Край", "snezhnaya": "Снежная"}
def ver_region(v):
    try: mj, mn = (int(x) for x in str(v).split(".")[:2])
    except Exception: return None
    if mj == 2: return "Ли Юэ" if mn == 6 else ("Инадзума" if mn <= 5 else None)
    if mj == 3: return "Сумеру"
    if mj == 4: return "Ли Юэ" if mn == 4 else "Фонтейн"
    if mj == 5: return "Натлан"
    if mj == 6: return "Мондштадт" if mn == 5 else "Нод-Край"
    if mj == 7: return "Снежная"
    return None
def region_of(gid, first, hint, quest):
    if gid in GROUP_REGION: return GROUP_REGION[gid]
    c = first.get("commissions")
    if isinstance(c, str) and c.lower() in COMM_REGION: return COMM_REGION[c.lower()]
    text = " ".join([first["desc"], hint or "", quest or ""]).lower()
    hits = {r: len(re.findall(rx, text)) for r, rx in KW.items()}
    best = max(hits.values())
    if best:
        top = [r for r, n in hits.items() if n == best]
        if len(top) == 1: return top[0]
    if gid in (0, 17):
        return ver_region(first.get("ver"))
    return None

# ---------- типы меток на карте HoYoLAB ----------
OCULI = {"Мондштадт":5, "Ли Юэ":6, "Инадзума":194, "Сумеру":403, "Фонтейн":508, "Натлан":626, "Нод-Край":694, "Снежная":833}
SHRINES = {"Инадзума":212, "Сумеру":411, "Фонтейн":509, "Натлан":577, "Нод-Край":703, "Снежная":835}
HOYO_RULES = [
    (r"местн\w* легенд", [547]), (r"электро фе", [205, 147]), (r"тёпл\w* фе|теплых фе|тёплых фе", [148, 147]),
    (r"\bфе[ийя]\b|феями|\bфей\b", [18, 147]), (r"маниту|граффити", [597, 602]),
    (r"ограниченн\w* по времени испытани", [64]), (r"колокол\w* духов", [478]), (r"барабан", [476]),
    (r"ниродх", [477]), (r"первозданн\w* обелиск", [444]), (r"книжн\w* полк", [578]), (r"миазм", [576]),
    (r"испытани\w* воина", [600]), (r"тотем\w* ночного|ночного духа|палат\w* испытания ночи", [683, 647]), (r"сфер\w* теней", [842, 839]),
    (r"переполняющ\w* сил\w* бездны", [785]), (r"факел", [71]), (r"элементальн\w* монумент", [70]),
    (r"летательн\w* аппарат", [520]), (r"кудзира", [225]), (r"светоносн\w* кристалл|светоносного камня", [357]),
    (r"куувяк", [711]), (r"фантомн\w* рисун|фреск", [445]),
]
def hoyo_types(text, region, gid):
    t = re.sub(r"фе[иия] мудрости", "", text.lower()); ids = []
    for rx, li in HOYO_RULES:
        if re.search(rx, t): ids += [i for i in li if i not in ids]
    if re.search(r"статую? семи|статуя семи|статую богини луны", t) and region in OCULI: ids.append(OCULI[region])
    if re.search(r"усыпальниц", t) and region in SHRINES: ids.append(SHRINES[region])
    if not ids: return None
    mp = 9 if gid == 30 else (7 if gid == 28 else 2)
    return f"https://act.hoyolab.com/ys/app/interactive-map/index.html?lang=ru-ru#/map/{mp}?shown_types=" + ",".join(map(str, ids))

# ---------- усилия ----------
QUICK = r"впервые|получите удар|присядьте|сфотограф|поднимитесь на|обменяйтесь|сядьте|поиграйте|погладьте|упадите|спугните|позвольте|подберите|наденьте|сбейте"
LONG = r"\bвсе\b|\bвсех\b|максимальн|до макс|уровн\w* репутации|\b\d{3,}\b"
def effort_of(first, stages, tags, status, hidden):
    text = " ".join(s["desc"] for s in stages).lower()
    if "irl" in tags or "коллекция" in tags or "бездна" in tags or re.search(LONG, text): return "долго"
    if "нелепость" in tags: return "быстро"
    if re.search(r"карт\w* |области|заверш\w* «|выполните «|главу", text): return "средне"
    if len(stages) == 1 and re.search(QUICK, text) and "сюжет" not in tags: return "быстро"
    if len(stages) == 1 and (stages[0].get("reward") or 0) <= 5 and set(tags) <= {"исследование", "быт", "кооп"}: return "быстро"
    return "средне"

EXTRA = [("кооп", r"совместн|co-?op"), ("irl", r"ежедневн|раз в день|каждый день|еженедел|daily|weekly|real[- ]time|реальн\w* врем")]

groups, items = [], []
for gid, g in sorted(pm_ru.items(), key=lambda kv: kv[1]["order"]):
    groups.append({"id": int(gid), "name": g["name"], "nameEn": pm_en.get(gid, {}).get("name", ""), "order": g["order"]})
    for a in g["achievements"]:
        stages = a if isinstance(a, list) else [a]
        first = stages[0]
        key = first["id"]
        tags, quest, hint, links, status = [], None, "", [], "none"

        if key in PILOT:
            p = PILOT[key]
            tags, quest, hint = list(p[0]), p[1], p[2]
            if len(p) > 3:
                links.append(p[3])
            status = "draft" if hint else "none"
        else:
            text = first["desc"].lower()
            for t, rx in GROUP_RULES:
                if re.search(rx, g["name"]):
                    tags.append(t)
            for t, rx in DESC_RULES:
                if re.search(rx, text) and t not in tags:
                    tags.append(t)
            m = re.search(r"заверш\w* (?:задание |историю )?«([^»]+)»", first["desc"], re.I)
            if m and not first.get("commissions"):
                if "задание мира" not in tags and "сюжет" not in tags:
                    tags.append("задание мира")
                quest = f"«{m.group(1)}»"
                hint = "Пройдите задание с этим названием."
                status = "auto"
            elif re.search(r"^(станьте свидетелем|помогите|узнайте|спасите|сопроводите|выполните просьбу)", text) and not tags:
                tags.append("задание мира")
            if first.get("commissions"):
                tags = ["поручение", "irl"]
                qn = first.get("quest", {}).get("name") or []
                quest = "Поручение: " + ", ".join(f"«{q}»" for q in qn) if qn else None
                hint = "Выпадает случайно в ежедневных поручениях — проверяйте каждый день."
                status = "auto"
        if len(stages) > 1 and "ступени" not in tags:
            pass  # ступени видны и так

        # --- вики ---
        wr, req_ru = wiki_pick(WRU, first["name"], g["name"], first["desc"])
        we, req_en = wiki_pick(WEN, en_name.get(key, ""), g["name"], pm_en_desc.get(key, ""))
        cat = (wr or {}).get("c") or (we or {}).get("c") or ""
        wtags = list(CAT_TAGS.get(cat, []))
        if "задание мира" in wtags and re.search(r"archon quest|задани\w* архонт", (req_en + req_ru).lower()):
            wtags = ["сюжет"] + [t for t in wtags if t != "задание мира"]
        if wtags:
            keep = [t for t in tags if t in ("кооп", "нелепость", "быт") or (t == "irl" and not (req_ru or req_en))]
            tags = wtags + [t for t in keep if t not in wtags]
        for t, rx in EXTRA:
            if re.search(rx, (req_ru + " " + req_en + " " + first["desc"]).lower()) and t not in tags:
                tags.append(t)
        wiki_url = WIKI_EN + we["p"].replace("/wiki/", "/wiki/", 1) if we and we.get("p") else None
        if req_ru:
            hint, status = req_ru, "wiki"
        elif req_en:
            tr = translate(key, req_en)
            hint, status = (tr, "wiki-tr") if tr else (req_en, "wiki-en")
        m = re.search(r"«([^«»]*(?:«[^»]*»[^«»]*)*)»", hint) if status in ("wiki", "wiki-en", "wiki-tr") else None
        if m and not quest and re.match(r"(заверш|пройд|открывается во время прохождения|выдаётся по ходу)", hint.lower()):
            quest = f"«{m.group(1)}»"

        # --- скрытые без требований: подсказки по страницам вики ---
        if not hint and key in HIDDEN:
            hint, status = HIDDEN[key], "wiki-draft"
            if re.search(r"местн\w* легенд", first["desc"].lower()) and "бой" not in tags:
                tags.append("бой")
            if "кооп" in hint and "кооп" not in tags:
                tags.append("кооп")
        # --- триаж того, что осталось без подсказки ---
        if not hint:
            m = re.search(r"главу «([^»]+)»", first["desc"]) or re.match(r"(?:Завершите|Выполните)(?: задание)? «([^»]+)»\.?$", first["desc"])
            if m:
                tags = ["сюжет"] + [t for t in tags if t != "сюжет"]
                quest = f"«{m.group(1)}»"
                status = "desc"
            elif gid == "0" and str(key).startswith("82"):
                if "бой" not in tags:
                    tags.append("бой")
                status = "desc"
            elif key not in hidden_ids or key in DESC_OK:
                status = "desc"
            elif re.search(r"местн\w* легенд", first["desc"].lower()) and "бой" not in tags:
                tags.append("бой")

        # --- добивка тегов и чистка ---
        text = first["desc"].lower()
        if re.search(r"уровн\w* репутации", text) and "irl" not in tags:
            tags.append("irl")
        if hint and re.sub(r"\W", "", hint.lower()) == re.sub(r"\W", "", text):
            hint, status = "", "desc"
        if not tags:
            for t, rx in UNTAGGED_RULES:
                if re.search(rx, text) or re.search(rx, g["name"]):
                    tags.append(t); break
        if not tags and re.match(r"(Пройдите задани|Выдаётся по ходу)", hint or ""):
            tags.append("задание мира")

        w = wiki.get(str(key))
        if w and w["url"] not in links:
            links.append(w["url"])

        # --- регион и усилия ---
        region = region_of(int(gid), first, hint, quest)
        effort = effort_of(first, stages, tags, status, key in hidden_ids)

        # --- карты ---
        wmap = None
        if wiki_url:
            base = re.sub(r"\s*\(Tier \d+\)$", "", urllib.parse.unquote(wiki_url.split("/wiki/",1)[1]).replace("_"," "))
            if base in WIKI_MAPS:
                wmap = wiki_url + ("#" + WIKI_MAPS[base] if WIKI_MAPS[base] else "")
        hmap = hoyo_types(first["desc"] + " " + (hint or ""), region, int(gid))

        items.append({
            "id": key,
            "group": int(gid),
            "name": first["name"],
            "nameEn": en_name.get(key, ""),
            "hidden": key in hidden_ids,
            "ver": first.get("ver", ""),
            "sort": sort_of.get(key, 0),
            "stages": [{"id": s["id"], "desc": s["desc"], "reward": s.get("reward", 0)} for s in stages],
            "tags": tags,
            "quest": quest,
            "hint": hint,
            "links": links,
            "checklist": first.get("checklist"),
            "wiki": wiki_url,
            "wikiCat": cat,
            "status": status,          # none | desc | auto | draft | wiki | wiki-en | wiki-draft | verified
            "pilot": key in PILOT,
            "region": region,
            "wmap": wmap,
            "hmap": hmap,
            "effort": effort,
        })

out = {
    "generated": datetime.date.today().isoformat(),
    "sources": ["paimon.moe (MadeBaruna/paimon-moe)", "genshin-db", "Genshin Impact Wiki, Fandom (CC BY-SA)"],
    "groups": groups,
    "achievements": items,
}
json.dump(out, open(ROOT / "data" / "achievements.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
missing = set(PILOT) - {i["id"] for i in items}
print("ачивок:", len(items), "| пилот:", sum(i["pilot"] for i in items),
      "| с подсказкой в пилоте:", sum(1 for i in items if i["pilot"] and i["hint"]),
      "| без тегов всего:", sum(1 for i in items if not i["tags"]),
      "| не найдено id:", missing or "—")
st = collections.Counter(i["status"] for i in items); print("статусы:", dict(st))
print("карты: вики", sum(1 for i in items if i["wmap"]), "| hoyolab", sum(1 for i in items if i["hmap"]))
print("регионы:", dict(collections.Counter(i["region"] for i in items))); print("усилия:", dict(collections.Counter(i["effort"] for i in items)))
print("без тегов:", sum(1 for i in items if not i["tags"]), "| без подсказки:", sum(1 for i in items if not i["hint"]))
