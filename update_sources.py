"""Скачивает свежие исходные данные ачивок в data/source/:
  - pm_ru.json, pm_en.json — из репозитория paimon.moe (github.com/MadeBaruna/paimon-moe);
  - gdb_achievements.json — выжимка из npm-пакета genshin-db (скрытость и порядок ачивок).
Таблицы вики (wiki_achievements.json) этим скриптом не обновляются — см. README.

Запуск из корня репозитория: python3 scripts/update_sources.py
"""
import io, json, tarfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "source"
UA = {"User-Agent": "TeyvatAchievementsTracker/0.2"}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()

for lang in ("ru", "en"):
    raw = get(f"https://raw.githubusercontent.com/MadeBaruna/paimon-moe/main/src/data/achievement/{lang}.json")
    json.loads(raw)  # проверка, что это JSON
    (SRC / f"pm_{lang}.json").write_bytes(raw)
    print(f"pm_{lang}.json: {len(raw) // 1024} KB")

meta = json.loads(get("https://registry.npmjs.org/genshin-db/latest"))
print("genshin-db", meta["version"], "— скачиваю пакет…")
tar = tarfile.open(fileobj=io.BytesIO(get(meta["dist"]["tarball"])), mode="r:gz")
member = tar.getmember("package/src/min/data.min.json")
data = json.load(tar.extractfile(member))["data"]["Russian"]["achievements"]
slim = {}
for v in data.values():
    for i in v["id"]:
        slim[i] = {"hidden": bool(v.get("isHidden")), "sort": v.get("sortOrder", 0)}
(SRC / "gdb_achievements.json").write_text(json.dumps(slim, separators=(",", ":")), encoding="utf-8")
print("gdb_achievements.json:", len(slim), "ступеней")
print("Готово. Дальше: python3 scripts/build.py && python3 scripts/make_html.py")
