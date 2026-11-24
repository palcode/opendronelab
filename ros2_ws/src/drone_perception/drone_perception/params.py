# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar

"""Parameter validation shared by the perception nodes (no ROS imports)."""


def validate_process_every_n(value):
    """Return process_every_n as an int >= 1, or raise ValueError.

    0 used to raise ZeroDivisionError on every frame (frame_count % 0).
    """
    if isinstance(value, bool):
        raise ValueError(f'process_every_n must be an integer >= 1, got {value!r}')
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f'process_every_n must be an integer >= 1, got {value!r}')
        value = int(value)
    if not isinstance(value, int) or value < 1:
        raise ValueError(f'process_every_n must be an integer >= 1, got {value!r}')
    return value
