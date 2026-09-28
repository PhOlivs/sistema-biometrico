"""Testes das regras dos níveis de acesso (não dependem de banco nem de Flask)."""

import pytest

from models.access_level import (
    LEVEL_1,
    LEVEL_2,
    LEVEL_3,
    can_access,
    is_valid_level,
    level_label,
)


@pytest.mark.parametrize("level", [1, 2, 3])
def test_valid_levels(level):
    assert is_valid_level(level)


@pytest.mark.parametrize("level", [0, 4, 999, -1, "1", None, 1.0, True])
def test_invalid_levels(level):
    assert not is_valid_level(level)


def test_level_labels():
    assert level_label(LEVEL_1) == "Acesso geral"
    assert level_label(LEVEL_2) == "Acesso de diretoria"
    assert level_label(LEVEL_3) == "Acesso ministerial"


@pytest.mark.parametrize(
    "user_level, required, expected",
    [
        (1, 1, True),
        (1, 2, False),
        (1, 3, False),
        (2, 1, True),
        (2, 2, True),
        (2, 3, False),
        (3, 1, True),
        (3, 2, True),
        (3, 3, True),
    ],
)
def test_can_access_matrix(user_level, required, expected):
    assert can_access(user_level, required) is expected


def test_can_access_rejects_invalid_levels():
    assert not can_access(999, 1)
    assert not can_access(3, 999)
