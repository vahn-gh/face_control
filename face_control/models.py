"""Locate (and download on first use) the MediaPipe model files."""

import logging
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
_BASE = "https://storage.googleapis.com/mediapipe-models"
POSE_MODEL = (
    "pose_landmarker_lite.task",
    f"{_BASE}/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
)
FACE_MODEL = (
    "face_landmarker.task",
    f"{_BASE}/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
)


def ensure_model(model: tuple[str, str]) -> Path:
    name, url = model
    path = MODELS_DIR / name
    if path.exists():
        return path
    log.info("Downloading model %s", name)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    try:
        urllib.request.urlretrieve(url, tmp)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Could not download {name} from {url}: {e}") from e
    tmp.rename(path)
    return path
