"""Небольшие JSON-файлы пользователя (настройки, прогресс, заметки): чтение с проверкой и надёжная запись. Без Qt.

Запись атомарная: сначала временный файл, сброшенный на диск (fsync), потом os.replace. Иначе после
отключения питания на месте файла мог остаться пустой или забитый нулями файл. На Windows os.replace
иногда не проходит, потому что файл ненадолго держит антивирус или индексатор: тогда пробуем ещё пару раз.
Испорченный файл не мешает работе: данные начинаются заново, но сам файл копируется в <имя>.bad.
Следующая запись его затрёт, а из копии историю ещё можно спасти.
"""

import json
import os
import time
from pathlib import Path

RETRIES = 3                     # попыток os.replace, когда файл занят другим процессом
RETRY_S = 0.05                  # пауза перед следующей попыткой, растёт с каждой попыткой


def read_bytes(path):
    """байты файла или None, если его нет или его нельзя прочитать"""
    try:
        return Path(path).read_bytes()
    except OSError:
        return None


def decode(raw, path=None):
    """байты файла -> словарь. Нет файла (None) - пустой словарь; испорченный файл - тоже пустой,
    а если указан path, его байты сохраняются в <path>.bad"""
    if raw is None:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:                      # UnicodeDecodeError - тоже ValueError
        data = None
    if isinstance(data, dict):
        return data
    if path is not None and raw.strip(b"\0 \t\r\n"):     # пустой или нулевой файл спасать нечего
        keep_broken(path, raw)
    return {}


def keep_broken(path, raw):
    """сохранить байты испорченного файла рядом, в <имя>.bad (ошибки записи пропускаем)"""
    p = Path(path)
    try:
        p.with_name(p.name + ".bad").write_bytes(raw)
    except OSError:
        pass


def write(path, data, indent=1):
    """записать data в JSON атомарно; True, если записалось. Ошибки записи не повод падать: False"""
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        for i in range(RETRIES):
            try:
                os.replace(tmp, p)
                return True
            except PermissionError:
                if i == RETRIES - 1:
                    raise
                time.sleep(RETRY_S * (i + 1))
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
    return False


class Cached:
    """файл, который читают часто (например, на каждый щелчок). Байты читаются всегда, потому что файл могли
    поменять, а parse(байты) вызывается, только если они изменились"""

    def __init__(self, parse):
        self.parse = parse
        self.last = None                    # (байты файла, разобранные данные)

    def load(self, path):
        raw = read_bytes(path)
        if self.last is None or self.last[0] != raw:
            self.last = (raw, self.parse(raw, path))
        return self.last[1]
