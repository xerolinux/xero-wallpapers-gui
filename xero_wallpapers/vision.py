import importlib.util
import io
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

log = logging.getLogger("xero_wallpapers.vision")

DATA = Path(__file__).resolve().parent / "data"
PROMPTS = DATA / "clip_prompts.json"
# CLIP ViT-B/32 image encoder (Xenova/clip-vit-base-patch32, MIT); packaging puts it here, git does not track it.
MODEL = DATA / "models" / "clip-vision.onnx"
SIZE = 224
MEAN = (0.48145466, 0.4578275, 0.40821073)
STD = (0.26862954, 0.26130258, 0.27577711)
# Tuned by hand on 163 labelled thumbnails from the built-in sources (packaging/clip/make_prompts.py has the prompts):
# 85 of 87 people/anime/cartoon pictures caught, 4 of 76 others hidden by mistake.
LOGIT_SCALE = 50.0
THRESHOLD = 0.34

# One picture at a time on two cores: fast enough for a page of results without spinning up the fans.
EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vision")
_lock = threading.Lock()
_state: dict = {}


def _load():
    with _lock:
        if "ready" in _state:
            return _state if _state["ready"] else None
        _state["ready"] = False
        try:
            import numpy as np
            import onnxruntime
        except ImportError:
            log.info("onnxruntime is not installed; No anime uses words and tags only")
            return None
        if not MODEL.is_file():
            log.info("the CLIP model is missing at %s; No anime uses words and tags only", MODEL)
            return None
        try:
            prompts = json.loads(PROMPTS.read_text())
            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 2
            session = onnxruntime.InferenceSession(str(MODEL), options, providers=["CPUExecutionProvider"])
        except Exception as e:
            log.warning("couldn't load the CLIP model: %s", e)
            return None
        _state.update(
            ready=True, np=np, session=session, blocked=int(prompts["blocked"]),
            text=np.asarray(prompts["embeddings"], dtype=np.float32),
        )
        return _state


def installed() -> bool:
    # Cheap check for the UI; loading the model happens on the vision thread.
    return MODEL.is_file() and importlib.util.find_spec("onnxruntime") is not None


def _pixels(np, data: bytes):
    image = Image.open(io.BytesIO(data))
    image.draft("RGB", (SIZE * 2, SIZE * 2))
    image = image.convert("RGB")
    w, h = image.size
    scale = SIZE / min(w, h)
    image = image.resize((max(SIZE, round(w * scale)), max(SIZE, round(h * scale))), Image.Resampling.BICUBIC)
    left, top = (image.width - SIZE) // 2, (image.height - SIZE) // 2
    image = image.crop((left, top, left + SIZE, top + SIZE))
    array = (np.asarray(image, dtype=np.float32) / 255.0 - MEAN) / STD
    return array.transpose(2, 0, 1)[None].astype(np.float32)


def blocked_share(data: bytes) -> float | None:
    """Probability (0-1) that the picture shows people, anime or cartoon characters; None without the model."""
    state = _load()
    if state is None:
        return None
    np = state["np"]
    embed = state["session"].run(None, {"pixel_values": _pixels(np, data)})[0][0]
    embed = embed / np.linalg.norm(embed)
    logits = LOGIT_SCALE * state["text"] @ embed
    probs = np.exp(logits - logits.max())
    probs /= probs.sum()
    return float(probs[: state["blocked"]].sum())


def looks_blocked(data: bytes) -> bool | None:
    share = blocked_share(data)
    return None if share is None else share >= THRESHOLD
