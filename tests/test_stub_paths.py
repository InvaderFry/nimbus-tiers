"""Stub path classes must raise NotImplementedError until implemented."""

from __future__ import annotations

import pytest

from nimbus_tiered.generator.cloud_only_path import CloudOnlyPath
from nimbus_tiered.generator.light_local_path import LightLocalPath


def test_cloud_only_can_be_instantiated() -> None:
    assert CloudOnlyPath().name == "cloud-only"


def test_cloud_only_template_files_raises() -> None:
    with pytest.raises(NotImplementedError, match="CloudOnlyPath"):
        CloudOnlyPath().template_files()


def test_light_local_can_be_instantiated() -> None:
    assert LightLocalPath().name == "light-local"


def test_light_local_template_files_raises() -> None:
    with pytest.raises(NotImplementedError, match="LightLocalPath"):
        LightLocalPath().template_files()
