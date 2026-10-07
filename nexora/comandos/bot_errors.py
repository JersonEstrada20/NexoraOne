import html


def api_error_text(action: str, status: int, data=None) -> str:
    payload = data if isinstance(data, dict) else {}
    raw = str(payload.get("message") or payload.get("error") or "").strip()
    if status == 599:
        title = "No se pudo conectar con el servicio web."
        hint = "Revisa que el servicio web esté Online y que API_BASE apunte al dominio correcto."
    elif status in {401, 403}:
        title = "La API rechazó la solicitud."
        hint = "Revisa que NEXORA_INTERNAL_API_KEY sea igual en web y worker."
    elif status == 404 and "usuario" in raw.lower() and "no encontrado" in raw.lower():
        title = "Usuario no encontrado en la base."
        hint = "Ese ID debe usar /register primero, o verifica que el ID esté bien escrito."
    elif status == 404:
        title = "Recurso no encontrado en la API."
        hint = raw or "Puede faltar deploy o el worker está llamando un endpoint viejo."
    elif status >= 500:
        title = f"El servicio web devolvió error {status}."
        hint = "Mira Deploy Logs y la sección Sistema del panel para ver el traceback."
    elif status >= 400:
        title = f"La API respondió {status}."
        hint = raw or "Revisa los datos enviados al comando."
    else:
        title = "La API no respondió como se esperaba."
        hint = raw or "Intenta de nuevo y revisa /status."
    # Server exception text can contain tokens, URLs or personal data.
    detail = hint if status >= 500 or status in {401, 403} else (raw if raw and raw != hint else hint)
    return (
        f"<b>NEXORA ONE ⇒ ERROR API</b>\n"
        f"Acción: <code>{html.escape(action)}</code>\n"
        f"Código: <code>{status}</code>\n"
        f"Estado: {html.escape(title)}\n"
        f"Detalle: {html.escape(detail[:700])}\n\n"
        f"Sugerencia: {html.escape(hint)}"
    )
