"""Instala únicamente la imagen y el hook de reposo; conserva copia de archivos previos."""
import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent


def configure_sleep(source):
    """Edit only the known top-level scalar keys in KOReader's settings file."""
    if not re.search(r"^return \{\s*$", source, re.M) or not source.rstrip().endswith("}"):
        raise ValueError("Formato de ajustes inesperado; configura la imagen desde KOReader")
    values = {
        "screensaver_type": '"document_cover"',
        "screensaver_document_cover": '"/mnt/us/koreader/conil.png"',
        "screensaver_show_message": "false",
    }
    for key, value in values.items():
        pattern = r'^    \["' + key + r'"\] = (?:"[^"\n]*"|true|false),\s*$'
        replacement = '    ["' + key + '"] = ' + value + ','
        updated, count = re.subn(pattern, lambda match: replacement, source, flags=re.M)
        if count > 1:
            raise ValueError("Ajuste duplicado: " + key)
        if count:
            source = updated
        else:
            if '["' + key + '"]' in source:
                raise ValueError("Ajuste con formato inesperado: " + key)
            index = source.rfind("}")
            source = source[:index] + replacement + "\n" + source[index:]
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="URL del PNG accesible desde el Kindle")
    parser.add_argument("--kindle", type=Path, default=Path("/Volumes/Kindle"))
    parser.add_argument("--configure-sleep", action="store_true", help="Seleccionar el panel como imagen de reposo y ocultar Sleeping")
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or any(c in args.url for c in '\\"\n\r'):
        parser.error("URL HTTP(S) inválida")
    r = args.kindle
    if not r.is_mount() or not (r / "koreader/git-rev").is_file():
        parser.error("No se encuentra una unidad Kindle montada con KOReader")
    if not (HERE / "output/conil.png").is_file():
        parser.error("Genera primero la imagen con panel.py render")
    backup = HERE / "backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
    files = {
        "koreader/patches/2-conil-sleepscreen.lua": (HERE / "kindle/2-conil-sleepscreen.lua").read_bytes(),
        "koreader/settings/conil-config.lua": ('return { url = "' + args.url + '" }\n').encode(),
        "koreader/conil.png": (HERE / "output/conil.png").read_bytes(),
    }
    if args.configure_sleep:
        settings = r / "koreader/settings.reader.lua"
        if not settings.is_file():
            parser.error("No se encuentran los ajustes de KOReader")
        files["koreader/settings.reader.lua"] = configure_sleep(settings.read_text()).encode()
    for rel in [*files, "koreader/settings.reader.lua"]:
        src = r / rel
        if src.is_file():
            dest = backup / rel; dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
    for rel, data in files.items():
        dst = r / rel; dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        tmp.write_bytes(data); tmp.replace(dst)
        assert dst.read_bytes() == data
        aux = dst.parent / ("._" + dst.name)
        if aux.is_file(): aux.unlink()
    print("Copiados y verificados", len(files), "archivos. Reinicia KOReader.")
    if not args.configure_sleep:
        print("Selecciona conil.png como imagen de reposo en los ajustes de KOReader.")
    print("Copia de archivos previos:", backup)


if __name__ == "__main__": main()
