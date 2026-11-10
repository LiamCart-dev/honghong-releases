#!/usr/bin/env python3
"""校验上传产物，生成 Release 元数据和旧版客户端清单。"""

import argparse
import hashlib
import json
import re
from pathlib import Path


def prepare(upload: Path, manifest: Path, repository: str, ref: str, output: Path):
    meta = json.loads((upload / "meta.json").read_text(encoding="utf-8"))
    name = meta["versionName"]
    channel = meta["channel"]
    semver = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    pattern = semver if channel == "stable" else semver + r"-dev"
    if channel not in ("stable", "dev") or not re.fullmatch(pattern, name):
        raise ValueError("版本名与 stable/dev 渠道不匹配")
    tag = f"v{name}"
    if ref != f"upload/{tag}":
        raise ValueError("上传分支与 meta.versionName 不匹配")
    code = meta["versionCode"]
    if type(code) is not int or not 0 < code <= 2_100_000_000:
        raise ValueError("versionCode 必须为有效 Android 正整数")
    minimum = meta["minSupportedVersionCode"]
    if type(minimum) is not int or not 0 <= minimum <= code:
        raise ValueError("minSupportedVersionCode 必须在 0..versionCode 范围内")
    if type(meta["force"]) is not bool:
        raise ValueError("force 必须为布尔值")
    for key in ("changelog", "commit", "publishedAt"):
        if not isinstance(meta[key], str) or not meta[key].strip():
            raise ValueError(f"{key} 不能为空")
    apk_name = f"honghong-{name}.apk"
    if meta["apkName"] != apk_name:
        raise ValueError("apkName 与版本名不匹配")
    apk = upload / apk_name
    if not apk.is_file() or apk.stat().st_size == 0:
        raise ValueError("APK 不存在或为空")
    if type(meta["size"]) is not int or apk.stat().st_size != meta["size"]:
        raise ValueError("APK 大小与元数据不符")
    with apk.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    if sha != meta["sha256"]:
        raise ValueError("APK SHA-256 与元数据不符")

    previous = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    channels = previous.get("channels", {})
    codes = [previous["versionCode"]] if "versionCode" in previous else []
    codes.extend(entry["versionCode"] for entry in channels.values())
    if any(type(value) is not int or value <= 0 for value in codes):
        raise ValueError("现有 version.json 含无效 versionCode")
    if codes and code <= max(codes):
        raise ValueError(f"versionCode {code} 必须高于已发布的 {max(codes)}")

    meta["apkUrl"] = f"https://github.com/{repository}/releases/download/{tag}/{apk_name}"
    channels[channel] = meta.copy()
    version = {**meta, "channels": channels}
    output.mkdir(parents=True, exist_ok=True)
    for filename, data in (("meta.json", meta), ("version.json", version)):
        (output / filename).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    (output / "notes.md").write_text(meta["changelog"] + "\n", encoding="utf-8")
    return {"tag": tag, "apk": str(apk), "prerelease": str(channel == "dev").lower()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = prepare(**vars(args))
    for key, value in values.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
