"""Distinct prompt setups, deduplicated.

Three experiments — (1.0, 1.0, 1.0), then (1.2, 1.0, 1.2), then back to
(1.0, 1.0, 1.0) — are two configurations, not three. The third run belongs to
the configuration the first one created.

That grouping is what makes "which setup produced this result?" answerable
without joining three artefact tables by hand and trusting that nobody edited a
block's text without moving its version.
"""

from __future__ import annotations

from app.prompts.builder import build_prompt
from app.services.emg_service import synthesise_window
from app.services.prompt_configuration_service import describe


class _Version:
    def __init__(self, version: str):
        self.id = f"id-{version}"
        self.version = version


def digest(system: str, technical: str, emg: str) -> str:
    """The frozen digest for a given set of block texts."""
    window = synthesise_window("rest", seed=1, samples=4)
    return build_prompt(
        window,
        system_prompt=system,
        technical_context=technical,
        emg_context=emg,
    ).frozen_context_sha256


# ── The deduplication key ───────────────────────────────────────────────────


def test_the_same_three_blocks_always_produce_the_same_key():
    """Deduplication rests on this: the key must be a function of the text."""
    assert digest("A", "B", "C") == digest("A", "B", "C")


def test_returning_to_an_earlier_setup_reuses_its_key():
    """The scenario exactly: run 1 and run 3 share a configuration, run 2 does
    not. Two rows, not three."""
    first = digest("system 1.0", "technical 1.0", "emg 1.0")
    second = digest("system 1.2", "technical 1.0", "emg 1.2")
    third = digest("system 1.0", "technical 1.0", "emg 1.0")

    assert first == third
    assert first != second
    assert len({first, second, third}) == 2


def test_changing_any_one_block_changes_the_key():
    """Each frozen block is part of the identity. If one were left out, two
    setups differing only in that block would be recorded as the same
    configuration and their results averaged together."""
    base = digest("S", "T", "E")
    assert digest("S!", "T", "E") != base
    assert digest("S", "T!", "E") != base
    assert digest("S", "T", "E!") != base


def test_the_dynamic_block_is_not_part_of_the_key():
    """A configuration is the frozen setup. Every EMG window would otherwise
    create its own configuration, which is the opposite of the point."""
    a = build_prompt(synthesise_window("rest", seed=1, samples=8))
    b = build_prompt(synthesise_window("power_grasp", seed=2, samples=64))

    assert a.dynamic_prompt_sha256 != b.dynamic_prompt_sha256
    assert a.frozen_context_sha256 == b.frozen_context_sha256


def test_the_key_catches_an_edit_that_the_version_ids_would_miss():
    """Why the digest is the key rather than the three version ids.

    A block edited in place, or supplied as a per-request override, keeps the
    same ids — or has none at all. Keying on ids would file those runs under a
    configuration whose text they never saw.
    """
    original = digest("system 1.0", "T", "E")
    edited = digest("system 1.0 with one sentence changed", "T", "E")
    assert original != edited


# ── The label ───────────────────────────────────────────────────────────────


def test_the_label_shows_which_block_moved():
    """Two labels side by side should answer "what changed?" without opening
    anything."""
    assert describe("1.0", "1.0", "1.0") == "S1.0 · T1.0 · E1.0"
    assert describe("1.2", "1.0", "1.2") == "S1.2 · T1.0 · E1.2"


def test_an_override_with_no_artefact_is_marked_rather_than_blank():
    """A blank would read as "no version"; `?` says the text was supplied per
    request and belongs to no stored artefact."""
    assert describe(None, "1.0", None) == "S? · T1.0 · E?"
