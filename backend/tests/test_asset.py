"""资产复用库测试"""
import tempfile
from pathlib import Path

import pytest

from ai_memory.core.types import AssetType
from ai_memory.storage.database import Database
from ai_memory.asset.registry import AssetRegistry, Asset


@pytest.fixture
def setup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        db.initialize()
        registry = AssetRegistry(db)

        artifact_dir = Path(tmpdir) / "artifacts" / "decompile"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "classes.dex").write_text("fake dex")
        (artifact_dir / "AndroidManifest.xml").write_text("<manifest/>")

        source_file = Path(tmpdir) / "test.apk"
        source_file.write_bytes(b"fake apk content for hash test")

        yield {
            "db": db,
            "registry": registry,
            "tmpdir": tmpdir,
            "artifact_dir": str(artifact_dir),
            "source_file": str(source_file),
        }
        db.close()


class TestAssetRegistry:
    def test_register_and_get(self, setup):
        asset = Asset(
            name="Test Decompile",
            type=AssetType.DECOMPILE,
            artifact_path=setup["artifact_dir"],
            source_path=setup["source_file"],
            tags=["test", "decompile"],
            project="ingo",
        )
        registered = setup["registry"].register(asset)
        assert registered.source_hash is not None
        assert registered.artifact_size > 0

        loaded = setup["registry"].get(registered.id)
        assert loaded is not None
        assert loaded.name == "Test Decompile"
        assert loaded.source_hash == registered.source_hash

    def test_lookup_by_hash(self, setup):
        source_hash = AssetRegistry.compute_hash(setup["source_file"])
        asset = Asset(
            name="APK Decompile",
            type=AssetType.DECOMPILE,
            artifact_path=setup["artifact_dir"],
            source_hash=source_hash,
        )
        setup["registry"].register(asset)

        results = setup["registry"].lookup(source_hash=source_hash)
        assert len(results) == 1
        assert results[0].name == "APK Decompile"

    def test_lookup_by_tags(self, setup):
        asset = Asset(
            name="jadx tool",
            type=AssetType.TOOL,
            artifact_path=setup["artifact_dir"],
            tags=["jadx", "decompiler"],
        )
        setup["registry"].register(asset)

        results = setup["registry"].lookup(tags=["jadx"])
        assert len(results) == 1

        results = setup["registry"].lookup(tags=["nonexistent"])
        assert len(results) == 0

    def test_validate_valid(self, setup):
        asset = Asset(
            name="Valid Asset",
            type=AssetType.DATA,
            artifact_path=setup["artifact_dir"],
            source_path=setup["source_file"],
        )
        registered = setup["registry"].register(asset)

        result = setup["registry"].validate(registered.id)
        assert result["valid"] is True

    def test_validate_missing_path(self, setup):
        asset = Asset(
            name="Missing Asset",
            type=AssetType.DATA,
            artifact_path="/nonexistent/path/xxx",
        )
        registered = setup["registry"].register(asset)

        result = setup["registry"].validate(registered.id)
        assert result["valid"] is False

    def test_validate_changed_source(self, setup):
        asset = Asset(
            name="Changed Source",
            type=AssetType.DECOMPILE,
            artifact_path=setup["artifact_dir"],
            source_path=setup["source_file"],
        )
        registered = setup["registry"].register(asset)

        Path(setup["source_file"]).write_bytes(b"modified content!")

        result = setup["registry"].validate(registered.id)
        assert result["valid"] is False

    def test_use_increments_count(self, setup):
        asset = Asset(
            name="Use Test",
            type=AssetType.TOOL,
            artifact_path=setup["artifact_dir"],
        )
        registered = setup["registry"].register(asset)

        setup["registry"].use(registered.id)
        setup["registry"].use(registered.id)

        loaded = setup["registry"].get(registered.id)
        assert loaded.use_count == 2
        assert loaded.last_used_at is not None

    def test_invalidate(self, setup):
        asset = Asset(
            name="To Invalidate",
            type=AssetType.SCRIPT,
            artifact_path=setup["artifact_dir"],
        )
        registered = setup["registry"].register(asset)

        setup["registry"].invalidate(registered.id, "过时了")

        loaded = setup["registry"].get(registered.id)
        assert loaded.valid is False
        assert loaded.invalid_reason == "过时了"

        results = setup["registry"].lookup(valid_only=True)
        assert all(a.id != registered.id for a in results)

    def test_compute_hash(self, setup):
        h = AssetRegistry.compute_hash(setup["source_file"])
        assert h is not None
        assert len(h) == 64

        h2 = AssetRegistry.compute_hash("/nonexistent/file")
        assert h2 is None
