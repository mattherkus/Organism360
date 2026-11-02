"""Чтение вслух: выбор источника голоса и команды системных синтезаторов (без настоящего звука)."""

import os
import unittest
from unittest import mock

from organism_atlas import speech


class SpeechTests(unittest.TestCase):
    def setUp(self):
        speech._backend = None
        self.addCleanup(setattr, speech, "_backend", None)

    def test_off_by_environment(self):
        with mock.patch.dict(os.environ, {"ORGANISM_ATLAS_SPEECH": "off"}):
            self.assertFalse(speech.available())
            self.assertFalse(speech.speak("текст"))

    def test_system_commands(self):
        cmd, stdin = speech._command("powershell", "Сердце «насос»", "ru")
        self.assertEqual(cmd[0], "powershell")
        self.assertEqual(stdin, "Сердце «насос»")                    # текст - через ввод, без экранирования
        self.assertIn("'ru'", cmd[-1])
        self.assertEqual(speech._command("say", "Heart", "en"), (["say", "Heart"], None))
        self.assertEqual(speech._command("spd-say", "Сердце", "ru")[0], ["spd-say", "-w", "-l", "ru", "Сердце"])
        self.assertEqual(speech._command("espeak", "Сердце", "ru")[0], ["espeak", "-v", "ru", "Сердце"])

    def test_speak_and_stop_with_system_tool(self):
        proc = mock.Mock()
        proc.poll.return_value = None
        with mock.patch.dict(os.environ, {"ORGANISM_ATLAS_SPEECH": ""}), \
                mock.patch.object(speech, "_qt", return_value=None), \
                mock.patch.object(speech, "_system", return_value=("espeak", None)), \
                mock.patch.object(speech.subprocess, "Popen", return_value=proc) as popen:
            self.assertTrue(speech.available())
            self.assertTrue(speech.speak("Печень", "ru"))
            self.assertEqual(popen.call_args[0][0], ["espeak", "-v", "ru", "Печень"])
            self.assertTrue(speech.speaking())
            speech.stop()
            proc.terminate.assert_called_once()
            self.assertFalse(speech.speaking())


if __name__ == "__main__":
    unittest.main()
