"""Helpers for building synthetic GGUF files in tests.

A real model is ~2 GB, so the integrity tests use tiny hand-built files with a
correct header and a real (if trivial) tensor table.
"""
from __future__ import annotations

import struct

ALIGNMENT = 32


def build_gguf(*, tensors: int = 1, elements: int = 4, alignment: int = ALIGNMENT) -> bytes:
    """A minimal, well-formed GGUF file with `tensors` F32 tensors."""
    out = bytearray()
    out += b"GGUF"
    out += struct.pack("<I", 3)          # version
    out += struct.pack("<Q", tensors)    # tensor count
    out += struct.pack("<Q", 1)          # metadata kv count

    key = b"general.alignment"
    out += struct.pack("<Q", len(key)) + key
    out += struct.pack("<I", 4)          # GGUF_UINT32
    out += struct.pack("<I", alignment)

    stride = elements * 4
    for index in range(tensors):
        name = f"t{index}".encode()
        out += struct.pack("<Q", len(name)) + name
        out += struct.pack("<I", 1)      # n_dims
        out += struct.pack("<Q", elements)
        out += struct.pack("<I", 0)      # GGML_TYPE_F32
        out += struct.pack("<Q", index * stride)

    pad = (-len(out)) % alignment
    out += b"\x00" * pad
    out += b"\x00" * (stride * tensors)
    return bytes(out)


def write_gguf(directory, name: str, *, truncate_bytes: int = 0, **kwargs) -> str:
    """Write a synthetic GGUF into `directory`, optionally cut short."""
    data = build_gguf(**kwargs)
    if truncate_bytes:
        data = data[: len(data) - truncate_bytes]
    path = str(directory / name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path
