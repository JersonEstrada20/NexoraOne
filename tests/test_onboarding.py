import unittest
from unittest.mock import AsyncMock, patch

from aiogram.types import Chat, User
from nexora.comandos import utils
from app.handlers import menu


class AccountGuidanceTests(unittest.TestCase):
    def test_missing_account_is_distinct_and_actionable(self):
        with patch.object(utils, "API_BASE", "https://example.test"), patch.object(
            utils, "fetch_api_json", return_value=(404, {"status": "error"})
        ):
            active, info = utils.verificar_usuario("123")
        self.assertFalse(active)
        self.assertEqual("missing", info["_account_state"])
        message = utils.account_access_message(info)
        self.assertIn("/register", message)
        self.assertIn("gratuito", message)

    def test_inactive_account_is_not_told_to_register_again(self):
        payload = {"data": {"ESTADO": "INACTIVO"}}
        with patch.object(utils, "API_BASE", "https://example.test"), patch.object(
            utils, "fetch_api_json", return_value=(200, payload)
        ):
            active, info = utils.verificar_usuario("123")
        self.assertFalse(active)
        self.assertEqual("inactive", info["_account_state"])
        message = utils.account_access_message(info)
        self.assertIn("@OficialNexora", message)
        self.assertNotIn("/register", message)

    def test_service_failure_is_not_reported_as_missing_account(self):
        with patch.object(utils, "API_BASE", "https://example.test"), patch.object(
            utils, "fetch_api_json", return_value=(503, {})
        ):
            active, info = utils.verificar_usuario("123")
        self.assertFalse(active)
        self.assertEqual("unavailable", info["_account_state"])
        message = utils.account_access_message(info)
        self.assertIn("no responde", message)
        self.assertNotIn("/register", message)

    def test_unconfigured_api_is_reported_as_unavailable(self):
        with patch.object(utils, "API_BASE", ""):
            active, info = utils.verificar_usuario("123")
        self.assertFalse(active)
        self.assertEqual("unavailable", info["_account_state"])


class MenuOnboardingTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_greets_user_and_shows_registration_button(self):
        user = User(id=123, is_bot=False, first_name="Ana")
        message = AsyncMock()
        message.chat = Chat(id=123, type="private")
        message.from_user = user
        message.bot = AsyncMock()
        with patch.object(menu, "get_settings", AsyncMock(return_value={"language": "es"})), patch.object(
            menu, "menu_role", AsyncMock(return_value="user")
        ):
            await menu.start(message)
        text = message.reply.await_args.args[0]
        markup = message.reply.await_args.kwargs["reply_markup"]
        callbacks = {button.callback_data for row in markup.inline_keyboard for button in row}
        self.assertIn("Ana", text)
        self.assertIn("/register", text)
        self.assertIn("unified:0:register", callbacks)

    def test_home_labels_match_selected_language(self):
        es = [button.text for row in menu.menu_keyboard(language="es", role="user").inline_keyboard for button in row]
        en = [button.text for row in menu.menu_keyboard(language="en", role="user").inline_keyboard for button in row]
        self.assertIn("📝 Crear cuenta gratis", es)
        self.assertNotIn("📝 Register", es)
        self.assertIn("📝 Register", en)
        self.assertNotIn("📝 Crear cuenta gratis", en)


if __name__ == "__main__":
    unittest.main()
