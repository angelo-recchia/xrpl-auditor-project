import os
import hashlib
import json
from datetime import datetime, timezone

# Directorio raíz del proyecto Hermes
PROJECT_DIR = r"C:\Users\user\Desktop\xrpl-auditor-project"
EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "env", "node_modules"}
EXCLUDE_FILES = {"MANIFEST.sha256", "generate_manifest.py"}

def compute_file_sha256(file_path):
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"[!] Error leyendo {file_path}: {e}")
        return None

def generate_repository_manifest():
    print(f"[*] Analizando repositorio en: {PROJECT_DIR}")
    file_hashes = {}
    master_hasher = hashlib.sha256()

    for root, dirs, files in os.walk(PROJECT_DIR):
        # Filtrar directorios excluidos
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            if file in EXCLUDE_FILES:
                continue
            
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, PROJECT_DIR)
            
            file_hash = compute_file_sha256(file_path)
            if file_hash:
                file_hashes[relative_path] = file_hash
                master_hasher.update(file_hash.encode('utf-8'))

    master_hash = master_hasher.hexdigest()
    timestamp = datetime.now(timezone.utc).isoformat()

    manifest_data = {
        "project": "Proyecto Hermes v1.2.0",
        "author": "Angelo Recchia",
        "timestamp_utc": timestamp,
        "master_repository_sha256": master_hash,
        "files_manifest": file_hashes
    }

    manifest_path = os.path.join(PROJECT_DIR, "MANIFEST.sha256")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=4)

    print("\n" + "="*60)
    print(f"[+] MANIFIESTO CRIPTOGRÁFICO GENERADO CON ÉXITO")
    print(f"[+] Huella Maestro (SHA-256): {master_hash}")
    print(f"[+] Guardado en: {manifest_path}")
    print("="*60)
    print("\n[*] Instrucción para Anclaje XRPL:")
    print(f"    Inserta este Master Hash en el campo 'MemoData' de una transacción de prueba en la Devnet/Mainnet para sellar tu propiedad intelectual on-chain de forma descentralizada e infalsificable.")

if __name__ == "__main__":
    generate_repository_manifest()
