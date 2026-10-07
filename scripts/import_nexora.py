"""Import application assets only; never import databases, Git or secrets."""
from pathlib import Path
import sys
import zipfile


def import_archive(archive_path, destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for item in archive.infolist():
            relative = Path(item.filename).parts
            if len(relative) < 2 or relative[0] != "Nexora Bot" or item.is_dir():
                continue
            relative = Path(*relative[1:])
            if relative.parts[0] == "comandos" and relative.name in {"start.py", "register.py", "rules.py", "cmdsadmin.py"}:
                continue
            if relative.parts[0] in {"comandos", "templates", "default_assets"}:
                target = destination / relative
            elif str(relative) in {"app.py", "storage.py", "config.example.json"}:
                target = destination / ("web.py" if str(relative) == "app.py" else relative)
            else:
                continue
            if not target.resolve().is_relative_to(destination) or target.exists():
                raise ValueError(f"Unsafe or existing target: {target.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            data = archive.read(item)
            if target.suffix == ".py":
                text = data.decode("utf-8-sig").replace("\r\r\n", "\n").replace("\r\n", "\n")
                text = text.replace("from comandos", "from nexora.comandos").replace("from storage import", "from nexora.storage import")
                data = text.encode("utf-8")
            target.write_bytes(data)


if __name__ == "__main__":
    import_archive(sys.argv[1], Path(__file__).resolve().parents[1] / "nexora")
