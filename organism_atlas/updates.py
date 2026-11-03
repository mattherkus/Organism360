"""Проверка обновлений: есть ли на GitHub выпуск новее этой версии. Без Qt.

Раз в день (не чаще) программа в фоне спрашивает у GitHub последний выпуск репозитория REPO - обычный
анонимный запрос к api.github.com, без данных о пользователе. Если версия выпуска больше organism_atlas.__version__,
в верхней панели появляется кнопка со ссылкой на страницу выпуска. Отключается в настройках («Проверять
обновления») или переменной окружения ORGANISM_ATLAS_NO_UPDATE_CHECK=1 (её ставят тесты).
"""

import datetime
import json
import os
import re
import urllib.request

from . import __version__, settings

REPO = "mattherkus/igra"
URL = "https://api.github.com/repos/%s/releases/latest" % REPO
TIMEOUT = 6                     # секунд на ответ: дольше не ждём, проверка - не повод висеть


def parse(tag):
    """'v1.2.0' -> (1, 2, 0); не версия - None"""
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", (tag or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def newer(tag, current=__version__):
    """версия tag больше текущей"""
    a, b = parse(tag), parse(current)
    if a is None or b is None:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def enabled(saved=None):
    if os.environ.get("ORGANISM_ATLAS_NO_UPDATE_CHECK", "").lower() in ("1", "yes", "on", "true"):
        return False
    return settings.get(saved if saved is not None else settings.load(), "updates") == "on"


def due(saved=None, today=None):
    """пора ли проверить: проверка включена и сегодня её ещё не было"""
    saved = saved if saved is not None else settings.load()
    today = (today or datetime.date.today()).isoformat()
    return enabled(saved) and saved.get("update_checked") != today


def check(opener=urllib.request.urlopen, today=None):
    """спросить GitHub о последнем выпуске: {"version", "url"}, если он новее этой версии, иначе None.
    Любая ошибка сети - тоже None (проверка тихая). Дата проверки запоминается в настройках"""
    settings.save(update_checked=(today or datetime.date.today()).isoformat())
    req = urllib.request.Request(URL, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "organism-atlas/" + __version__})
    try:
        with opener(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    tag = data.get("tag_name", "") if isinstance(data, dict) else ""
    if not newer(tag):
        return None
    url = data.get("html_url")
    if not (isinstance(url, str) and url.startswith("https://github.com/")):     # открывается в браузере: только GitHub
        url = "https://github.com/%s/releases" % REPO
    return {"version": tag.lstrip("v"), "url": url}
