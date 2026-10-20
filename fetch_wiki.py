"""Собирает с Fandom-вики заметки «как получить» для ачивок.

Что делает:
  1. Для каждой категории ачивок открывает её страницу на вики (например
     «Wonders of the World») и ищет в таблицах строку с названием ачивки.
     Весь текст строки сохраняется как заметка.
  2. Для ачивок, которых нет в таблицах, проверяет, есть ли на вики отдельная
     страница с таким же названием, и берёт с неё начало текста.
     Осторожно: такая страница может быть про одноимённый квест или предмет.
     Такие заметки помечаются source="page".

Результат: wiki_notes.json  {id: {"source", "url", "text"}}  и отчёт в консоли.
Все ответы вики кешируются в папку wiki_cache/, повторный запуск сеть не дёргает.

Установка:  pip install requests beautifulsoup4
Запуск:
  python3 scripts/fetch_wiki.py --groups "Wonders of the World" --limit 20   # сначала пробный прогон
  python3 scripts/fetch_wiki.py                                              # всё
  python3 scripts/fetch_wiki.py --lang ru                                    # русская вики, русские названия

Тексты вики распространяются по лицензии CC BY-SA: ссылку на источник (url)
сохраняем и показываем на странице.
"""
import argparse, json, os, re, sys, time, hashlib
import requests
from pathlib import Path
from bs4 import BeautifulSoup

WIKI = {
    "en": "https://genshin-impact.fandom.com",
    "ru": "https://genshin-impact.fandom.com/ru",
}
HEADERS = {"User-Agent": "TeyvatAchievementsTracker/0.1 (fan project; contact via GitHub)"}
DELAY = 1.0          # секунд между запросами — не нагружаем вики
ROOT = Path(__file__).resolve().parent.parent
CACHE = str(ROOT / "wiki_cache")


def norm(s):
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[«»\"'“”„‘’`!?.,:;…\-–—()]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def api(base, params):
    """GET к api.php с кешем на диске."""
    params = {**params, "format": "json", "formatversion": "2"}
    key = hashlib.sha1((base + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    path = os.path.join(CACHE, key + ".json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    for attempt in range(4):
        try:
            r = requests.get(base + "/api.php", params=params, headers=HEADERS, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            wait = 5 * (attempt + 1)
            print(f"  ! {e}, повтор через {wait} c", file=sys.stderr)
            time.sleep(wait)
    else:
        raise SystemExit("Вики не отвечает — попробуй позже, кеш сохранится.")
    os.makedirs(CACHE, exist_ok=True)
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    time.sleep(DELAY)
    return data


def parse_html(base, page):
    d = api(base, {"action": "parse", "page": page, "prop": "text", "redirects": 1})
    if "error" in d:
        return None, None
    title = d["parse"]["title"]
    return title, BeautifulSoup(d["parse"]["text"], "html.parser")


def page_url(base, title):
    return f"{base}/wiki/{title.replace(' ', '_')}"


def rows_from_tables(soup):
    """Все строки всех таблиц страницы: список (нормализованный текст первых ячеек, полный текст)."""
    out = []
    for tr in soup.select("table tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) >= 2 and tr.find("td"):
            out.append((cells, " | ".join(cells)))
    return out


def find_row(rows, name):
    n = norm(name)
    # точное совпадение одной из первых двух ячеек
    for cells, text in rows:
        if any(norm(c) == n for c in cells[:2]):
            return text
    # ячейка начинается с названия (бывает «Название Hidden»)
    for cells, text in rows:
        if any(norm(c).startswith(n + " ") for c in cells[:2]):
            return text
    return None


def page_intro(soup, limit=1500):
    """Первые абзацы и пункты списков страницы, без инфобоксов и навигации."""
    for junk in soup.select("aside, table, .navbox, .toc, sup.reference, script, style"):
        junk.decompose()
    parts = []
    for el in soup.find_all(["p", "li", "h2", "h3"]):
        t = el.get_text(" ", strip=True)
        if not t:
            continue
        if el.name in ("h2", "h3") and re.match(r"(references|navigation|change history|история изменений|навигация)", t, re.I):
            break
        parts.append(t)
        if sum(len(p) for p in parts) > limit:
            break
    return " ".join(parts)[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=WIKI, default="en")
    ap.add_argument("--groups", nargs="*", help="только эти категории (названия как на вики)")
    ap.add_argument("--limit", type=int, default=0, help="не больше N ачивок (для пробного прогона)")
    ap.add_argument("--no-pages", action="store_true", help="не искать отдельные страницы ачивок")
    ap.add_argument("--out", default=str(ROOT / "data" / "source" / "wiki_notes.json"))
    a = ap.parse_args()

    base = WIKI[a.lang]
    data = json.load(open(ROOT / "data" / "achievements.json", encoding="utf-8"))
    name_key = "nameEn" if a.lang == "en" else "name"
    groups = {g["id"]: g[name_key] for g in data["groups"]}
    achs = data["achievements"]
    if a.groups:
        wanted = {norm(x) for x in a.groups}
        achs = [x for x in achs if norm(groups[x["group"]]) in wanted]
    if a.limit:
        achs = achs[: a.limit]
    print(f"Ачивок к обработке: {len(achs)} | вики: {base}")

    notes = json.load(open(a.out, encoding="utf-8")) if os.path.exists(a.out) else {}

    # 1. Таблицы на страницах категорий
    by_group = {}
    for x in achs:
        by_group.setdefault(x["group"], []).append(x)
    missing_groups = []
    for gid, items in by_group.items():
        gname = groups[gid]
        title, soup = parse_html(base, gname)
        if not soup:
            missing_groups.append(gname)
            continue
        rows = rows_from_tables(soup)
        hit = 0
        for x in items:
            row = find_row(rows, x[name_key])
            if row:
                notes[str(x["id"])] = {"source": "table", "url": page_url(base, title), "text": row}
                hit += 1
        print(f"  {gname}: {hit}/{len(items)} найдено в таблицах")

    # 2. Отдельные страницы для оставшихся
    if not a.no_pages:
        rest = [x for x in achs if str(x["id"]) not in notes and x[name_key]]
        print(f"Проверяю отдельные страницы для {len(rest)} ачивок…")
        exists = {}
        for i in range(0, len(rest), 50):
            batch = rest[i:i + 50]
            d = api(base, {"action": "query", "titles": "|".join(x[name_key] for x in batch), "redirects": 1})
            q = d.get("query", {})
            redirect = {r["from"]: r["to"] for r in q.get("redirects", []) + q.get("normalized", [])}
            found = {p["title"] for p in q.get("pages", []) if not p.get("missing")}
            for x in batch:
                t = x[name_key]
                t = redirect.get(t, t); t = redirect.get(t, t)
                if t in found:
                    exists[x["id"]] = t
        for x in rest:
            if x["id"] not in exists:
                continue
            title, soup = parse_html(base, exists[x["id"]])
            if soup:
                text = page_intro(soup)
                if text:
                    notes[str(x["id"])] = {"source": "page", "url": page_url(base, title), "text": text}

    json.dump(notes, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    got = [x for x in achs if str(x["id"]) in notes]
    src = {}
    for x in got:
        s = notes[str(x["id"])]["source"]; src[s] = src.get(s, 0) + 1
    print(f"\nГотово: заметки для {len(got)}/{len(achs)} ачивок {src} -> {a.out}")
    if missing_groups:
        print("Не нашлись страницы категорий:", "; ".join(missing_groups))
    lost = [x[name_key] for x in achs if str(x["id"]) not in notes]
    if lost:
        print(f"Без заметки ({len(lost)}), первые 15:", "; ".join(lost[:15]))
    for x in got[:3]:
        n = notes[str(x["id"])]
        print(f"\nПример — {x[name_key]} [{n['source']}]\n  {n['text'][:300]}")


if __name__ == "__main__":
    main()
