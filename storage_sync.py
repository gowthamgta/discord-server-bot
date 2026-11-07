"""
Keeps data/ alive across Hugging Face Space restarts by mirroring it to a private HF dataset repo.

Set two Space Secrets to enable it:
  HF_TOKEN  - a Hugging Face access token with *write* permission
  DATA_REPO - dataset repo to store data in, e.g. "your-username/kralveth-bot-data" (created automatically, private)
Without them (e.g. when running locally) every function here is a no-op.
"""
import hashlib
import logging
import os
from config import DATA_DIR

logger = logging.getLogger("StorageSync")

SYNCED_FILES = ["server_data.json", "persona.txt"]

HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
DATA_REPO = os.getenv("DATA_REPO", "").strip()

_last_uploaded = {}  # filename: sha256 of the last uploaded content


def is_enabled() -> bool:
    return bool(HF_TOKEN and DATA_REPO)


def _api():
    from huggingface_hub import HfApi
    return HfApi(token=HF_TOKEN)


def _digest(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return None


def restore():
    """Downloads the saved data files into data/. Call once at startup, before anything reads data/."""
    if not is_enabled():
        logger.info("Storage sync disabled (HF_TOKEN / DATA_REPO not set). Data lives only on this disk.")
        return
    from huggingface_hub import hf_hub_download
    from huggingface_hub.utils import EntryNotFoundError, RepositoryNotFoundError

    try:
        _api().create_repo(DATA_REPO, repo_type="dataset", private=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Could not create/access dataset {DATA_REPO}: {e}")
        return

    for name in SYNCED_FILES:
        try:
            cached = hf_hub_download(DATA_REPO, name, repo_type="dataset", token=HF_TOKEN, force_download=True)
            with open(cached, "rb") as src:
                content = src.read()
            with open(os.path.join(DATA_DIR, name), "wb") as dst:
                dst.write(content)
            _last_uploaded[name] = hashlib.sha256(content).hexdigest()
            logger.info(f"Restored {name} from {DATA_REPO}")
        except (EntryNotFoundError, RepositoryNotFoundError):
            logger.info(f"No saved {name} in {DATA_REPO} yet; keeping the bundled copy.")
        except Exception as e:
            logger.error(f"Failed to restore {name}: {e}")


def upload_changes() -> int:
    """Uploads any data file that changed since the last upload. Blocking; run it in a thread."""
    if not is_enabled():
        return 0
    from huggingface_hub import CommitOperationAdd

    ops = []
    pending = {}
    for name in SYNCED_FILES:
        path = os.path.join(DATA_DIR, name)
        digest = _digest(path)
        if digest and digest != _last_uploaded.get(name):
            ops.append(CommitOperationAdd(path_in_repo=name, path_or_fileobj=path))
            pending[name] = digest
    if not ops:
        return 0
    try:
        _api().create_commit(DATA_REPO, repo_type="dataset", operations=ops,
                             commit_message=f"Bot data sync: {', '.join(pending)}")
        _last_uploaded.update(pending)
        logger.info(f"Synced {', '.join(pending)} to {DATA_REPO}")
    except Exception as e:
        logger.error(f"Data sync upload failed: {e}")
        return 0
    return len(ops)
