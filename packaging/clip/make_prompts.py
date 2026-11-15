#!/usr/bin/env python3
"""Precompute the CLIP text embeddings for the No anime filter into xero_wallpapers/data/clip_prompts.json.

Usage: make_prompts.py <text_model.onnx> <tokenizer.json>   (needs onnxruntime, numpy and tokenizers)
Both files come from https://huggingface.co/Xenova/clip-vit-base-patch32 (MIT); the app only ships the vision model.
"""
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime
from tokenizers import Tokenizer

BLOCKED = [
    "a photo of a person", "a portrait of a woman", "a portrait of a man", "a group of people",
    "a girl", "a boy", "a human face", "a model posing", "a soldier", "a warrior with a sword",
    "an anime character", "an anime girl", "an anime illustration", "a manga drawing", "a chibi character",
    "a cartoon character", "a cartoon illustration", "a video game character", "a superhero", "a cosplay photo",
    "a 3d rendered character", "a fantasy character", "a vtuber",
    "a beautiful anime girl with long hair", "an anime girl sitting in a room", "a digital painting of a woman",
    "a woman standing", "a man standing", "a person in a hoodie", "a character in armor", "spider-man",
    "a masked person", "a stylized illustration of a person", "a girl looking out a window", "a figure in a scene",
    "a soldier in a helmet",
]
ALLOWED = [
    "a landscape", "a photo of nature", "mountains", "a forest", "the ocean", "a beach", "a sunset sky",
    "a city skyline", "a city at night", "a street at night", "a car", "a sports car", "a motorcycle",
    "an abstract pattern", "abstract shapes", "outer space", "a galaxy", "a planet", "an animal", "a cat",
    "a dog", "a bird", "architecture", "a building", "a minimalist wallpaper", "a dark wallpaper",
    "a logo", "a futuristic city", "a room interior", "a video game landscape", "a skull", "a robot",
    "flowers", "a castle", "pixel art scenery", "a technology wallpaper",
    "a sword", "a katana", "a black hole", "a dark abstract wallpaper", "a black background", "a glowing light",
    "a moon", "an empty room", "a video game logo", "text on a dark background", "a sports car at night",
    "a race car", "a lake", "a waterfall", "a cherry blossom tree", "a skeleton", "a pumpkin",
]
OUT = Path(__file__).resolve().parents[2] / "xero_wallpapers" / "data" / "clip_prompts.json"


def main(model: str, tokenizer_file: str):
    tok = Tokenizer.from_file(tokenizer_file)
    session = onnxruntime.InferenceSession(model)
    prompts = BLOCKED + ALLOWED
    ids = [tok.encode(p).ids for p in prompts]
    width = max(map(len, ids))
    end = ids[0][-1]
    batch = np.array([i + [end] * (width - len(i)) for i in ids], dtype=np.int64)
    emb = session.run(None, {"input_ids": batch})[0]
    emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
    OUT.write_text(json.dumps({
        "blocked": len(BLOCKED),
        "prompts": prompts,
        "embeddings": [[round(float(x), 6) for x in row] for row in emb],
    }))
    print(f"wrote {OUT} ({len(prompts)} prompts)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
