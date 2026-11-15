import hashlib
import json
import os
from datetime import datetime, timezone

# Directorio raíz dinámico (portable entre Windows, Linux y Docker)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "venv", "env", "node_modules", ".pytest_cache"}
EXCLUDE_FILES = {"MANIFEST.sha256", "generate_manifest.py", ".env"}


def compute_file_sha256(file_path: str) -> str | None:
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"[!] Error leyendo {file_path}: {e}")
        return None


def generate_repository_manifest() -> None:
    print(f"[*] Analizando repositorio en: {PROJECT_DIR}")
    file_hashes: dict[str, str] = {}
    master_hasher = hashlib.sha256()

    for root, dirs, files in os.walk(PROJECT_DIR):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)

        for file in sorted(files):
            if file in EXCLUDE_FILES or file.endswith((".log", ".tmp")):
                continue

            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, PROJECT_DIR).replace("\\", "/")

            if relative_path.startswith("progress/drafts/") and relative_path.endswith(".json"):
                continue

            file_hash = compute_file_sha256(file_path)
            if file_hash:
                file_hashes[relative_path] = file_hash
                master_hasher.update(f"{relative_path}:{file_hash}".encode("utf-8"))

    master_hash = master_hasher.hexdigest()
    timestamp = datetime.now(timezone.utc).isoformat()

    manifest_data = {
        "project": "Proyecto Hermes v2.0.0",
        "author": "Angelo Recchia",
        "timestamp_utc": timestamp,
        "master_repository_sha256": master_hash,
        "files_manifest": file_hashes,
    }

    manifest_path = os.path.join(PROJECT_DIR, "MANIFEST.sha256")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=4)

    print("\n" + "=" * 60)
    print("[+] MANIFIESTO CRIPTOGRÁFICO GENERADO CON ÉXITO")
    print(f"[+] Archivos sellados: {len(file_hashes)}")
    print(f"[+] Huella Maestra (SHA-256): {master_hash}")
    print(f"[+] Guardado en: {manifest_path}")
    print("=" * 60)
    print("\n[*] Instrucción para Anclaje XRPL:")
    print(
        "    Inserta este Master Hash en el campo 'MemoData' de una transacción de prueba "
        "en la Devnet/Mainnet para sellar tu propiedad intelectual on-chain de forma "
        "descentralizada e infalsificable."
    )


if __name__ == "__main__":
    generate_repository_manifest()