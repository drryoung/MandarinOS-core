"""
Tests for the one-time learner-memory corruption migration.

Verifies:
  1. Corrupt place values ("等你等", compound junk strings) are cleared.
  2. Valid place values (新西兰, 达尼丁, 新西兰南岛, Dunedin, 北京) are preserved or
     correctly canonicalised, not damaged.
  3. Non-place fields with junk prefixes are stripped.
  4. Non-place fields without junk are not modified.
  5. The migration is idempotent (running twice yields no further changes).
  6. Dry-run mode does not modify the file on disk.
  7. reset_memory (clear()) still zeroes every field after migration.
  8. No "等你等" survives in learner_memory.json after migration.
  9. migrate_corrupted_memory handles a missing file gracefully.
 10. The CLI script (migrate_learner_memory.py) is importable and callable.
"""

import importlib.util
import json
import sys
import pathlib
import tempfile

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO_ROOT / "scripts"

# ── Module loading helpers ──────────────────────────────────────────────────


def _load_learner_memory(tmp_path: pathlib.Path):
    """Load learner_memory module pointing its persistence file at tmp_path."""
    spec = importlib.util.spec_from_file_location(
        "lm_mig", _SCRIPTS / "learner_memory.py"
    )
    mod = importlib.util.module_from_spec(spec)
    # Redirect persistence path to temp dir before exec so _store starts fresh.
    import os
    old_env = os.environ.get("MANDARINOS_DATA_DIR")
    os.environ["MANDARINOS_DATA_DIR"] = str(tmp_path)
    try:
        spec.loader.exec_module(mod)
    finally:
        if old_env is None:
            os.environ.pop("MANDARINOS_DATA_DIR", None)
        else:
            os.environ["MANDARINOS_DATA_DIR"] = old_env
    return mod


def _write_memory_file(path: pathlib.Path, data: dict) -> pathlib.Path:
    f = path / "learner_memory.json"
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp(tmp_path):
    return tmp_path


# ── 1. Corrupt place values are cleared ────────────────────────────────────


class TestCorruptPlaceValuesCleared:
    """ASR-junk place values must be cleaned to None or a canonical place after migration."""

    def _migrate(self, tmp, lives_in_value):
        _write_memory_file(tmp, {
            "test_learner": {
                "learner_name": None,
                "hometown": "新西兰",
                "lives_in": lives_in_value,
                "job_or_study": None,
                "family": None,
                "favourite_food": None,
            }
        })
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        learners, fields, log = mod.migrate_corrupted_memory(path=target)
        result = json.loads(target.read_text(encoding="utf-8"))
        return result["test_learner"]["lives_in"], learners, fields, log

    # Cases where junk is unrecoverable — field must become None.
    @pytest.mark.parametrize("junk", [
        "等你等",
        "等你等是圣希兰南方",   # verb residual "是圣希兰南方" after stripping
        "，等你等",
        "的那等",               # strips to single char "那" — too short
    ])
    def test_unrecoverable_junk_is_cleared(self, tmp, junk):
        lives_in_after, _, fields, _ = self._migrate(tmp, junk)
        assert lives_in_after is None, (
            f"Expected lives_in=None after cleaning {junk!r}, got {lives_in_after!r}"
        )
        assert fields >= 1, "At least one field must be reported as changed"

    # Cases where junk prefix is stripped but a valid place is recovered.
    @pytest.mark.parametrize("junk,expected", [
        ("等你等新西兰的南方", "新西兰南岛"),   # NZ region recovery
        ("等你等Dunedin的南方", "达尼丁"),       # English alias recovery
    ])
    def test_junk_prefix_stripped_valid_place_recovered(self, tmp, junk, expected):
        lives_in_after, _, fields, _ = self._migrate(tmp, junk)
        assert lives_in_after == expected, (
            f"Expected lives_in={expected!r} after cleaning {junk!r}, got {lives_in_after!r}"
        )
        # May or may not count as a field change depending on whether the value
        # shifted from the junk string to the canonical form.
        assert "等你等" not in (lives_in_after or "")

    def test_pure_junk_hometown_is_cleared(self, tmp):
        _write_memory_file(tmp, {
            "learner_x": {
                "learner_name": None,
                "hometown": "等你等",
                "lives_in": None,
                "job_or_study": None,
                "family": None,
                "favourite_food": None,
            }
        })
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        mod.migrate_corrupted_memory(path=target)
        result = json.loads(target.read_text(encoding="utf-8"))
        assert result["learner_x"]["hometown"] is None

    def test_no_等你等_survives_in_file_after_migration(self, tmp):
        """Full scan: no "等你等" substring must remain in any field after migration."""
        data = {
            f"learner_{i}": {
                "learner_name": None,
                "hometown": "新西兰" if i % 2 == 0 else None,
                "lives_in": "等你等",
                "job_or_study": None,
                "family": None,
                "favourite_food": None,
            }
            for i in range(10)
        }
        _write_memory_file(tmp, data)
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        mod.migrate_corrupted_memory(path=target)
        raw = target.read_text(encoding="utf-8")
        assert "等你等" not in raw, (
            "After migration, no '等你等' must remain in learner_memory.json"
        )


# ── 2. Valid place values are preserved ────────────────────────────────────


class TestValidPlaceValuesPreserved:
    """Clean place values must survive migration unchanged or canonically equivalent."""

    @pytest.mark.parametrize("field,value,expected", [
        ("hometown", "新西兰", "新西兰"),
        ("hometown", "北京", "北京"),
        ("hometown", "成都", "成都"),
        ("lives_in", "达尼丁", "达尼丁"),
        ("lives_in", "新西兰南岛", "新西兰南岛"),
        ("lives_in", "Dunedin", "达尼丁"),        # alias → canonical
        ("lives_in", "Auckland", "奥克兰"),        # alias → canonical
        ("hometown", "上海", "上海"),
    ])
    def test_valid_value_preserved_or_canonicalised(self, tmp, field, value, expected):
        data = {
            "learner_valid": {
                "learner_name": None,
                "hometown": value if field == "hometown" else None,
                "lives_in": value if field == "lives_in" else None,
                "job_or_study": None,
                "family": None,
                "favourite_food": None,
            }
        }
        _write_memory_file(tmp, data)
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        mod.migrate_corrupted_memory(path=target)
        result = json.loads(target.read_text(encoding="utf-8"))
        assert result["learner_valid"][field] == expected, (
            f"{field}={value!r}: expected {expected!r}, got {result['learner_valid'][field]!r}"
        )

    def test_none_fields_stay_none(self, tmp):
        data = {"learner_none": {k: None for k in
                ("learner_name", "hometown", "lives_in", "job_or_study", "family", "favourite_food")}}
        _write_memory_file(tmp, data)
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        learners, fields, _ = mod.migrate_corrupted_memory(path=target)
        assert fields == 0, "All-None record must not be counted as changed"


# ── 3. Non-place fields: junk stripped; clean values untouched ─────────────


class TestNonPlaceFields:
    def _migrate(self, tmp, data):
        _write_memory_file(tmp, data)
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        mod.migrate_corrupted_memory(path=target)
        return json.loads(target.read_text(encoding="utf-8"))

    def test_junk_prefix_stripped_from_non_place_field(self, tmp):
        data = {"lx": {
            "learner_name": None, "hometown": None, "lives_in": None,
            "job_or_study": "等你等老师", "family": None, "favourite_food": None,
        }}
        result = self._migrate(tmp, data)
        # junk stripped; remaining text "老师" is a valid short string
        assert "等你等" not in (result["lx"]["job_or_study"] or "")

    def test_clean_learner_name_not_damaged(self, tmp):
        data = {"lx": {
            "learner_name": "Alice", "hometown": None, "lives_in": None,
            "job_or_study": None, "family": None, "favourite_food": None,
        }}
        result = self._migrate(tmp, data)
        assert result["lx"]["learner_name"] == "Alice"

    def test_clean_job_not_damaged(self, tmp):
        data = {"lx": {
            "learner_name": None, "hometown": None, "lives_in": None,
            "job_or_study": "老师", "family": None, "favourite_food": None,
        }}
        result = self._migrate(tmp, data)
        assert result["lx"]["job_or_study"] == "老师"


# ── 4. Idempotency ─────────────────────────────────────────────────────────


class TestIdempotency:
    def test_migrating_twice_yields_no_further_changes(self, tmp):
        data = {
            "learner_a": {
                "learner_name": "rimant", "hometown": "新西兰",
                "lives_in": "等你等", "job_or_study": None,
                "family": None, "favourite_food": None,
            },
            "learner_b": {
                "learner_name": None, "hometown": "北京",
                "lives_in": "达尼丁", "job_or_study": None,
                "family": None, "favourite_food": None,
            },
        }
        _write_memory_file(tmp, data)
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        _, first_changes, _ = mod.migrate_corrupted_memory(path=target)
        _, second_changes, _ = mod.migrate_corrupted_memory(path=target)
        assert second_changes == 0, (
            f"Second migration must report 0 changes (got {second_changes})"
        )


# ── 5. Dry-run does not write the file ─────────────────────────────────────


class TestDryRun:
    def test_dry_run_does_not_modify_file(self, tmp):
        data = {"lx": {
            "learner_name": None, "hometown": None,
            "lives_in": "等你等", "job_or_study": None,
            "family": None, "favourite_food": None,
        }}
        _write_memory_file(tmp, data)
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        original_text = target.read_text(encoding="utf-8")

        learners, fields, log = mod.migrate_corrupted_memory(path=target, dry_run=True)

        assert target.read_text(encoding="utf-8") == original_text, (
            "Dry-run must not modify the file on disk"
        )
        assert fields >= 1, "Dry-run must still report what would change"
        assert any("dry-run" in line for line in log)

    def test_dry_run_log_describes_change(self, tmp):
        data = {"lx": {
            "learner_name": None, "hometown": "新西兰",
            "lives_in": "等你等新西兰的南方", "job_or_study": None,
            "family": None, "favourite_food": None,
        }}
        _write_memory_file(tmp, data)
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        _, _, log = mod.migrate_corrupted_memory(path=target, dry_run=True)
        combined = "\n".join(log)
        assert "lives_in" in combined
        assert "等你等新西兰的南方" in combined


# ── 6. clear() still works after migration ────────────────────────────────


class TestClearAfterMigration:
    def test_clear_zeros_all_fields(self, tmp):
        data = {
            "learner_z": {
                "learner_name": "rimant",
                "hometown": "新西兰",
                "lives_in": "达尼丁",
                "job_or_study": None,
                "family": None,
                "favourite_food": None,
            }
        }
        _write_memory_file(tmp, data)
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        mod.migrate_corrupted_memory(path=target)
        mod.clear("learner_z")
        result = mod.load("learner_z")
        for field in mod.LEARNER_MEMORY_KEYS:
            assert result[field] is None, f"{field} must be None after clear()"

    def test_no_junk_survives_clear(self, tmp):
        data = {
            "learner_z": {
                "learner_name": None,
                "hometown": "新西兰",
                "lives_in": "等你等新西兰的南方",
                "job_or_study": None,
                "family": None,
                "favourite_food": None,
            }
        }
        _write_memory_file(tmp, data)
        mod = _load_learner_memory(tmp)
        mod.clear("learner_z")
        on_disk = json.loads((tmp / "learner_memory.json").read_text(encoding="utf-8"))
        mem = on_disk.get("learner_z", {})
        assert mem.get("lives_in") is None


# ── 7. Missing file is handled gracefully ─────────────────────────────────


class TestMissingFile:
    def test_migrate_missing_file_returns_zero(self, tmp):
        mod = _load_learner_memory(tmp)
        missing = tmp / "does_not_exist.json"
        learners, fields, log = mod.migrate_corrupted_memory(path=missing)
        assert learners == 0
        assert fields == 0
        assert log


# ── 8. CLI script is importable and callable ───────────────────────────────


class TestCLIScript:
    def test_cli_script_importable(self):
        cli_path = _SCRIPTS / "migrate_learner_memory.py"
        assert cli_path.is_file(), "migrate_learner_memory.py must exist in scripts/"
        spec = importlib.util.spec_from_file_location("migrate_cli", cli_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(getattr(mod, "main", None)), "CLI module must have a main() function"

    def test_cli_dry_run_exits_zero(self, tmp):
        cli_path = _SCRIPTS / "migrate_learner_memory.py"
        data = {"lx": {
            "learner_name": None, "hometown": "新西兰",
            "lives_in": "等你等", "job_or_study": None,
            "family": None, "favourite_food": None,
        }}
        target = tmp / "learner_memory.json"
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        spec = importlib.util.spec_from_file_location("migrate_cli2", cli_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        rc = mod.main(["--dry-run", "--path", str(target)])
        assert rc == 0

    def test_cli_has_dry_run_flag_in_help(self):
        cli_path = _SCRIPTS / "migrate_learner_memory.py"
        spec = importlib.util.spec_from_file_location("migrate_cli3", cli_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        parser = mod._build_parser()
        help_text = parser.format_help()
        assert "--dry-run" in help_text
        assert "--path" in help_text


# ── 9. Realistic data snapshot (regression) ───────────────────────────────


class TestRealisticSnapshot:
    """Simulate the actual corrupt entries found in the live learner_memory.json."""

    _SNAPSHOT = {
        "learner_1779441865679": {
            "learner_name": None,
            "hometown": "新西兰",
            "lives_in": "等你等是圣希兰南方",
            "job_or_study": None, "family": None, "favourite_food": None,
        },
        "learner_1778820892173": {
            "learner_name": None,
            "hometown": "新西兰",
            "lives_in": "等你等",
            "job_or_study": None, "family": None, "favourite_food": None,
        },
        "interaction_regression_tester": {
            "learner_name": "rimant",
            "hometown": "新西兰",
            "lives_in": "等你等",
            "job_or_study": None, "family": None, "favourite_food": None,
        },
        "learner_valid_nz": {
            "learner_name": None,
            "hometown": "新西兰",
            "lives_in": "达尼丁",
            "job_or_study": None, "family": None, "favourite_food": None,
        },
        "learner_valid_bj": {
            "learner_name": None,
            "hometown": "北京",
            "lives_in": "上海",
            "job_or_study": None, "family": None, "favourite_food": None,
        },
    }

    def test_all_junk_lives_in_cleared(self, tmp):
        _write_memory_file(tmp, self._SNAPSHOT)
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        mod.migrate_corrupted_memory(path=target)
        result = json.loads(target.read_text(encoding="utf-8"))

        # "等你等是圣希兰南方" → verb residual "是圣希兰南方" → None
        assert result["learner_1779441865679"]["lives_in"] is None, (
            f"Got: {result['learner_1779441865679']['lives_in']!r}"
        )
        # "等你等" → None
        assert result["learner_1778820892173"]["lives_in"] is None
        assert result["interaction_regression_tester"]["lives_in"] is None

    def test_valid_entries_preserved(self, tmp):
        _write_memory_file(tmp, self._SNAPSHOT)
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        mod.migrate_corrupted_memory(path=target)
        result = json.loads(target.read_text(encoding="utf-8"))

        assert result["learner_valid_nz"]["lives_in"] == "达尼丁"
        assert result["learner_valid_nz"]["hometown"] == "新西兰"
        assert result["learner_valid_bj"]["hometown"] == "北京"
        assert result["learner_valid_bj"]["lives_in"] == "上海"

    def test_junk_string_absent_after_migration(self, tmp):
        _write_memory_file(tmp, self._SNAPSHOT)
        mod = _load_learner_memory(tmp)
        target = tmp / "learner_memory.json"
        mod.migrate_corrupted_memory(path=target)
        raw = target.read_text(encoding="utf-8")
        assert "等你等" not in raw
