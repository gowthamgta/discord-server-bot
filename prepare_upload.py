"""
Builds hf_upload/ with exactly the files the Hugging Face Space needs, ready to copy-paste.
Run it again after any code change:  python prepare_upload.py
Secrets (.env) and PC-only files are never copied.
"""
import os
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "hf_upload")

FILES = [
    "app.py", "bot.py", "checks.py", "config.py", "data_manager.py", "emojis.py", "owner_actions.py",
    "rate_limiter.py", "storage_sync.py", "utils.py",
    "requirements.txt", "README.md", ".env.example", ".gitignore",
    "data/persona.txt",
]
# Upload this one only until HF data sync is running; after that the dataset copy is the live data
SEED_DATA = "data/server_data.json"
NEVER = {".env"}


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    copied = []
    for rel in FILES + [f"cogs/{f}" for f in sorted(os.listdir(os.path.join(BASE, "cogs"))) if f.endswith(".py")]:
        dst = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(BASE, rel), dst)
        copied.append(rel)
    if os.path.exists(os.path.join(BASE, SEED_DATA)):
        shutil.copy2(os.path.join(BASE, SEED_DATA), os.path.join(OUT, SEED_DATA))
        copied.append(SEED_DATA)

    leaked = [p for p in copied if os.path.basename(p) in NEVER]
    assert not leaked, f"Refusing to include secrets: {leaked}"
    print(f"Built {OUT} with {len(copied)} files:")
    for rel in copied:
        print("  " + rel)
    print(f"\nNote: {SEED_DATA} is included. Once HF data sync is running, delete it from hf_upload before uploading.")


if __name__ == "__main__":
    main()
