"""Вставляет data/achievements.json в scripts/template.html -> index.html в корне (один файл для GitHub Pages).
Запуск из корня репозитория: python3 scripts/make_html.py"""
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
data = (ROOT / "data" / "achievements.json").read_text(encoding="utf-8").replace("</", "<\\/")
html = (ROOT / "scripts" / "template.html").read_text(encoding="utf-8").replace("__DATA__", data)
(ROOT / "index.html").write_text(html, encoding="utf-8")
print("index.html:", round(len(html.encode()) / 1024), "KB")
