"""Read-only credential/connectivity check. Never prints credentials or data."""
import json
import os
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def endpoint(value):
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"libsql", "https"} or not parsed.hostname:
        raise ValueError("TURSO_DATABASE_URL debe empezar por libsql:// o https://")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("La URL no debe contener credenciales ni parámetros")
    if not parsed.hostname.endswith(".turso.io") or parsed.port not in (None, 443):
        raise ValueError("Se requiere un dominio de Turso Cloud con HTTPS")
    if parsed.path not in ("", "/"):
        raise ValueError("Usa la Database URL sin rutas adicionales")
    return f"https://{parsed.hostname}/v2/pipeline"


def check(url, token):
    if not token.strip():
        raise ValueError("Falta TURSO_AUTH_TOKEN")
    payload = {"requests": [
        {"type": "execute", "stmt": {"sql": "SELECT 1 AS connection_ok", "want_rows": True}},
        {"type": "close"},
    ]}
    req = Request(endpoint(url), data=json.dumps(payload).encode(), method="POST",
                  headers={"Authorization": "Bearer " + token.strip(), "Content-Type": "application/json"})
    with urlopen(req, timeout=20) as response:
        result = json.load(response)
    first = result.get("results", [{}])[0]
    if first.get("type") != "ok":
        raise ValueError("Turso rechazó la consulta de comprobación")
    rows = first.get("response", {}).get("result", {}).get("rows", [])
    if not rows or str(rows[0][0].get("value")) != "1":
        raise ValueError("Respuesta inesperada de Turso")


def main():
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    try:
        check(os.getenv("TURSO_DATABASE_URL", ""), os.getenv("TURSO_AUTH_TOKEN", ""))
    except HTTPError as exc:
        print(f"Conexión rechazada (HTTP {exc.code}). Revisa URL, permisos y vencimiento del token.")
        return 1
    except (URLError, TimeoutError):
        print("No se pudo conectar a Turso. Revisa la red y el dominio.")
        return 1
    except ValueError as exc:
        print(str(exc))
        return 1
    print("Turso: conexión y lectura correctas. No se modificaron datos.")
    print("Esto no confirma todavía la migración del bot ni permisos de escritura.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
