import os
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from dotenv import dotenv_values

from api_quotex import login

LOGIN_HELPER_PATH = Path(__file__).parents[1] / "login.py"
LOGIN_HELPER_SPEC = importlib.util.spec_from_file_location("quotex_login_helper", LOGIN_HELPER_PATH)
assert LOGIN_HELPER_SPEC and LOGIN_HELPER_SPEC.loader
login_helper = importlib.util.module_from_spec(LOGIN_HELPER_SPEC)
LOGIN_HELPER_SPEC.loader.exec_module(login_helper)


class SessionEnvironmentTests(unittest.IsolatedAsyncioTestCase):
    def test_trade_url_identifies_demo_and_live_routes(self):
        for infer_mode in (login._infer_is_demo_from_url, login_helper._infer_is_demo_from_url):
            self.assertIs(infer_mode("https://quotex.com/en/demo-trade"), True)
            self.assertIs(infer_mode("https://qxbroker.com/en/trade"), False)
            self.assertIsNone(infer_mode("https://quotex.com/en/sign-in/"))
            self.assertIsNone(infer_mode("https://example.com/en/demo-trade"))

    def test_selected_mode_builds_expected_trade_url(self):
        demo_bot = login_helper.QuotexBot(is_demo=True)
        live_bot = login_helper.QuotexBot(is_demo=False)
        self.assertEqual(login_helper._trade_url(demo_bot.is_demo), "https://quotex.com/en/demo-trade")
        self.assertEqual(login_helper._trade_url(live_bot.is_demo), "https://quotex.com/en/trade")

    def test_save_session_persists_ssid_to_env(self):
        ssid = '42["authorization",{"session":"synthetic","isDemo":1,"tournamentId":0}]'
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / ".env"
            env_file.write_text("QUOTEX_EMAIL=test@example.com\n", encoding="utf-8")
            with (
                patch.object(login, "ENV_FILE", env_file),
                patch.object(login, "Config") as config_class,
                patch.dict(os.environ, {}, clear=False),
            ):
                login.save_session({"ssid": ssid})
                self.assertEqual(os.environ["QUOTEX_SSID"], ssid)

            self.assertEqual(dotenv_values(env_file)["QUOTEX_SSID"], ssid)
            self.assertEqual(dotenv_values(env_file)["QUOTEX_EMAIL"], "test@example.com")
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
            config_class.return_value.save_session.assert_called_once_with({"ssid": ssid})

    async def test_get_ssid_reuses_valid_env_ssid(self):
        ssid = '42["authorization",{"session":"synthetic","isDemo":1,"tournamentId":0}]'
        with (
            patch.object(login, "load_session", return_value={}),
            patch.dict(os.environ, {"QUOTEX_SSID": ssid}),
            patch.object(login, "validate_ssid", new_callable=AsyncMock, return_value=True),
            patch.object(login, "save_session") as save_session,
        ):
            success, session_data = await login.get_ssid(is_demo=True)

        self.assertTrue(success)
        self.assertEqual(session_data, {"ssid": ssid, "is_demo": True})
        save_session.assert_called_once_with(session_data)


if __name__ == "__main__":
    unittest.main()
