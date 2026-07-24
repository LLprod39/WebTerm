from __future__ import annotations

import json
import stat
import tarfile
import zipfile
from dataclasses import replace
from io import BytesIO
from pathlib import Path, PurePosixPath

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import path

from servers.models import Playbook, PlaybookAssetBundle, PlaybookDraft, PlaybookRevision, Server
from servers.services.ansible_project import materialize_ansible_project
from servers.services.playbooks.bundle_archive import (
    BundleLimits,
    BundleValidationError,
    inspect_project_bundle,
)
from servers.services.playbooks.bundle_runtime import BundleRuntimeError, load_revision_runtime_bundle
from servers.services.playbooks.bundle_storage import BundleStorageError, MediaRootPlaybookBundleStorage
from servers.services.playbooks.bundles import (
    commit_project_bundle,
    export_revision_bundle,
    preview_project_bundle,
)
from servers.services.playbooks.content import calculate_content_hash
from servers.services.playbooks.validation import validate_revision
from servers.views.playbook_bundle_views import (
    playbook_bundle_commit,
    playbook_bundle_preview,
    playbook_revision_bundle_export,
)

PLAYBOOK_YAML = b"""---
- name: Configure web tier
  hosts: web
  gather_facts: false
  tasks:
    - name: Show deployment status
      ansible.builtin.debug:
        msg: ready
"""


urlpatterns = [
    path("bundle/preview/", playbook_bundle_preview),
    path("bundle/commit/", playbook_bundle_commit),
    path(
        "playbooks/<int:playbook_id>/revisions/<int:revision_id>/export/",
        playbook_revision_bundle_export,
    ),
]


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(username="bundle-owner", password="test", is_staff=True)


def _manifest(**overrides) -> bytes:
    payload = {
        "schema_version": 1,
        "kind": "webterm.playbook.bundle",
        "name": "Web rollout",
        "entrypoint": "playbook.yml",
        "required_collections": ["ansible.posix"],
        "required_roles": ["web"],
        "tags": ["web", "bundle"],
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


def _valid_files() -> dict[str, bytes]:
    return {
        "manifest.json": _manifest(),
        "playbook.yml": PLAYBOOK_YAML,
        "requirements.yml": b"collections:\n  - ansible.posix\nroles:\n  - web\n",
        "roles/web/tasks/main.yml": b"- name: Role task\n  ansible.builtin.debug:\n    msg: role-ready\n",
        "templates/site.conf.j2": b"server_name {{ inventory_hostname }};\n",
        "files/logo.bin": b"\x00\x01\x02webterm",
    }


def _zip(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def _tar(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, BytesIO(content))
    return output.getvalue()


def _zip_with_symlink() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("playbook.yml", PLAYBOOK_YAML)
        link = zipfile.ZipInfo("files/link.bin")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, b"../../outside")
    return output.getvalue()


def _tar_with_link(*, hardlink: bool) -> bytes:
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        playbook = tarfile.TarInfo("playbook.yml")
        playbook.size = len(PLAYBOOK_YAML)
        archive.addfile(playbook, BytesIO(PLAYBOOK_YAML))
        link = tarfile.TarInfo("files/link.bin")
        link.type = tarfile.LNKTYPE if hardlink else tarfile.SYMTYPE
        link.linkname = "../../outside"
        archive.addfile(link)
    return output.getvalue()


def test_preview_lists_safe_yaml_and_binary_assets_without_returning_file_content():
    preview = preview_project_bundle(_zip(_valid_files()))

    assert preview["safe_to_commit"] is True
    assert preview["selected_entrypoint"] == "playbook.yml"
    assert preview["entrypoints"] == [
        {
            "path": "playbook.yml",
            "play_count": 1,
            "task_count": 1,
            "plays": [{"name": "Configure web tier", "hosts": "web", "task_count": 1}],
        }
    ]
    file_rows = {item["path"]: item for item in preview["files"]}
    assert file_rows["files/logo.bin"]["is_text"] is False
    assert all("content" not in item for item in preview["files"])


def test_preview_accepts_a_safe_tar_project_bundle():
    preview = preview_project_bundle(_tar(_valid_files()))

    assert preview["archive_format"] == "tar"
    assert preview["selected_entrypoint"] == "playbook.yml"
    assert preview["file_count"] == len(_valid_files())


@pytest.mark.parametrize("unsafe_path", ["../escape.yml", "/absolute.yml", r"C:\outside.yml", "roles/web/../../x.yml"])
def test_preview_rejects_zip_path_traversal_and_absolute_paths(unsafe_path):
    with pytest.raises(BundleValidationError) as caught:
        inspect_project_bundle(_zip({unsafe_path: PLAYBOOK_YAML}))

    assert caught.value.code == "unsafe_path"


@pytest.mark.parametrize("unsafe_path", ["../escape.yml", "/absolute.yml"])
def test_preview_rejects_tar_path_traversal_and_absolute_paths(unsafe_path):
    with pytest.raises(BundleValidationError) as caught:
        inspect_project_bundle(_tar({unsafe_path: PLAYBOOK_YAML}))

    assert caught.value.code == "unsafe_path"


@pytest.mark.parametrize(
    "archive",
    [_zip_with_symlink(), _tar_with_link(hardlink=False), _tar_with_link(hardlink=True)],
    ids=["zip-symlink", "tar-symlink", "tar-hardlink"],
)
def test_preview_rejects_symlinks_and_hardlinks(archive):
    with pytest.raises(BundleValidationError) as caught:
        inspect_project_bundle(archive)

    assert caught.value.code == "unsafe_link"


def test_preview_enforces_file_count_per_file_and_total_limits():
    archive = _zip({"playbook.yml": PLAYBOOK_YAML, "README.md": b"readme"})
    base = BundleLimits(max_archive_bytes=100_000, max_file_bytes=100_000, max_total_bytes=100_000, max_files=10)

    with pytest.raises(BundleValidationError, match="too many files") as count_error:
        inspect_project_bundle(archive, limits=replace(base, max_files=1))
    assert count_error.value.status_code == 413

    with pytest.raises(BundleValidationError, match="per-file") as file_error:
        inspect_project_bundle(archive, limits=replace(base, max_file_bytes=16))
    assert file_error.value.code == "file_size_limit"

    with pytest.raises(BundleValidationError, match="extracted size") as total_error:
        inspect_project_bundle(archive, limits=replace(base, max_total_bytes=len(PLAYBOOK_YAML)))
    assert total_error.value.code == "total_size_limit"

    with pytest.raises(BundleValidationError, match="upload size") as archive_error:
        inspect_project_bundle(archive, limits=replace(base, max_archive_bytes=len(archive) - 1))
    assert archive_error.value.code == "archive_size_limit"


@pytest.mark.parametrize(
    ("files", "expected_code"),
    [
        ({"playbook.yml": PLAYBOOK_YAML, "files/payload.exe": b"MZ"}, "disallowed_extension"),
        (
            {
                "playbook.yml": PLAYBOOK_YAML,
                "manifest.json": _manifest(inventory_bindings={"web": [1]}),
            },
            "invalid_manifest",
        ),
        (
            {"playbook.yml": PLAYBOOK_YAML, "requirements.yml": b"roles: invalid\n"},
            "malformed_requirements",
        ),
    ],
)
def test_preview_rejects_disallowed_extensions_manifest_fields_and_requirements(files, expected_code):
    with pytest.raises(BundleValidationError) as caught:
        inspect_project_bundle(_zip(files))

    assert caught.value.code == expected_code


def test_preview_reports_secrets_without_echoing_secret_values():
    secret = "ultra-secret-value"
    source = (
        PLAYBOOK_YAML + f"\n# retained yaml\n- hosts: all\n  vars:\n    api_token: {secret}\n  tasks: []\n".encode()
    )
    preview = preview_project_bundle(_zip({"playbook.yml": source}))

    assert preview["safe_to_commit"] is False
    assert preview["secret_warnings"]
    assert secret not in json.dumps(preview)


@pytest.mark.django_db
def test_commit_persists_canonical_bundle_revision_and_draft(staff_user, tmp_path):
    storage = MediaRootPlaybookBundleStorage(tmp_path)
    result = commit_project_bundle(_zip(_valid_files()), actor=staff_user, storage=storage)

    result.playbook.refresh_from_db()
    assert result.playbook.origin_revision_id == result.revision.id
    assert result.playbook.published_revision_id == result.revision.id
    assert result.revision.asset_bundle_id == result.asset_bundle.id
    assert result.revision.bundle_hash == result.asset_bundle.content_hash
    assert result.asset_bundle.scan_status == PlaybookAssetBundle.SCAN_CLEAN
    assert result.asset_bundle.file_count == len(_valid_files())
    draft = PlaybookDraft.objects.get(playbook=result.playbook)
    assert draft.asset_bundle_id == result.asset_bundle.id
    assert draft.base_revision_id == result.revision.id

    stored = storage.read(result.asset_bundle.storage_key, max_bytes=10 * 1024 * 1024)
    with zipfile.ZipFile(BytesIO(stored)) as archive:
        assert set(archive.namelist()) == set(_valid_files())
        for info in archive.infolist():
            assert (info.external_attr >> 16) & 0o111 == 0


@pytest.mark.django_db
def test_commit_rejects_secret_material_before_storage(staff_user, tmp_path):
    storage = MediaRootPlaybookBundleStorage(tmp_path)
    source = PLAYBOOK_YAML.replace(b"msg: ready", b"api_token: plaintext-token")

    with pytest.raises(BundleValidationError) as caught:
        commit_project_bundle(_zip({"playbook.yml": source}), actor=staff_user, storage=storage)

    assert caught.value.code == "secret_material_detected"
    assert not Playbook.objects.exists()
    assert not list(tmp_path.rglob("*.zip"))


@pytest.mark.django_db
def test_commit_rolls_back_database_and_artifact_when_revision_creation_fails(staff_user, tmp_path, monkeypatch):
    storage = MediaRootPlaybookBundleStorage(tmp_path)

    def fail_revision(*_args, **_kwargs):
        raise RuntimeError("forced revision failure")

    monkeypatch.setattr(PlaybookRevision.objects, "create", fail_revision)
    with pytest.raises(RuntimeError, match="forced revision failure"):
        commit_project_bundle(_zip(_valid_files()), actor=staff_user, storage=storage)

    assert not Playbook.objects.exists()
    assert not PlaybookAssetBundle.objects.exists()
    assert not list(tmp_path.rglob("*.zip"))


@pytest.mark.django_db
def test_export_redacts_secrets_and_never_serializes_binding_metadata(staff_user, tmp_path):
    storage = MediaRootPlaybookBundleStorage(tmp_path)
    result = commit_project_bundle(_zip(_valid_files()), actor=staff_user, storage=storage)
    secret = "super-secret-value"
    source_yaml = (
        PLAYBOOK_YAML.decode()
        + f"\n- hosts: all\n  vars:\n    api_token: {secret}\n    ansible_host: 10.0.0.5\n  tasks: []\n"
    )
    revision = PlaybookRevision.objects.create(
        playbook=result.playbook,
        revision_number=2,
        parent=result.revision,
        author=staff_user,
        content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
        source_yaml=source_yaml,
        tasks=[],
        content_hash=calculate_content_hash(
            content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
            source_yaml=source_yaml,
            tasks=[],
            bundle_hash=result.revision.bundle_hash,
        ),
        asset_bundle=result.asset_bundle,
        bundle_hash=result.revision.bundle_hash,
        origin_type=PlaybookRevision.ORIGIN_MANUAL,
        metadata={
            "bundle_entrypoint": "playbook.yml",
            "inventory_bindings": {"web": {"server_ids": [1]}},
            "host": "10.0.0.5",
        },
    )

    artifact = export_revision_bundle(revision, actor=staff_user, storage=storage)
    assert artifact.redaction_count >= 1
    with zipfile.ZipFile(BytesIO(artifact.content)) as archive:
        combined = b"\n".join(archive.read(name) for name in archive.namelist())
        assert secret.encode() not in combined
        assert b"__REDACTED__" in archive.read("playbook.yml")
        assert b"inventory_bindings" not in combined
        assert b"10.0.0.5" not in combined
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["sanitized"] is True
        assert set(manifest["revision"]) == {"id", "number", "content_hash", "bundle_hash"}
        assert archive.read("files/logo.bin") == _valid_files()["files/logo.bin"]


def test_media_storage_rejects_keys_outside_its_scoped_root(tmp_path):
    storage = MediaRootPlaybookBundleStorage(tmp_path)
    with pytest.raises(BundleStorageError):
        storage.read("../outside.zip", max_bytes=100)


@pytest.mark.django_db
def test_runtime_bundle_is_verified_and_materialized_with_the_exact_revision_source(staff_user, tmp_path):
    with override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=tmp_path / "bundles"):
        result = commit_project_bundle(_zip(_valid_files()), actor=staff_user)
        runtime = load_revision_runtime_bundle(result.revision)

        assert runtime is not None
        assert runtime.entrypoint == "playbook.yml"
        workdir = tmp_path / "runtime"
        workdir.mkdir()
        edited_source = result.revision.source_yaml.replace("msg: ready", "msg: exact-revision")
        entrypoint = materialize_ansible_project(
            workdir,
            playbook_yaml=edited_source,
            project_files=runtime.files,
            entrypoint=runtime.entrypoint,
        )

        assert entrypoint == "playbook.yml"
        assert "exact-revision" in (workdir / "playbook.yml").read_text(encoding="utf-8")
        assert (workdir / "roles" / "web" / "tasks" / "main.yml").read_bytes() == _valid_files()[
            "roles/web/tasks/main.yml"
        ]
        assert (workdir / "templates" / "site.conf.j2").is_file()


@pytest.mark.django_db
def test_runtime_bundle_refuses_tampered_stored_bytes(staff_user, tmp_path):
    storage_root = tmp_path / "bundles"
    with override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=storage_root):
        result = commit_project_bundle(_zip(_valid_files()), actor=staff_user)
        artifact = Path(storage_root, *PurePosixPath(result.asset_bundle.storage_key).parts)
        artifact.write_bytes(b"tampered")

        with pytest.raises(BundleRuntimeError, match="could not be verified"):
            load_revision_runtime_bundle(result.revision)


@pytest.mark.django_db
def test_validation_blocks_controller_escape_hidden_in_bundle_role(staff_user, tmp_path, monkeypatch):
    files = _valid_files()
    files["playbook.yml"] = b"""- name: Role-backed play
  hosts: web
  gather_facts: false
  roles:
    - web
  tasks: []
"""
    files["roles/web/tasks/main.yml"] = b"""- name: Escape to controller
  ansible.builtin.shell: id
  delegate_to: localhost
"""
    server = Server.objects.create(
        user=staff_user,
        name="bundle-target",
        host="192.0.2.10",
        port=22,
        username="root",
        auth_method="key",
        is_active=True,
    )
    monkeypatch.setattr(
        "servers.services.playbooks.validation.runtime_fingerprint",
        lambda: {"method": "test", "available": True, "analyzer_version": 3},
    )
    monkeypatch.setattr(
        "servers.services.playbooks.validation.validate_playbook_syntax",
        lambda _source, **_kwargs: {"status": "passed", "passed": True, "message": "ok"},
    )

    with override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=tmp_path / "bundles"):
        result = commit_project_bundle(_zip(files), actor=staff_user)
        validation = validate_revision(
            revision=result.revision,
            user=staff_user,
            target_server_ids=[server.id],
            inventory_bindings={"web": {"server_ids": [server.id], "group_ids": []}},
        )

    assert validation.status == "blocked"
    issue = next(item for item in validation.issues if item["code"] == "controller_delegate_forbidden")
    assert "roles/web/tasks/main.yml" in issue["path"]


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_bundle_views_preview_commit_and_export_without_project_url_wiring(staff_user):
    client = Client()
    client.force_login(staff_user)
    archive = _zip(_valid_files())

    preview = client.post(
        "/bundle/preview/",
        {"bundle": SimpleUploadedFile("project.zip", archive, content_type="application/zip")},
    )
    assert preview.status_code == 200
    assert preview.json()["preview"]["selected_entrypoint"] == "playbook.yml"

    commit = client.post(
        "/bundle/commit/",
        {
            "bundle": SimpleUploadedFile("project.zip", archive, content_type="application/zip"),
            "name": "Imported from API",
            "tags": json.dumps(["api", "safe"]),
        },
    )
    assert commit.status_code == 201, commit.content
    payload = commit.json()
    assert payload["bundle"]["scan_status"] == "clean"

    exported = client.get(f"/playbooks/{payload['playbook']['id']}/revisions/{payload['revision']['id']}/export/")
    assert exported.status_code == 200
    assert exported["Content-Type"] == "application/zip"
    assert "attachment" in exported["Content-Disposition"]
    with zipfile.ZipFile(BytesIO(exported.content)) as archive_file:
        assert "manifest.json" in archive_file.namelist()
