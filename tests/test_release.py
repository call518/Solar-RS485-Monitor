"""Offline checks for tag validation and release publication."""

import io
import json
import tarfile
import zipfile

import pytest

from scripts.check_release import check_release, release_version
from scripts import publish_release as publisher


@pytest.mark.parametrize("tag", ["1", "1.2", "2.4.3", "1.2.3.4"])
def test_numeric_release_tag(tag):
    assert release_version(tag) == tag


@pytest.mark.parametrize("tag", ["v1.2.3", "1.2.3rc1", "1..2", "01.2", "1.2."])
def test_invalid_release_tag(tag):
    with pytest.raises(ValueError):
        release_version(tag)


def test_distribution_versions_must_match_tag(tmp_path):
    metadata = b"Name: solar-rs485-monitor\nVersion: 2.4.3\n"
    with zipfile.ZipFile(tmp_path / "package.whl", "w") as archive:
        archive.writestr("package.dist-info/METADATA", metadata)
    with tarfile.open(tmp_path / "package.tar.gz", "w:gz") as archive:
        item = tarfile.TarInfo("package/PKG-INFO")
        item.size = len(metadata)
        archive.addfile(item, io.BytesIO(metadata))
    check_release("2.4.3", tmp_path)
    with pytest.raises(ValueError):
        check_release("2.4.4", tmp_path)


def test_notes_preserve_full_messages_and_previous_release_range(monkeypatch):
    calls = []

    def command(*args):
        calls.append(args)
        if args[1] == "rev-parse":
            return "previous" if "2.4.2" in args[-1] else "current"
        if args[1] == "log":
            return "abc1234\0Subject\n\nBody with ``` and $(echo unsafe)\0"
        return ""

    monkeypatch.setattr(publisher, "command", command)
    notes = publisher.release_notes("owner/repo", "2.4.3", "2.4.2")
    assert "Subject\n\nBody with ``` and $(echo unsafe)" in notes
    assert "````text" in notes
    assert any("previous..current" in args for args in calls)
    assert "compare/2.4.2...2.4.3" in notes


@pytest.mark.parametrize("existing", [False, True])
def test_publish_release_uses_latest_publication_and_preserves_existing(
    monkeypatch, existing
):
    calls = []
    releases = [
        {"tag_name": "2.4.1", "draft": False, "published_at": "2026-10-20"},
        {"tag_name": "2.4.2", "draft": False, "published_at": "2026-10-23"},
        {"tag_name": "2.4.4", "draft": True, "published_at": None},
    ]
    if existing:
        releases.append({"tag_name": "2.4.3", "draft": False})

    def command(*args):
        calls.append(args)
        if "--slurp" in args:
            return json.dumps([releases])
        return "current"

    def notes(repository, tag, previous):
        assert previous == "2.4.2"
        return "Release notes"

    monkeypatch.setattr(publisher, "command", command)
    monkeypatch.setattr(publisher, "release_notes", notes)
    publisher.publish_release("owner/repo", "2.4.3")
    created = [args for args in calls if args[:3] == ("gh", "release", "create")]
    assert len(created) == (0 if existing else 1)
