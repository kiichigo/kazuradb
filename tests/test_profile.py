from pathlib import Path

import pytest

from kazura.profile import Profile, ProfileValidationError


PROFILE_PATH = Path("examples/work_notes/profile.yaml")


def test_loads_work_notes_profile():
    profile = Profile.load(PROFILE_PATH)

    assert profile.name == "work_notes"
    assert sorted(profile.node_kinds) == ["concept", "organization", "person", "work"]
    assert "features" in profile.edge_types


def test_valid_node_kinds_pass():
    profile = Profile.load(PROFILE_PATH)

    assert profile.validate_node_kind("person") is True
    assert profile.validate_node_kind("work") is True


def test_invalid_node_kind_fails():
    profile = Profile.load(PROFILE_PATH)

    with pytest.raises(ProfileValidationError, match="node kind 'place' is not allowed"):
        profile.validate_node_kind("place")


def test_valid_edge_shapes_pass():
    profile = Profile.load(PROFILE_PATH)

    assert profile.validate_edge("person", "created", "work") is True
    assert profile.validate_edge("organization", "produced", "work") is True
    assert profile.validate_edge("work", "features", "concept") is True


def test_invalid_edge_type_fails():
    profile = Profile.load(PROFILE_PATH)

    with pytest.raises(ProfileValidationError, match="edge type 'owns' is not allowed"):
        profile.validate_edge("person", "owns", "work")


def test_invalid_source_kind_for_edge_fails():
    profile = Profile.load(PROFILE_PATH)

    with pytest.raises(ProfileValidationError, match="cannot start from node kind 'concept'"):
        profile.validate_edge("concept", "created", "work")


def test_invalid_target_kind_for_edge_fails():
    profile = Profile.load(PROFILE_PATH)

    with pytest.raises(ProfileValidationError, match="cannot target node kind 'person'"):
        profile.validate_edge("person", "created", "person")


def test_related_to_is_symmetric():
    profile = Profile.load(PROFILE_PATH)

    assert profile.edge_types["related_to"].symmetric is True
