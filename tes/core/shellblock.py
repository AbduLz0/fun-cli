"""Managed blocks: the only way we ever touch a user's config file.

A block is a run of lines between two marker lines. We replace or remove only that run.
Everything outside the markers is left byte-for-byte alone.
"""
from __future__ import annotations


class BlockError(Exception):
    """The markers in the file are damaged (e.g. a start with no end)."""


def _locate(lines: list[str], start: str, end: str):
    s_idx = [i for i, l in enumerate(lines) if l.strip() == start]
    e_idx = [i for i, l in enumerate(lines) if l.strip() == end]
    if not s_idx and not e_idx:
        return None
    if len(s_idx) != 1 or len(e_idx) != 1:
        raise BlockError(
            "The Terminal Experience Studio markers appear more than once or are incomplete. "
            "Open the file, remove the leftover marker lines, then try again."
        )
    if e_idx[0] < s_idx[0]:
        raise BlockError("The end marker comes before the start marker in this file.")
    return s_idx[0], e_idx[0]


def has_block(text: str, start: str, end: str) -> bool:
    try:
        return _locate(text.split("\n"), start, end) is not None
    except BlockError:
        return True


def get_block(text: str, start: str, end: str) -> str | None:
    lines = text.split("\n")
    loc = _locate(lines, start, end)
    if loc is None:
        return None
    return "\n".join(lines[loc[0]: loc[1] + 1])


def set_block(text: str, start: str, end: str, block: str | None) -> str:
    """Insert/replace the block, or remove it when `block` is None."""
    lines = text.split("\n")
    loc = _locate(lines, start, end)
    if block is None:
        if loc is None:
            return text
        i, j = loc
        del lines[i: j + 1]
        while 0 < i < len(lines) and lines[i - 1].strip() == "" and lines[i].strip() == "":
            del lines[i]
        out = "\n".join(lines).rstrip("\n")
        return out + "\n" if out else ""
    new = block.split("\n")
    if loc is not None:
        i, j = loc
        lines[i: j + 1] = new
        return "\n".join(lines)
    body = text.rstrip("\n")
    return (body + "\n\n" if body.strip() else "") + block + "\n"
