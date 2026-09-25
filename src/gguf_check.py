"""Cheap, dependency-free GGUF integrity checks.

The app downloads its models from Hugging Face. A download that is interrupted
(a dropped connection, or the disk filling up mid-write) leaves a **partial**
file on disk whose size is greater than zero. Every naive "is there a file
here?" check then reports the model as present and ready, and the failure only
surfaces much later as an opaque error from ``llama-server`` or the FunASR
binary (``failed to read tensor data binary blob``) after the user has already
waited through preprocessing.

This module reads the GGUF header, metadata and tensor table — never the tensor
data itself — and answers two questions:

* does the file start with a well-formed GGUF header, and
* does the header describe more data than the file contains (i.e. is it cut
  short)?

It deliberately does *not* validate tensor payloads: that would mean reading
gigabytes, which is exactly what a pre-flight check must not do.
"""
from __future__ import annotations

import mmap
import os
import struct

MAGIC = b"GGUF"

# GGUF metadata value type ids (see the GGUF spec).
_GGUF_UINT8 = 0
_GGUF_INT8 = 1
_GGUF_UINT16 = 2
_GGUF_INT16 = 3
_GGUF_UINT32 = 4
_GGUF_INT32 = 5
_GGUF_FLOAT32 = 6
_GGUF_BOOL = 7
_GGUF_STRING = 8
_GGUF_ARRAY = 9
_GGUF_UINT64 = 10
_GGUF_INT64 = 11
_GGUF_FLOAT64 = 12

_FIXED_SIZES = {
    _GGUF_UINT8: 1,
    _GGUF_INT8: 1,
    _GGUF_UINT16: 2,
    _GGUF_INT16: 2,
    _GGUF_UINT32: 4,
    _GGUF_INT32: 4,
    _GGUF_FLOAT32: 4,
    _GGUF_BOOL: 1,
    _GGUF_UINT64: 8,
    _GGUF_INT64: 8,
    _GGUF_FLOAT64: 8,
}

# Default tensor-data alignment from the GGUF spec; overridable by the
# `general.alignment` metadata key.
_DEFAULT_ALIGNMENT = 32

# GGML tensor types -> (elements per block, bytes per block). Used only to size
# the *last* tensor, so truncation is still detected when the cut lands past the
# final tensor's start offset. Unknown ids are tolerated: the size is then
# unknown and the check degrades to the offset comparison rather than reporting
# a healthy file as broken.
_GGML_TYPES: dict[int, tuple[int, int]] = {
    0: (1, 4),       # F32
    1: (1, 2),       # F16
    2: (32, 18),     # Q4_0
    3: (32, 20),     # Q4_1
    6: (32, 22),     # Q5_0
    7: (32, 24),     # Q5_1
    8: (32, 34),     # Q8_0
    9: (32, 36),     # Q8_1
    10: (256, 84),   # Q2_K
    11: (256, 110),  # Q3_K
    12: (256, 144),  # Q4_K
    13: (256, 176),  # Q5_K
    14: (256, 210),  # Q6_K
    15: (256, 292),  # Q8_K
    16: (256, 66),   # IQ2_XXS
    17: (256, 74),   # IQ2_XS
    18: (256, 98),   # IQ3_XXS
    19: (256, 50),   # IQ1_S
    20: (32, 18),    # IQ4_NL
    21: (256, 110),  # IQ3_S
    22: (256, 82),   # IQ2_S
    23: (256, 136),  # IQ4_XS
    24: (1, 1),      # I8
    25: (1, 2),      # I16
    26: (1, 4),      # I32
    27: (1, 8),      # I64
    28: (1, 8),      # F64
    29: (256, 56),   # IQ1_M
    30: (1, 2),      # BF16
}

# Sanity ceilings so a corrupt header cannot make us read gigabytes.
_MAX_METADATA_KV = 1 << 20
_MAX_TENSORS = 1 << 20
_MAX_STRING_BYTES = 1 << 26
_MAX_ARRAY_ELEMENTS = 1 << 30

_U32 = struct.Struct("<I")
_U64 = struct.Struct("<Q")


class GgufError(Exception):
    """Raised internally when the file cannot be parsed as a GGUF file."""


def _tensor_bytes(dims: list[int], type_id: int) -> int | None:
    """Byte size of a tensor, or ``None`` when the quantisation is unknown."""
    block = _GGML_TYPES.get(type_id)
    if block is None:
        return None
    elements = 1
    for dim in dims:
        elements *= dim
    per_block, block_bytes = block
    if elements <= 0:
        return 0
    blocks = -(-elements // per_block)  # ceil
    return blocks * block_bytes


class _Reader:
    """Cursor over the file's bytes.

    Uses ``mmap`` when available so the tokenizer metadata (hundreds of
    thousands of short strings) can be walked without a syscall per string —
    the difference between ~2.4 s and a few milliseconds on a 1.9 GB model.
    Falls back to a plain buffered file when the platform refuses to map it.
    """

    def __init__(self, path: str) -> None:
        self._file = open(path, "rb")
        self._map = None
        self._pos = 0
        try:
            if os.fstat(self._file.fileno()).st_size > 0:
                self._map = mmap.mmap(
                    self._file.fileno(), 0, access=mmap.ACCESS_READ
                )
        except (OSError, ValueError):
            self._map = None

    def __enter__(self) -> "_Reader":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        if self._map is not None:
            self._map.close()
            self._map = None
        self._file.close()

    def read(self, count: int) -> bytes:
        if count < 0:
            raise GgufError("negative read")
        if self._map is not None:
            end = self._pos + count
            if end > len(self._map):
                raise GgufError("unexpected end of file")
            data = self._map[self._pos:end]
            self._pos = end
            return data
        data = self._file.read(count)
        if len(data) != count:
            raise GgufError("unexpected end of file")
        self._pos += count
        return data

    def skip(self, count: int) -> None:
        if count < 0:
            raise GgufError("negative skip")
        if self._map is not None:
            end = self._pos + count
            if end > len(self._map):
                raise GgufError("unexpected end of file")
            self._pos = end
            return
        self._file.seek(count, os.SEEK_CUR)
        self._pos += count

    def u32(self) -> int:
        if self._map is not None:
            value = _U32.unpack_from(self._map, self._pos)[0]
            self._pos += 4
            return value
        return _U32.unpack(self.read(4))[0]

    def u64(self) -> int:
        if self._map is not None:
            value = _U64.unpack_from(self._map, self._pos)[0]
            self._pos += 8
            return value
        return _U64.unpack(self.read(8))[0]

    def string(self) -> bytes:
        length = self.u64()
        if length > _MAX_STRING_BYTES:
            raise GgufError("implausible string length")
        return self.read(length)

    @property
    def position(self) -> int:
        return self._pos


def _read_value(reader: _Reader, value_type: int):
    """Consume one metadata value; returns it only when cheap to keep."""
    if value_type in _FIXED_SIZES:
        if value_type == _GGUF_UINT32:
            return reader.u32()
        if value_type == _GGUF_UINT64:
            return reader.u64()
        reader.skip(_FIXED_SIZES[value_type])
        return None
    if value_type == _GGUF_STRING:
        reader.string()
        return None
    if value_type == _GGUF_ARRAY:
        element_type = reader.u32()
        count = reader.u64()
        if count > _MAX_ARRAY_ELEMENTS:
            raise GgufError("implausible array length")
        if element_type in _FIXED_SIZES:
            reader.skip(_FIXED_SIZES[element_type] * count)
            return None
        if element_type == _GGUF_STRING:
            for _ in range(count):
                reader.string()
            return None
        raise GgufError("unknown array element type")
    raise GgufError("unknown metadata value type")


def _parse_header(reader: _Reader) -> tuple[int, int, int, int | None]:
    """Return (tensor_count, data_start, max_offset, last_tensor_bytes).

    Raises :class:`GgufError` when the file is not a parseable GGUF header.
    """
    if reader.read(4) != MAGIC:
        raise GgufError("not a GGUF file (bad magic)")
    version = reader.u32()
    if version not in (1, 2, 3):
        raise GgufError(f"unsupported GGUF version {version}")
    tensor_count = reader.u64()
    metadata_count = reader.u64()
    if tensor_count > _MAX_TENSORS or metadata_count > _MAX_METADATA_KV:
        raise GgufError("implausible GGUF header")

    alignment = _DEFAULT_ALIGNMENT
    for _ in range(metadata_count):
        key = reader.string()
        value_type = reader.u32()
        value = _read_value(reader, value_type)
        if key == b"general.alignment" and isinstance(value, int) and value > 0:
            alignment = value

    max_offset = 0
    last_tensor_bytes: int | None = 0
    for _ in range(tensor_count):
        reader.string()  # tensor name
        n_dims = reader.u32()
        if n_dims > 8:
            raise GgufError("implausible tensor rank")
        dims = [reader.u64() for _ in range(n_dims)]
        type_id = reader.u32()
        offset = reader.u64()
        if offset >= max_offset:
            max_offset = offset
            last_tensor_bytes = _tensor_bytes(dims, type_id)

    position = reader.position
    padding = (-position) % max(1, alignment)
    data_start = position + padding

    return tensor_count, data_start, max_offset, last_tensor_bytes


def _cache_key(path: str) -> tuple[str, int, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (os.path.abspath(path), stat.st_size, stat.st_mtime_ns)


# Parsing a large tokenizer's metadata takes ~1 s on a 1.9 GB model, and the UI
# asks for readiness on every form change. Results are cached against the file's
# size and mtime, so a re-download (new size/mtime) always re-validates.
_CACHE: dict[tuple[str, int, int], tuple[bool, str]] = {}
_CACHE_LIMIT = 64


def inspect_gguf(path: str | None) -> tuple[bool, str]:
    """Return ``(usable, reason)`` for the GGUF file at ``path``.

    ``reason`` is an empty string when the file is usable, otherwise a short
    human-readable explanation suitable for showing to the user.
    """
    if not path:
        return False, "no path given"
    key = _cache_key(path)
    if key is not None:
        cached = _CACHE.get(key)
        if cached is not None:
            return cached
    result = _inspect_gguf_uncached(path)
    if key is not None:
        if len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.clear()
        _CACHE[key] = result
    return result


def _inspect_gguf_uncached(path: str) -> tuple[bool, str]:
    try:
        if not os.path.isfile(path):
            return False, "file not found"
        size = os.path.getsize(path)
        if size == 0:
            return False, "file is empty"
        if size < 32:
            return False, "file is too small to be a GGUF model"
    except OSError as exc:
        return False, f"cannot read the file ({exc})"

    try:
        with _Reader(path) as reader:
            tensor_count, data_start, max_offset, last_bytes = _parse_header(reader)
    except GgufError as exc:
        return False, f"not a valid GGUF file ({exc})"
    except OSError as exc:
        return False, f"cannot read the file ({exc})"

    if tensor_count == 0:
        return False, "GGUF file declares no tensors"

    # Tensors are stored contiguously after `data_start`, so the file must be
    # long enough to hold the last tensor's payload. A download cut short by a
    # dropped connection or a full disk fails here. When the quantisation type
    # is unknown we can only check that the tensor *starts* inside the file.
    required = data_start + max_offset + (last_bytes or 0)
    if required > size:
        missing = required - size
        return False, (
            f"file is incomplete: {missing} byte(s) short of the size its "
            f"GGUF header describes"
        )

    return True, ""


def is_usable_gguf(path: str | None) -> bool:
    """True when ``path`` is a complete, parseable GGUF file."""
    return inspect_gguf(path)[0]


__all__ = ["GgufError", "inspect_gguf", "is_usable_gguf"]
