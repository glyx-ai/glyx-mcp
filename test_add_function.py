"""Tests for the add function."""

import pytest
from add_function import add


def test_add_integers():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0


def test_add_floats():
    assert add(2.5, 3.5) == 6.0
    assert add(1.1, 2.2) == pytest.approx(3.3)


def test_add_mixed_types():
    assert add(2, 3.5) == 5.5
    assert add(1.5, 3) == 4.5


def test_add_raises_on_string():
    with pytest.raises(TypeError, match="First argument must be int or float"):
        add("2", 3)
    
    with pytest.raises(TypeError, match="Second argument must be int or float"):
        add(2, "3")


def test_add_raises_on_none():
    with pytest.raises(TypeError, match="First argument must be int or float"):
        add(None, 3)
    
    with pytest.raises(TypeError, match="Second argument must be int or float"):
        add(2, None)


def test_add_raises_on_bool():
    with pytest.raises(TypeError, match="First argument must be int or float"):
        add(True, 3)
    
    with pytest.raises(TypeError, match="Second argument must be int or float"):
        add(2, False)
