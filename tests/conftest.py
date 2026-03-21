"""Shared test fixtures."""

from __future__ import annotations

import json
import pytest


SAMPLE_RATES = {
    "opus": {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_create": 18.75},
    "sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_create": 3.75},
    "haiku": {"input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_create": 1.25},
}


def make_assistant_entry(
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 1000,
    output_tokens: int = 500,
    cache_read: int = 0,
    cache_create: int = 0,
    timestamp: str = "2026-03-20T12:00:00Z",
) -> str:
    """Create a JSONL line for an assistant message."""
    entry = {
        "type": "assistant",
        "timestamp": timestamp,
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_create,
            },
        },
    }
    return json.dumps(entry)


def make_user_entry(timestamp: str = "2026-03-20T12:00:00Z") -> str:
    """Create a JSONL line for a user message (should be skipped by scanner)."""
    return json.dumps({"type": "user", "timestamp": timestamp, "message": {"content": "hello"}})
