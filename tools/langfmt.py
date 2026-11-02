"""Запись файлов lang/*.json в принятом виде: отступ 2, кириллица как есть, а списки слов в разделе links -
в одну строку (их много и они короткие). Нужна скриптам, которые правят тексты программно.

    python tools/langfmt.py            # переписать все lang/*.json в этом виде (проверка: git diff пуст)
"""

import json
import sys
from pathlib import Path

LANG_DIR = Path(__file__).resolve().parents[1] / "organism_atlas" / "lang"


def _dump(v, indent, path):
    pad = "  " * indent
    if isinstance(v, dict):
        if not v:
            return "{}"
        items = ['%s  %s: %s' % (pad, json.dumps(k, ensure_ascii=False), _dump(x, indent + 1, path + (k,)))
                 for k, x in v.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(v, list):
        if not v:
            return "[]"
        if path[:1] == ("links",) and all(isinstance(x, str) for x in v):
            return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in v) + "]"
        items = [pad + "  " + _dump(x, indent + 1, path) for x in v]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"
    return json.dumps(v, ensure_ascii=False)


def dumps(data):
    return _dump(data, 0, ()) + "\n"


def save(path, data):
    Path(path).write_text(dumps(data), encoding="utf-8")


def main():
    for p in sorted(LANG_DIR.glob("*.json")):
        save(p, json.loads(p.read_text(encoding="utf-8")))


if __name__ == "__main__":
    sys.exit(main())
