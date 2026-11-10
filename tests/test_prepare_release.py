import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "prepare_release", Path(__file__).resolve().parents[1] / "prepare_release.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PrepareReleaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upload = self.root / "upload"
        self.upload.mkdir()
        self.manifest = self.root / "version.json"
        self.output = self.root / "output"
        self.apk = self.upload / "honghong-0.1.26.apk"
        self.apk.write_bytes(b"test APK bytes")
        self.meta = {
            "versionName": "0.1.26",
            "versionCode": 126,
            "channel": "stable",
            "apkName": self.apk.name,
            "sha256": hashlib.sha256(self.apk.read_bytes()).hexdigest(),
            "size": self.apk.stat().st_size,
            "changelog": "修复提醒\n支持更新",
            "force": True,
            "minSupportedVersionCode": 126,
            "commit": "a" * 40,
            "publishedAt": "2026-11-10T07:00:00Z",
        }

    def run_prepare(self, ref=None):
        (self.upload / "meta.json").write_text(json.dumps(self.meta), encoding="utf-8")
        return module.prepare(
            self.upload, self.manifest, "LiamCart-dev/honghong-releases",
            ref or f"upload/v{self.meta['versionName']}", self.output,
        )

    def test_stable_preserves_metadata_and_other_channel(self):
        old_dev = {"versionCode": 125, "versionName": "0.1.25-dev", "channel": "dev"}
        self.manifest.write_text(json.dumps({"versionCode": 77, "channels": {"dev": old_dev}}))
        result = self.run_prepare()
        published = json.loads((self.output / "meta.json").read_text())
        version = json.loads((self.output / "version.json").read_text())
        for key, value in self.meta.items():
            self.assertEqual(published[key], value)
        self.assertEqual(published["apkUrl"], "https://github.com/LiamCart-dev/honghong-releases/releases/download/v0.1.26/honghong-0.1.26.apk")
        self.assertEqual(version["channels"], {"dev": old_dev, "stable": published})
        self.assertEqual({k: v for k, v in version.items() if k != "channels"}, published)
        self.assertEqual(result["prerelease"], "false")
        self.assertEqual((self.output / "notes.md").read_text(), self.meta["changelog"] + "\n")

    def test_dev_first_release(self):
        self.meta.update(versionName="0.1.26-dev", channel="dev", apkName="honghong-0.1.26-dev.apk")
        self.apk.rename(self.upload / self.meta["apkName"])
        self.assertEqual(self.run_prepare()["prerelease"], "true")
        self.assertEqual(json.loads((self.output / "version.json").read_text())["channel"], "dev")

    def test_rejects_nonincreasing_code_across_channels(self):
        for prior in (
            {"versionCode": 126},
            {"versionCode": 77, "channels": {"dev": {"versionCode": 127}}},
        ):
            with self.subTest(prior=prior):
                self.manifest.write_text(json.dumps(prior))
                with self.assertRaisesRegex(ValueError, "必须高于"):
                    self.run_prepare()
                self.assertFalse(self.output.exists())

    def test_rejects_invalid_stable_and_channel(self):
        for name, channel in (("0.1.26-dev", "stable"), ("01.1.26", "stable"), ("0.1.26+1", "stable"), ("0.1.26", "ci"), ("0.1.26", "dev")):
            with self.subTest(name=name, channel=channel):
                self.meta.update(versionName=name, channel=channel)
                with self.assertRaises(ValueError):
                    self.run_prepare()

    def test_rejects_branch_mismatch(self):
        with self.assertRaisesRegex(ValueError, "上传分支"):
            self.run_prepare("upload/v0.1.27")

    def test_rejects_missing_metadata_and_apk(self):
        with self.assertRaises(FileNotFoundError):
            module.prepare(self.upload, self.manifest, "owner/repo", "upload/v0.1.26", self.output)
        self.apk.unlink()
        with self.assertRaisesRegex(ValueError, "APK 不存在"):
            self.run_prepare()

    def test_rejects_changed_apk_and_size(self):
        self.apk.write_bytes(b"changed APK!!!")
        self.meta["size"] = self.apk.stat().st_size
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.run_prepare()
        self.meta["size"] += 1
        with self.assertRaisesRegex(ValueError, "大小"):
            self.run_prepare()


if __name__ == "__main__":
    unittest.main()
