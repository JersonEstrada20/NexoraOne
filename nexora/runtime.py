"""Compatibility boundary: service handlers run without a second poller."""
import asyncio
import logging
import time
import secrets
import traceback
from telegram import Update
from telegram.ext import Application, CallbackContext
from nexora.comandos import admin_ops, admin_requests, admin_tools, broadcast, buy, cmds, compras, genkey, helpadmin, historial, me, precios, setup, system_ops, terminos
from nexora.comandos.request_catalog import REQUEST_COMMANDS, make_request_command
from nexora.comandos.utils import API_BASE, fetch_api_json_async
from app.config import OWNER_USER_ID

PUBLIC = {"buy": buy.buy_command, "compras": compras.compras_command,
          "precios": precios.precios_command, "redeem": genkey.redeem,
          "terminos": terminos.terminos_command}
ADMIN = {name: getattr(admin_ops, name + "_command") for name in
         ("setcred", "cred", "uncred", "setsub", "sub", "unsub", "setrol", "setantispam")}
ADMIN.update({"dm": admin_tools.dm_command, "user": admin_tools.user_command,
              "solicitudes": admin_requests.pending_requests_command,
              "ventas": admin_tools.ventas_command, "errores": admin_tools.errores_command,
              "global": broadcast.global_command, "genkey": genkey.genkey,
              "keyslog": genkey.keyslog, "keysinfo": genkey.keysinfo,
              "reply": admin_requests.reply_request, "pending": admin_requests.pending_requests_command,
              "close": admin_requests.close_request, "done": admin_requests.done_request,
              "fail": admin_requests.fail_request, "templates": admin_requests.templates_command,
              "rquick": admin_requests.quick_reply_command, "requestlog": admin_requests.request_log_command,
              "reopen": admin_requests.reopen_request,
              "status": system_ops.status_command})
COMMANDS = {**PUBLIC, **ADMIN, "me": me.me_command}
COMMANDS.update({name: make_request_command(name, cost, category, validation)
                 for name, cost, category, validation in REQUEST_COMMANDS})
ACTIONS = {"catalog": cmds.cmds_command, "buy": buy.buy_command, "account": me.me_command,
           "history": historial.historial_command, "admin": helpadmin.admin_menu_command,
           "web": system_ops.panel_command, "health": system_ops.status_command,
           "setup": setup.setup_command}
CALLBACKS = {"cmds_": cmds.cmds_callback, "buy:": buy.buy_callback,
              "global_": broadcast.global_callback, "admintool:": admin_tools.admin_tools_callback,
              "adminreq:": admin_requests.request_buttons_callback,
             "adminmenu:": helpadmin.admin_menu_callback}


class ServiceRuntime:
    def __init__(self):
        self.application = None
        self.calls = {}

    async def start(self, token):
        if not API_BASE:
            return
        admin_requests.init_db()
        self.application = Application.builder().token(token).updater(None).build()
        await self.application.initialize()
        await self.application.start()

    async def stop(self):
        if self.application:
            await self.application.stop()
            await self.application.shutdown()

    def waiting_for_owner(self, user_id):
        if not self.application:
            return False
        return bool(self.application.user_data.get(user_id, {}).get(admin_requests.REQUEST_ACTION_KEY))

    @staticmethod
    def log_failure(message, reference, error, handler=None):
        """Log source locations and error type, never exception text or payloads."""
        frames = "".join(traceback.format_list(traceback.extract_tb(error.__traceback__)))
        logging.error(
            "%s referencia=%s tipo=%s handler=%s\n%s",
            message,
            reference,
            type(error).__name__,
            getattr(handler, "__name__", "unknown"),
            frames,
        )

    async def report_failure(self, event, reference, update=None):
        """Report a failed dispatch without leaking internals or masking the original error."""
        if hasattr(event, "data") and hasattr(event, "message"):
            try:
                await event.answer(
                    f"No se pudo confirmar la operación. Referencia: {reference}. "
                    "Revisa si se aplicó antes de repetirla.",
                    show_alert=True,
                )
                return
            except Exception as exc:
                self.log_failure("No se pudo mostrar el aviso del callback", reference, exc)

        message = getattr(update, "effective_message", None) if update else None
        message = message or getattr(event, "message", None) or event
        reply = getattr(message, "reply_text", None) or getattr(message, "answer", None)
        if reply:
            try:
                await reply(
                    f"No pude confirmar la operación. Referencia: {reference}.\n"
                    "Si modificaba créditos o enviaba una respuesta, revisa el resultado antes de repetirla."
                )
            except Exception as exc:
                self.log_failure("No se pudo responder el fallo", reference, exc)

    async def persist_failure(self, reference, error, stage, handler=None):
        """Store a searchable, payload-free worker error record in the API service."""
        try:
            frames = "".join(traceback.format_list(traceback.extract_tb(error.__traceback__)))
            await fetch_api_json_async(
                "/internal/admin/worker-error",
                timeout=5,
                method="POST",
                payload={
                    "reference": reference,
                    "stage": stage,
                    "handler": getattr(handler, "__name__", "unknown"),
                    "error_type": type(error).__name__,
                    "traceback": frames[-6000:],
                },
            )
        except Exception:
            logging.warning("No se pudo sincronizar la referencia de error %s", reference)

    async def invoke(self, event, action=None):
        if not self.application:
            message = getattr(event, "message", None) or event
            await message.answer("El servicio de cuentas todavía no está conectado. El dueño debe configurar NEXORA_API_BASE.")
            return
        is_callback = hasattr(event, "data") and hasattr(event, "message")
        command = ""
        try:
            if is_callback and action is None:
                payload = {
                    "update_id": 0,
                    "callback_query": event.model_dump(
                        mode="json",
                        by_alias=True,
                        exclude_none=True,
                        fallback=lambda _value: None,
                    ),
                }
                handler = next((fn for prefix, fn in CALLBACKS.items() if event.data.startswith(prefix)), None)
            else:
                message = event.message if is_callback else event
                raw = message.model_dump(mode="json", by_alias=True, exclude_none=True)
                raw["from"] = event.from_user.model_dump(mode="json", exclude_none=True)
                raw.pop("from_user", None)
                if action:
                    raw["text"] = "/" + action
                    raw.pop("entities", None)
                payload = {"update_id": 0, "message": raw}
                text = raw.get("text", "")
                command = text.split()[0].split("@")[0].lstrip("/") if text.startswith("/") else ""
                handler = ACTIONS.get(action) if action else COMMANDS.get(command)
                if not handler and self.waiting_for_owner(event.from_user.id):
                    handler = admin_requests.admin_followup_message if text else admin_requests.forward_file

            if not handler:
                return
            update = Update.de_json(payload, self.application.bot)
            context = CallbackContext.from_update(update, self.application)
            context.args = [] if action or is_callback else (update.effective_message.text or "").split()[1:]
        except Exception as exc:
            reference = secrets.token_hex(4).upper()
            self.log_failure(
                "No se pudo preparar el evento " + ("callback" if is_callback else "message"),
                reference,
                exc,
            )
            await self.persist_failure(reference, exc, "prepare_event")
            await self.report_failure(event, reference)
            return
        privileged = (action in {"admin", "web", "health", "setup"}
                      or (not is_callback and not action and command in ADMIN)
                      or (is_callback and action is None and event.data.startswith(("global_", "admintool:", "adminreq:", "adminmenu:"))))
        if privileged and event.from_user.id != OWNER_USER_ID:
            return
        if not action and not is_callback and command not in ADMIN:
            key = (event.from_user.id, command)
            now = time.monotonic()
            if now - self.calls.get(key, -100) < 2:
                await event.reply("Espera un momento antes de repetir la solicitud.")
                return
            self.calls[key] = now
        try:
            await handler(update, context)
        except Exception as exc:
            reference = secrets.token_hex(4).upper()
            self.log_failure("Error en módulo de servicios", reference, exc, handler)
            await self.persist_failure(reference, exc, "handler", handler)
            await self.report_failure(event, reference, update)


runtime = ServiceRuntime()
