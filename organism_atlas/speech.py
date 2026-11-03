"""Чтение вслух (карточка органа, кости, мышцы): синтез речи без лишних зависимостей.

Голос берётся из первого доступного источника:
  1. QtTextToSpeech - есть в полном PySide6 (pip install PySide6), в PySide6-Essentials его нет;
  2. системный синтезатор: Windows - System.Speech через PowerShell (есть в Windows всегда),
     macOS - say, Linux - spd-say, espeak-ng или espeak.
Если ничего нет, available() - False, и кнопки «Прочитать вслух» в карточке нет.
ORGANISM_ATLAS_SPEECH=off отключает чтение (нужно тестам и тем, кому оно мешает)."""

import os
import shutil
import subprocess
import sys
import threading

_backend = None                 # выбранный источник голоса (кэш)
_proc = None                    # процесс системного синтезатора, пока он говорит

# PowerShell: текст - со стандартного ввода в UTF-8 (так не нужно экранировать кавычки), голос - по языку, если есть
_PS = ("[Console]::InputEncoding=[Text.Encoding]::UTF8; Add-Type -AssemblyName System.Speech; "
       "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
       "$v=$s.GetInstalledVoices()|?{$_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq '%s'}|select -First 1; "
       "if($v){$s.SelectVoice($v.VoiceInfo.Name)}; $s.Speak([Console]::In.ReadToEnd())")


def _qt():
    try:
        from PySide6.QtTextToSpeech import QTextToSpeech
    except ImportError:
        return None
    try:
        engine = QTextToSpeech()
    except Exception:
        return None
    return ("qt", engine)


def _system():
    if sys.platform == "win32" and shutil.which("powershell"):
        return ("powershell", None)
    if sys.platform == "darwin" and shutil.which("say"):
        return ("say", None)
    for cmd in ("spd-say", "espeak-ng", "espeak"):
        if shutil.which(cmd):
            return (cmd, None)
    return None


def backend():
    """(имя, движок) первого доступного источника голоса или None"""
    global _backend
    if os.environ.get("ORGANISM_ATLAS_SPEECH", "").lower() in ("off", "0", "no"):
        return None
    if _backend is None:
        _backend = _qt() or _system() or ("", None)
    return _backend if _backend[0] else None


def available():
    return backend() is not None


def _command(name, text, lang):
    """команда системного синтезатора и текст для стандартного ввода (или None)"""
    if name == "powershell":
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS % lang], text
    if name == "say":
        return ["say", text], None
    if name == "spd-say":
        return ["spd-say", "-w", "-l", lang, text], None
    return [name, "-v", lang, text], None


def speak(text, lang="ru"):
    """прочитать text вслух (прежнее чтение прерывается); False - читать нечем"""
    global _proc
    b = backend()
    if b is None or not text:
        return False
    stop()
    name, engine = b
    if name == "qt":
        from PySide6.QtCore import QLocale
        engine.setLocale(QLocale(lang))
        engine.say(text)
        return True
    cmd, stdin = _command(name, text, lang)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)          # на Windows - без окна консоли
    try:
        _proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    except OSError:
        _proc = None
        return False
    if stdin is not None:           # в фоне: PowerShell читает ввод через секунду-другую, а канал вмещает ~4 КБ
        threading.Thread(target=_feed, args=(_proc, stdin.encode("utf-8")), daemon=True).start()
    return True


def _feed(proc, data):
    """отдать текст синтезатору; если его уже остановили (stop), запись просто обрывается"""
    try:
        proc.stdin.write(data)
        proc.stdin.close()
    except (OSError, ValueError):
        pass


def speaking():
    """идёт ли чтение"""
    b = backend()
    if b is None:
        return False
    if b[0] == "qt":
        from PySide6.QtTextToSpeech import QTextToSpeech
        return b[1].state() == QTextToSpeech.State.Speaking
    return _proc is not None and _proc.poll() is None


def stop():
    global _proc
    b = backend()
    if b is not None and b[0] == "qt":
        b[1].stop()
    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
    _proc = None
