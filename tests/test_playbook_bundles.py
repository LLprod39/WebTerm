from __future__ import annotations

import hashlib
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

from core_ui.models.projects import ProjectMembership
from servers.models import Playbook, PlaybookAssetBundle, PlaybookDraft, PlaybookGrant, PlaybookRevision
from servers.services.ansible_project import AnsibleProjectError, materialize_ansible_project
from servers.services.playbooks.bundle_archive import (
    BundleFile,
    BundleLimits,
    BundleValidationError,
    build_canonical_zip,
    calculate_bundle_content_hash,
    inspect_project_bundle,
    sanitize_file_for_export,
)
from servers.services.playbooks.bundle_runtime import BundleRuntimeError, load_revision_runtime_bundle
from servers.services.playbooks.bundle_storage import BundleStorageError, MediaRootPlaybookBundleStorage
from servers.services.playbooks.bundles import (
    commit_project_bundle,
    export_revision_bundle,
    preview_project_bundle,
)
from servers.services.playbooks.content import calculate_content_hash
from servers.services.playbooks.revisions import publish_revision
from servers.services.playbooks.sharing import save_grant
from servers.views.playbook_bundle_views import (
    playbook_bundle_commit,
    playbook_bundle_preview,
    playbook_revision_bundle_export,
)
from servers.views.playbook_draft_views import playbook_draft_file, playbook_draft_files
from servers.views.playbook_revision_views import playbook_revision_detail
from servers.views.server_playbooks import playbook_detail, playbook_duplicate

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
    path("playbooks/<int:playbook_id>/draft/files/", playbook_draft_files),
    path("playbooks/<int:playbook_id>/draft/file/", playbook_draft_file),
    path("playbooks/<int:playbook_id>/content/", playbook_detail),
    path("playbooks/<int:playbook_id>/duplicate/", playbook_duplicate),
    path("playbooks/<int:playbook_id>/revisions/<int:revision_id>/content/", playbook_revision_detail),
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
    assert preview["dependencies"] == {"collections": ["ansible.posix"], "roles": ["web"]}
    assert preview["manifest"]["required_roles"] == ["web"]
    assert preview["compatibility"]["status"] in {"needs_binding", "ready"}
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


def test_tar_reader_does_not_materialize_unbounded_members(monkeypatch):
    monkeypatch.setattr(tarfile.TarFile, "getmembers", lambda _self: pytest.fail("getmembers is unbounded"))

    preview = preview_project_bundle(_tar(_valid_files()))

    assert preview["selected_entrypoint"] == "playbook.yml"


def test_compressed_tar_metadata_is_bounded_before_member_processing():
    output = BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz", format=tarfile.PAX_FORMAT) as archive:
        info = tarfile.TarInfo("playbook.yml")
        info.size = len(PLAYBOOK_YAML)
        info.pax_headers = {"comment": "x" * (2 * 1024 * 1024)}
        archive.addfile(info, BytesIO(PLAYBOOK_YAML))
    limits = BundleLimits(
        max_archive_bytes=100_000,
        max_file_bytes=100_000,
        max_total_bytes=1024,
        max_files=1,
    )

    with pytest.raises(BundleValidationError) as caught:
        inspect_project_bundle(output.getvalue(), limits=limits)

    assert caught.value.code == "total_size_limit"
    assert caught.value.status_code == 413


def test_repository_archive_tolerates_known_metadata_wrapper_and_safe_subdirectories():
    files = {
        "ops-a1b2/.gitlab-ci.yml": b"stages: [test]\n",
        "ops-a1b2/docs/guide.md": b"documentation\n",
        "ops-a1b2/playbooks/site.yml": PLAYBOOK_YAML,
        "ops-a1b2/inventory/hosts.yml": b"all:\n  children:\n    web: {}\n",
    }

    preview = preview_project_bundle(
        _zip(files),
        allow_single_root=True,
        allow_repository_metadata=True,
    )

    assert preview["selected_entrypoint"] == "playbooks/site.yml"
    assert {item["path"] for item in preview["files"]} == {
        "playbooks/site.yml",
        "inventory/hosts.yml",
    }
    assert preview["ignored_files"] == [".gitlab-ci.yml", "docs/guide.md"]


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_archive_project_path_is_filtered_and_bound_across_preview_and_commit(staff_user, tmp_path):
    archive = _zip(
        {
            "repo-a1b2/.gitlab-ci.yml": b"stages: [test]\n",
            "repo-a1b2/ansible/playbook.yml": PLAYBOOK_YAML,
            "repo-a1b2/ansible/roles/web/tasks/main.yml": b"- ansible.builtin.debug:\n    msg: role\n",
            "repo-a1b2/service/app.py": b"print('not part of ansible')\n",
        }
    )
    client = Client()
    client.force_login(staff_user)
    preview_response = client.post(
        "/bundle/preview/",
        {
            "bundle": SimpleUploadedFile("repository.zip", archive, content_type="application/zip"),
            "project_path": "ansible/",
        },
    )
    assert preview_response.status_code == 200, preview_response.content
    preview = preview_response.json()["preview"]
    assert preview["project_path"] == "ansible"
    assert {item["path"] for item in preview["files"]} == {
        "playbook.yml",
        "roles/web/tasks/main.yml",
    }
    assert preview["ignored_files"] == [".gitlab-ci.yml", "service/app.py"]

    missing_root_binding = client.post(
        "/bundle/commit/",
        {
            "bundle": SimpleUploadedFile("repository.zip", archive, content_type="application/zip"),
            "project_path": "ansible",
            "entrypoint": "playbook.yml",
            "expected_content_hash": preview["content_hash"],
        },
    )
    assert missing_root_binding.status_code == 409
    assert missing_root_binding.json()["code"] == "preview_required"

    with override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=tmp_path / "bundles"):
        committed = client.post(
            "/bundle/commit/",
            {
                "bundle": SimpleUploadedFile("repository.zip", archive, content_type="application/zip"),
                "project_path": "ansible",
                "expected_project_path": preview["project_path"],
                "entrypoint": "playbook.yml",
                "expected_content_hash": preview["content_hash"],
            },
        )
    assert committed.status_code == 201, committed.content
    revision = PlaybookRevision.objects.get(pk=committed.json()["revision"]["id"])
    assert revision.metadata["bundle_project_path"] == "ansible"


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


def test_zip_entry_count_is_rejected_before_zipinfo_materialization(monkeypatch):
    archive = _zip({f"files/item-{index}.txt": b"" for index in range(8)})

    def unexpected_infolist(_archive):
        raise AssertionError("ZIP preflight must reject before infolist allocation")

    monkeypatch.setattr(zipfile.ZipFile, "infolist", unexpected_infolist)
    with pytest.raises(BundleValidationError) as caught:
        inspect_project_bundle(archive, limits=BundleLimits(max_files=4))

    assert caught.value.code == "file_count_limit"


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


def test_preview_redacts_camel_case_secret_pat_and_dependency_credentials():
    password = "literal-database-password"
    gitlab_pat = "glpat-0123456789abcdefghij"
    dependency_url = "https://deploy-user:deploy-password@example.invalid/role.git"
    source = f"""---
- name: {gitlab_pat}
  hosts: all
  vars:
    settings: {{dbPassword: {password}}}
  tasks: []
""".encode()
    requirements = f"roles:\n  - src: {dependency_url}\n".encode()

    preview = preview_project_bundle(_zip({"playbook.yml": source, "requirements.yml": requirements}))

    serialized = json.dumps(preview)
    assert preview["safe_to_commit"] is False
    assert preview["secret_warnings"]
    assert password not in serialized
    assert gitlab_pat not in serialized
    assert dependency_url not in serialized


@pytest.mark.parametrize(
    "token",
    [
        "sk-" + "proj-0123456789abcdefghijklmnop",
        "xox" + "b-0123456789-abcdefghijklmnop",
    ],
)
def test_preview_blocks_and_never_echoes_bare_provider_tokens(token):
    source = PLAYBOOK_YAML.replace(b"msg: ready", f"msg: {token}".encode())

    preview = preview_project_bundle(_zip({"playbook.yml": source}))

    assert preview["safe_to_commit"] is False
    assert token not in json.dumps(preview)


def test_credential_token_in_bundle_path_is_blocked_and_never_echoed(staff_user, tmp_path):
    token = "glpat-0123456789abcdefghij"
    files = {**_valid_files(), f"files/{token}.txt": b"harmless"}
    preview = preview_project_bundle(_zip(files))

    assert preview["safe_to_commit"] is False
    assert token not in json.dumps(preview)
    with pytest.raises(BundleValidationError) as caught:
        commit_project_bundle(
            _zip(files),
            actor=staff_user,
            storage=MediaRootPlaybookBundleStorage(tmp_path),
        )
    assert caught.value.code == "secret_material_detected"


def test_controller_lookup_token_is_never_echoed_in_bundle_preview():
    token = "glpat-0123456789abcdefghij"
    source = f"""- hosts: all
  tasks:
    - debug:
        msg: "{{{{ lookup('{token}', 'value') }}}}"
""".encode()
    preview = preview_project_bundle(_zip({"playbook.yml": source}))

    assert preview["safe_to_commit"] is False
    assert preview["controller_warnings"]
    assert token not in json.dumps(preview)


def test_reference_inventory_identity_is_importable_but_not_exported(staff_user, tmp_path):
    inventory = b"""all:
  hosts:
    web-01:
      ansible_host: 192.0.2.10
      ansible_user: deploy
      ansible_port: 2222
"""
    files = {**_valid_files(), "inventory/hosts.yml": inventory}
    preview = preview_project_bundle(_zip(files))

    assert preview["safe_to_commit"] is True
    assert any(item["kind"] == "inventory_identity" for item in preview["secret_warnings"])
    result = commit_project_bundle(
        _zip(files),
        actor=staff_user,
        storage=MediaRootPlaybookBundleStorage(tmp_path),
    )
    assert result.asset_bundle.file_count == len(files)
    exported = export_revision_bundle(
        result.revision,
        actor=staff_user,
        storage=MediaRootPlaybookBundleStorage(tmp_path),
    )
    with zipfile.ZipFile(BytesIO(exported.content)) as archive:
        assert "inventory/hosts.yml" not in archive.namelist()


@pytest.mark.parametrize(
    ("path", "content"),
    [
        (
            "inventory/hosts.yml",
            b"all:\n  hosts:\n    web:\n      ansible_ssh_pass: SuperSecret123\n",
        ),
        (
            "inventory/hosts.json",
            b'{"all":{"vars":{"ansible_ssh_passphrase":"SuperSecret123"}}}',
        ),
        (
            "inventory/hosts.ini",
            b"[web]\nnode ansible_host=192.0.2.10 ansible_ssh_pass=SuperSecret123\n",
        ),
    ],
)
def test_inventory_password_aliases_are_blocked_without_value_egress(staff_user, tmp_path, path, content):
    files = {**_valid_files(), path: content}
    preview = preview_project_bundle(_zip(files))

    assert preview["safe_to_commit"] is False
    assert "SuperSecret123" not in json.dumps(preview)
    with pytest.raises(BundleValidationError) as caught:
        commit_project_bundle(
            _zip(files),
            actor=staff_user,
            storage=MediaRootPlaybookBundleStorage(tmp_path),
        )
    assert caught.value.code == "secret_material_detected"


@pytest.mark.parametrize("key", ["db_pass", "ssh_passphrase", "ansible_become_pass", "ansible_sudo_pass"])
def test_role_variable_password_aliases_are_blocked(key):
    content = f"{key}: SuperSecret123\n".encode()
    preview = preview_project_bundle(_zip({**_valid_files(), "roles/web/defaults/main.yml": content}))

    assert preview["safe_to_commit"] is False
    assert "SuperSecret123" not in json.dumps(preview)


@pytest.mark.parametrize("secret", ["literal-secret-value", "p@ss word!", "literal secret value", "abc:123!xyz"])
def test_template_inline_camel_case_secret_is_blocked_and_export_sanitizer_redacts_it(secret):
    template = f'<script>const cfg = {{dbPassword: "{secret}"}};</script>\n'.encode()
    files = {**_valid_files(), "templates/app.j2": template}

    preview = preview_project_bundle(_zip(files))
    sanitized, redaction_count = sanitize_file_for_export(
        BundleFile(
            path="templates/app.j2",
            content=template,
            sha256="0" * 64,
            is_text=True,
        )
    )

    assert preview["safe_to_commit"] is False
    assert secret not in json.dumps(preview)
    assert sanitized is not None
    assert secret.encode() not in sanitized
    assert b"__REDACTED__" in sanitized
    assert redaction_count >= 1


@pytest.mark.parametrize("key", ["DBPassword", "APIToken", "OAuthToken"])
def test_minified_json_acronym_secret_is_blocked_and_export_remains_valid_json(key):
    secret = "p@ss word!"
    content = json.dumps({key: secret}, separators=(",", ":")).encode()
    preview = preview_project_bundle(_zip({**_valid_files(), "vars/settings.json": content}))
    sanitized, redaction_count = sanitize_file_for_export(
        BundleFile(
            path="vars/settings.json",
            content=content,
            sha256="0" * 64,
            is_text=True,
        )
    )

    assert preview["safe_to_commit"] is False
    assert secret not in json.dumps(preview)
    assert sanitized is not None
    assert json.loads(sanitized) == {key: "__REDACTED__"}
    assert redaction_count >= 1


@pytest.mark.parametrize(
    "private_key",
    [
        "-----BEGIN ENCRYPTED PRIVATE KEY-----\nsecret\n-----END ENCRYPTED PRIVATE KEY-----\n",
        "-----BEGIN DSA PRIVATE KEY-----\nsecret\n-----END DSA PRIVATE KEY-----\n",
        "-----BEGIN PGP PRIVATE KEY BLOCK-----\nsecret\n-----END PGP PRIVATE KEY BLOCK-----\n",
        "PuTTY-User-Key-File-2: ssh-rsa\nPrivate-Lines: 1\nsecret\nPrivate-MAC: deadbeef\n",
    ],
)
def test_private_key_variants_are_blocked_and_export_redacted(private_key):
    content = private_key.encode()
    preview = preview_project_bundle(_zip({**_valid_files(), "files/material.txt": content}))
    sanitized, redaction_count = sanitize_file_for_export(
        BundleFile(path="files/material.txt", content=content, sha256="0" * 64, is_text=True)
    )

    assert preview["safe_to_commit"] is False
    assert private_key not in json.dumps(preview)
    assert sanitized is not None
    assert b"secret" not in sanitized
    assert redaction_count >= 1


@pytest.mark.parametrize(
    "filename",
    ["playbook.yml", "vars/deep.json"],
)
def test_deep_yaml_and_json_return_controlled_complexity_errors(filename):
    if filename.endswith(".json"):
        files = {"playbook.yml": PLAYBOOK_YAML, filename: ("[" * 1200 + "0" + "]" * 1200).encode()}
    else:
        files = {filename: ("- " + "[" * 1200 + "0" + "]" * 1200).encode()}

    with pytest.raises(BundleValidationError) as caught:
        inspect_project_bundle(_zip(files))

    assert caught.value.code == "yaml_complexity_limit"
    assert caught.value.status_code == 413


def test_preview_reports_yaml_complexity_as_non_committable_without_echoing_content():
    source = b"- &play\n  hosts: all\n  tasks: []\n- *play\n- *play\n"
    preview = preview_project_bundle(
        _zip({"playbook.yml": source}),
        limits=BundleLimits(max_yaml_aliases=1),
    )

    assert preview["safe_to_commit"] is False
    assert preview["complexity_warnings"] == [{"code": "yaml_complexity_limit", "message": "YAML alias limit exceeded"}]
    assert source.decode() not in json.dumps(preview)


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
@override_settings(ROOT_URLCONF=__name__)
def test_viewer_reads_published_bundle_files_without_seeing_unpublished_draft(
    staff_user,
    django_user_model,
    tmp_path,
):
    with override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=tmp_path / "bundles"):
        imported = commit_project_bundle(_zip(_valid_files()), actor=staff_user)
        owner_client = Client()
        owner_client.force_login(staff_user)
        tree_response = owner_client.get(f"/playbooks/{imported.playbook.id}/draft/files/")
        assert tree_response.status_code == 200, tree_response.content
        tree = tree_response.json()["tree"]
        changed = owner_client.patch(
            f"/playbooks/{imported.playbook.id}/draft/file/",
            data=json.dumps(
                {
                    "path": "roles/web/tasks/main.yml",
                    "content": "- ansible.builtin.debug:\n    msg: draft-only\n",
                    "expected_draft_version": tree["draft_version"],
                    "expected_bundle_hash": tree["bundle_hash"],
                }
            ),
            content_type="application/json",
        )
        assert changed.status_code == 200, changed.content

        viewer = django_user_model.objects.create_user(
            username="published-bundle-viewer",
            password="test",
            is_staff=True,
        )
        ProjectMembership.objects.create(
            project=imported.playbook.project,
            user=viewer,
            role=ProjectMembership.ROLE_OPERATOR,
        )
        save_grant(playbook=imported.playbook, actor=staff_user, role="viewer", user=viewer)
        viewer_client = Client()
        viewer_client.force_login(viewer)
        published_tree = viewer_client.get(f"/playbooks/{imported.playbook.id}/draft/files/")
        published_file = viewer_client.get(
            f"/playbooks/{imported.playbook.id}/draft/file/",
            {"path": "roles/web/tasks/main.yml"},
        )
        denied_current = viewer_client.get(
            f"/playbooks/{imported.playbook.id}/draft/file/",
            {"path": "roles/web/tasks/main.yml", "view": "current"},
        )

    assert published_tree.status_code == 200, published_tree.content
    assert published_tree.json()["view"] == "published"
    assert published_tree.json()["tree"]["draft_version"] is None
    assert published_file.status_code == 200, published_file.content
    assert published_file.json()["view"] == "published"
    assert "role-ready" in published_file.json()["file"]["content"]
    assert "draft-only" not in published_file.content.decode()
    assert denied_current.status_code == 403


@pytest.mark.django_db
def test_unsafe_historical_revision_cannot_be_published_or_exported(staff_user):
    playbook = Playbook.objects.create(
        user=staff_user,
        name="Historical unsafe",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml=PLAYBOOK_YAML.decode(),
    )
    unsafe = "- hosts: all\n  vars:\n    api_token: literal-secret-value\n  tasks: []\n"
    revision = PlaybookRevision.objects.create(
        playbook=playbook,
        revision_number=1,
        author=staff_user,
        content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
        source_yaml=unsafe,
        tasks=[],
        content_hash=calculate_content_hash(
            content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
            source_yaml=unsafe,
            tasks=[],
        ),
    )

    with pytest.raises(BundleValidationError) as publish_error:
        publish_revision(playbook, revision, actor=staff_user)
    assert publish_error.value.code == "secret_material_detected"
    assert publish_error.value.status_code == 422
    with pytest.raises(BundleValidationError) as export_error:
        export_revision_bundle(revision, actor=staff_user)
    assert export_error.value.code == "secret_material_detected"


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_unsafe_legacy_published_content_is_owner_remediation_only(staff_user, django_user_model):
    token = "glpat-0123456789abcdefghij"
    source = f"- hosts: all\n  tasks:\n    - debug:\n        msg: {token}\n"
    playbook = Playbook.objects.create(
        user=staff_user,
        name="Unsafe legacy shared",
        kind=Playbook.KIND_ANSIBLE,
        source_yaml=source,
    )
    revision = PlaybookRevision.objects.create(
        playbook=playbook,
        revision_number=1,
        author=staff_user,
        content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
        source_yaml=source,
        tasks=[],
        content_hash=calculate_content_hash(
            content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
            source_yaml=source,
            tasks=[],
        ),
    )
    playbook.origin_revision = revision
    playbook.published_revision = revision
    playbook.save(update_fields=["origin_revision", "published_revision"])
    viewer = django_user_model.objects.create_user(username="unsafe-legacy-viewer", password="test", is_staff=True)
    ProjectMembership.objects.create(
        project=playbook.project,
        user=viewer,
        role=ProjectMembership.ROLE_OPERATOR,
    )
    PlaybookGrant.objects.create(
        playbook=playbook,
        user=viewer,
        role=PlaybookGrant.ROLE_VIEWER,
        can_view=True,
        granted_by=staff_user,
        is_legacy=True,
    )
    manager = django_user_model.objects.create_user(username="unsafe-legacy-manager", password="test", is_staff=True)
    ProjectMembership.objects.create(
        project=playbook.project,
        user=manager,
        role=ProjectMembership.ROLE_OPERATOR,
    )
    PlaybookGrant.objects.create(
        playbook=playbook,
        user=manager,
        role=PlaybookGrant.ROLE_MANAGER,
        can_view=True,
        can_edit=True,
        can_validate=True,
        can_publish=True,
        can_run=True,
        can_export=True,
        can_manage_shares=True,
        granted_by=staff_user,
        is_legacy=True,
    )
    owner_client = Client()
    owner_client.force_login(staff_user)
    viewer_client = Client()
    viewer_client.force_login(viewer)
    manager_client = Client()
    manager_client.force_login(manager)

    owner_detail = owner_client.get(f"/playbooks/{playbook.id}/content/")
    viewer_detail = viewer_client.get(f"/playbooks/{playbook.id}/content/")
    viewer_revision = viewer_client.get(f"/playbooks/{playbook.id}/revisions/{revision.id}/content/")
    viewer_file = viewer_client.get(
        f"/playbooks/{playbook.id}/draft/file/",
        {"path": "playbook.yml", "view": "published"},
    )
    viewer_tree = viewer_client.get(
        f"/playbooks/{playbook.id}/draft/files/",
        {"view": "published"},
    )
    manager_detail = manager_client.get(f"/playbooks/{playbook.id}/content/")
    manager_revision = manager_client.get(f"/playbooks/{playbook.id}/revisions/{revision.id}/content/")
    manager_file = manager_client.get(
        f"/playbooks/{playbook.id}/draft/file/",
        {"path": "playbook.yml", "view": "published"},
    )
    manager_tree = manager_client.get(
        f"/playbooks/{playbook.id}/draft/files/",
        {"view": "published"},
    )
    duplicate = owner_client.post(f"/playbooks/{playbook.id}/duplicate/")

    assert owner_detail.status_code == 200
    assert token in owner_detail.content.decode()
    for response in (
        viewer_detail,
        viewer_revision,
        viewer_file,
        viewer_tree,
        manager_detail,
        manager_revision,
        manager_file,
        manager_tree,
        duplicate,
    ):
        assert response.status_code == 422, response.content
        assert token not in response.content.decode()


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_unsafe_legacy_bundle_token_path_is_not_exposed_in_published_tree(
    staff_user,
    django_user_model,
    tmp_path,
):
    token = "glpat-0123456789abcdefghij"
    files = {"playbook.yml": PLAYBOOK_YAML, f"files/{token}.txt": b"harmless"}
    archive = build_canonical_zip(files)
    bundle_hash = calculate_bundle_content_hash(files)
    with override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=tmp_path / "legacy-bundles"):
        storage = MediaRootPlaybookBundleStorage()
        storage_key = storage.save(archive, content_hash=bundle_hash)
        asset = PlaybookAssetBundle.objects.create(
            storage_key=storage_key,
            manifest=[],
            content_hash=bundle_hash,
            size_bytes=sum(len(content) for content in files.values()),
            file_count=len(files),
            scan_status=PlaybookAssetBundle.SCAN_CLEAN,
            scan_report={"entrypoint": "playbook.yml"},
            created_by=staff_user,
        )
        playbook = Playbook.objects.create(
            user=staff_user,
            name="Unsafe legacy bundle path",
            kind=Playbook.KIND_ANSIBLE,
            source_yaml=PLAYBOOK_YAML.decode(),
        )
        revision = PlaybookRevision.objects.create(
            playbook=playbook,
            revision_number=1,
            author=staff_user,
            content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
            source_yaml=PLAYBOOK_YAML.decode(),
            tasks=[],
            content_hash=calculate_content_hash(
                content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
                source_yaml=PLAYBOOK_YAML.decode(),
                tasks=[],
                bundle_hash=bundle_hash,
            ),
            asset_bundle=asset,
            bundle_hash=bundle_hash,
            metadata={"bundle_entrypoint": "playbook.yml"},
        )
        playbook.origin_revision = revision
        playbook.published_revision = revision
        playbook.save(update_fields=["origin_revision", "published_revision"])
        viewer = django_user_model.objects.create_user(
            username="unsafe-path-viewer",
            password="test",
            is_staff=True,
        )
        ProjectMembership.objects.create(
            project=playbook.project,
            user=viewer,
            role=ProjectMembership.ROLE_OPERATOR,
        )
        PlaybookGrant.objects.create(
            playbook=playbook,
            user=viewer,
            role=PlaybookGrant.ROLE_VIEWER,
            can_view=True,
            granted_by=staff_user,
            is_legacy=True,
        )
        client = Client()
        client.force_login(viewer)
        response = client.get(
            f"/playbooks/{playbook.id}/draft/files/",
            {"view": "published"},
        )

    assert response.status_code == 422, response.content
    assert token not in response.content.decode()


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
def test_safe_export_removes_inventory_references_and_never_serializes_binding_metadata(staff_user, tmp_path):
    storage = MediaRootPlaybookBundleStorage(tmp_path)
    files = {**_valid_files(), "inventory/hosts.yml": b"all:\n  children:\n    web: {}\n"}
    result = commit_project_bundle(_zip(files), actor=staff_user, storage=storage)
    source_yaml = PLAYBOOK_YAML.decode()
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
        exported_files = {name: archive.read(name) for name in archive.namelist()}
        combined = b"\n".join(archive.read(name) for name in archive.namelist())
        assert "inventory/hosts.yml" not in archive.namelist()
        assert b"inventory_bindings" not in combined
        assert b"10.0.0.5" not in combined
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["sanitized"] is True
        assert set(manifest["revision"]) == {"id", "number", "content_hash", "bundle_hash"}
        assert manifest["checksum_algorithm"] == "sha256"
        assert manifest["checksums_file"] == "checksums.sha256"
        checksum_rows = {
            path: digest
            for digest, path in (
                line.split("  ", 1) for line in archive.read("checksums.sha256").decode("utf-8").splitlines()
            )
        }
        assert set(checksum_rows) == set(archive.namelist()) - {"checksums.sha256"}
        for path, digest in checksum_rows.items():
            assert hashlib.sha256(archive.read(path)).hexdigest() == digest
        assert manifest["checksums"] == {
            path: hashlib.sha256(archive.read(path)).hexdigest()
            for path in archive.namelist()
            if path not in {"manifest.json", "checksums.sha256"}
        }
        assert archive.read("files/logo.bin") == _valid_files()["files/logo.bin"]

    inspected_export = inspect_project_bundle(artifact.content)
    assert inspected_export.manifest["checksums_file"] == "checksums.sha256"
    tampered_files = {**exported_files, "playbook.yml": exported_files["playbook.yml"] + b"\n# tampered\n"}
    with pytest.raises(BundleValidationError) as checksum_error:
        inspect_project_bundle(_zip(tampered_files))
    assert checksum_error.value.code == "bundle_checksum_mismatch"


def test_media_storage_rejects_keys_outside_its_scoped_root(tmp_path):
    storage = MediaRootPlaybookBundleStorage(tmp_path)
    with pytest.raises(BundleStorageError):
        storage.read("../outside.zip", max_bytes=100)


@pytest.mark.parametrize(
    "reserved_path",
    ["extra_vars.json", "inventory.ini", "known_hosts", "key_1", "./key_42", ".\\known_hosts"],
)
def test_runtime_project_rejects_runner_owned_secret_files(tmp_path, reserved_path):
    with pytest.raises(AnsibleProjectError):
        materialize_ansible_project(
            tmp_path,
            playbook_yaml=PLAYBOOK_YAML.decode(),
            project_files={reserved_path: b"must-not-materialize"},
        )


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
def test_preview_and_commit_block_controller_escape_hidden_in_bundle_role(staff_user, tmp_path):
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
    preview = preview_project_bundle(_zip(files))
    assert preview["safe_to_commit"] is False
    assert any(item["code"] == "controller_delegate_forbidden" for item in preview["controller_warnings"])
    with (
        override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=tmp_path / "bundles"),
        pytest.raises(BundleValidationError) as caught,
    ):
        commit_project_bundle(_zip(files), actor=staff_user)
    assert caught.value.code == "controller_policy_violation"
    assert caught.value.status_code == 422


def test_preview_blocks_role_dependency_path_escape():
    files = {
        **_valid_files(),
        "roles/web/meta/main.yml": b"dependencies:\n  - role: ../../../../tmp/controller-role\n",
    }

    preview = preview_project_bundle(_zip(files))

    assert preview["safe_to_commit"] is False
    assert any(item["code"] == "controller_path_forbidden" for item in preview["controller_warnings"])


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
            "expected_content_hash": preview.json()["preview"]["content_hash"],
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


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_draft_project_file_patch_is_clone_on_write_and_rejects_stale_or_read_only_paths(
    staff_user,
    tmp_path,
):
    storage_root = tmp_path / "bundles"
    with override_settings(PLAYBOOK_BUNDLE_STORAGE_ROOT=storage_root):
        result = commit_project_bundle(_zip(_valid_files()), actor=staff_user)
        original_asset_id = result.asset_bundle.id
        original_bundle_hash = result.asset_bundle.content_hash
        client = Client()
        client.force_login(staff_user)

        tree_response = client.get(f"/playbooks/{result.playbook.id}/draft/files/")
        assert tree_response.status_code == 200, tree_response.content
        tree = tree_response.json()["tree"]
        rows = {item["path"]: item for item in tree["files"]}
        assert rows["playbook.yml"]["editable"] is True
        assert rows["roles/web/tasks/main.yml"]["editable"] is True
        assert rows["requirements.yml"]["editable"] is False
        assert rows["templates/site.conf.j2"]["editable"] is False

        changed_role = "- name: Changed role task\n  ansible.builtin.debug:\n    msg: changed\n"
        patched = client.patch(
            f"/playbooks/{result.playbook.id}/draft/file/",
            data=json.dumps(
                {
                    "path": "roles/web/tasks/main.yml",
                    "content": changed_role,
                    "expected_draft_version": tree["draft_version"],
                    "expected_bundle_hash": tree["bundle_hash"],
                }
            ),
            content_type="application/json",
        )
        assert patched.status_code == 200, patched.content
        payload = patched.json()
        assert payload["file"]["content"] == changed_role
        assert payload["draft"]["asset_bundle_id"] != original_asset_id
        assert payload["draft"]["bundle_hash"] != original_bundle_hash
        result.revision.refresh_from_db()
        assert result.revision.asset_bundle_id == original_asset_id
        assert result.revision.bundle_hash == original_bundle_hash

        opened = client.get(
            f"/playbooks/{result.playbook.id}/draft/file/",
            {"path": "roles/web/tasks/main.yml"},
        )
        assert opened.status_code == 200
        assert opened.json()["file"]["content"] == changed_role
        base_file = client.get(
            f"/playbooks/{result.playbook.id}/draft/file/",
            {"path": "roles/web/tasks/main.yml", "view": "base"},
        )
        assert base_file.status_code == 200, base_file.content
        assert base_file.json()["view"] == "base"
        assert base_file.json()["file"]["content"] != changed_role

        current = payload["draft"]
        stale = client.patch(
            f"/playbooks/{result.playbook.id}/draft/file/",
            data=json.dumps(
                {
                    "path": "roles/web/tasks/main.yml",
                    "content": changed_role,
                    "expected_version": current["version"],
                    "expected_bundle_hash": original_bundle_hash,
                }
            ),
            content_type="application/json",
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "playbook_draft_conflict"

        for path_value, expected_status in (("templates/site.conf.j2", 422), ("roles/web/tasks/new.yml", 404)):
            denied = client.patch(
                f"/playbooks/{result.playbook.id}/draft/file/",
                data=json.dumps(
                    {
                        "path": path_value,
                        "content": "safe\n",
                        "expected_draft_version": current["version"],
                        "expected_bundle_hash": current["bundle_hash"],
                    }
                ),
                content_type="application/json",
            )
            assert denied.status_code == expected_status, denied.content
