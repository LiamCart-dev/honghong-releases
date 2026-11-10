# 哄哄公开发布仓库

此目录是独立公开仓库的完整模板，拟使用 `LiamCart-dev/honghong-releases`，默认分支为 `main`。源码继续保存在私有仓库 `LiamCart-dev/honghong`。公开仓库只接收发布流程、APK、发布说明与元数据。

## 初始化与连接

创建公开仓库、上传文件、配置 Deploy Key 和触发发布前，需要取得用户对具体仓库及操作的明确批准。此模板不会自动创建仓库或发布版本。

批准后，在源码仓库根目录执行以下命令；它们将创建公开仓库并推送模板：

```bash
RELEASES_REPO=LiamCart-dev/honghong-releases
release_dir=$(mktemp -d)
cp -R backend/releases-repository/. "$release_dir/"
git -C "$release_dir" init -b main
git -C "$release_dir" add .
git -C "$release_dir" commit -m "chore: initialize Android release repository"
gh repo create "$RELEASES_REPO" --public --source "$release_dir" --remote origin --push
gh variable set RELEASES_REPO --repo LiamCart-dev/honghong --body "$RELEASES_REPO"
```

若仓库已存在，应先克隆并检查现有 `main` 和 `version.json`，再合并模板；不要覆盖现有清单。公开仓库需启用 Actions，允许工作流使用 `contents: write` 向 `main` 提交清单，并创建 Release。分支规则不得阻止该工作流的直接提交。

源码工作流通过 `RELEASES_DEPLOY_KEY` 向公开仓库推送 `upload/v*` 分支。已有密钥若确实属于这个发布链路，可只在目标仓库授权对应公钥；否则，经批准创建专用密钥：

```bash
key_dir=$(mktemp -d)
chmod 700 "$key_dir"
ssh-keygen -t ed25519 -N '' -C honghong-releases -f "$key_dir/releases"
gh repo deploy-key add "$key_dir/releases.pub" --repo "$RELEASES_REPO" --allow-write --title honghong-source-ci
gh secret set RELEASES_DEPLOY_KEY --repo LiamCart-dev/honghong < "$key_dir/releases"
rm -f "$key_dir/releases" "$key_dir/releases.pub"
rmdir "$key_dir"
```

Deploy Key 的 SSH 推送会触发公开仓库自己的工作流。公开仓库使用自己的 `GITHUB_TOKEN` 发布，无需保存源码仓库凭据、Android 签名密钥或服务器 SSH 密钥。源码仓库的 Android 签名配置必须沿用已安装版本的签名身份。

## 版本和产物契约

源码的 `Android APK` 工作流保留三种入口：`master` push / PR 只检查和构建；在 `master` 手动运行发布 dev；推送带非空说明的 `vX.Y.Z` 注释标签发布 stable。stable 标签只接受严格的三段数字版本，主次版本必须与 `app/pubspec.yaml` 一致。

Android `versionCode = 100 + github.run_number`。历史下载版本已出现 `versionCode=77`，当前源码工作流运行编号约为 25；直接使用运行编号会使 Android 无法覆盖更新。固定基数 100 保证当前新构建超过历史版本，后续继续随运行编号递增。dev 的 `versionName` 仍为 `<pubspec 主.次>.<run_number>-dev`，正式版名仍取标签。不要降低基数；若迁移或重建工作流导致编号重置，应在发版前按已发布最高 `versionCode` 调整基数。

公开仓库工作流在创建 Release 前执行以下约束：

- 上传分支必须等于 `upload/v<meta.versionName>`，stable / dev 版本名与渠道匹配。
- `meta.json` 和对应的 `honghong-<versionName>.apk` 必须存在，APK 非空，大小和 SHA-256 与元数据一致。
- 新 `versionCode` 必须高于 `main/version.json` 顶层与所有渠道中的最大值；首次发布允许没有清单。比较跨渠道进行，避免先装 dev 的用户无法升级到 stable。
- 目标标签或同名 Release（包括草稿）已存在时停止，不覆盖、不删除。

每个 Release 附上 APK 和 `meta.json`，保留 `versionName`、`versionCode`、`channel`、`apkName`、`size`、`sha256`、`changelog`、`force`、`minSupportedVersionCode`、`commit`、`publishedAt`，并写入对应 GitHub Release 下载地址 `apkUrl`。stable 是正式 Release，dev 标记为 prerelease 且不成为 GitHub 的 Latest。

上传完资产后才公开草稿，然后更新 `main/version.json`：顶层等于最近发布的版本，`channels.stable` 与 `channels.dev` 分别保存各自最新版本。另一渠道的数据不变。旧版客户端和下载站可继续使用这个字段格式。顶层旧协议会跟随 dev，选择 stable 的消费者必须读取 `channels.stable`。

## 导入自建分发中心

只导入已经完整发布的 stable。在能通过 SSH 连接 `de` 的终端，进入私有源仓库 `LiamCart-dev/honghong` 根目录，取得发布授权后执行（把版本替换为实际标签）：

```bash
python3 backend/android-builder/import-release \
  --repository LiamCart-dev/honghong-releases --tag vX.Y.Z
```

分发中心原样保存全部资产，因此 APK 和 `meta.json` 必须同时存在。新客户端读取 `https://releases.hczhw.com/api/apps/honghong/latest.json`，下载其中的 `meta.json` 并要求 `meta.versionName == latest.version`、`channel == stable`，再用 `meta.apkName` 匹配资产 URL。`versionCode`、SHA-256、强制更新和最低支持版本来自这份元数据。导入后应核对 latest 的版本、两个资产的可访问性，以及 meta 的版本与渠道；dev 不进入这个 stable 入口。

发布工作流不连接分发服务器，导入是独立的人工操作。

## 失败处理与兼容边界

发布串行执行。GitHub Actions 的并发组最多保留一个运行中任务和一个待运行任务；密集推送可能取消较早的待运行任务，应等待前一版完成后再发下一版。新版本的代码值若低于已发布清单，会被拒绝。

失败后先检查目标标签、Release 草稿 / 公开状态、两个资产与 `main/version.json`。资产上传可能留下草稿；Release 已公开后也可能因 `main` 分支保护或并发修改而未更新清单。这些情况不自动重试、不自动删除或重新创建 Release。若 Release 已完整公开但清单未更新，应比对资产里的 meta 与最新 main，在明确确认后仅补齐清单；若产物错误，使用更高 `versionCode` 的新版本修复。不要 Re-run 已开始发布的旧版本来覆盖同名资产。

模板兼容旧清单格式，但不能更改已安装客户端内写死的 GitHub 仓库地址。历史入口 `JiHe021499/honghong-releases` 与拟用的 `LiamCart-dev/honghong-releases` 均曾返回 404；新建后者不会让前者自动恢复。指向旧地址的已安装版本需要恢复原入口或手动安装同签名的新版本。旧下载站的同步源 `HH_SRC` 和浏览器 GitHub 备用地址也应在部署时改成实际公开仓库，否则仍会读取旧地址。

本地验证：Python 3.11+ 运行 `python3 -m unittest discover -s backend/releases-repository/tests`；发布工作流在 GitHub 的 Ubuntu runner 使用系统 Python 3。
