# KazuraDB

[English README](README.md)

KazuraDB は、AI エージェント向けの小さなリレーションシップ・グラフ DB のプロトタイプです。人や概念などの知識を「ノード」、それらの関係を有向「エッジ」として SQLite に保存し、CLI（`kazura`）またはオプションの MCP サーバーから JSON で操作できます。

名前は蔓草の「葛（かずら）」に由来します。蔓が絡まり広がっていくように、関係が増殖していく様子をそのまま保存する DB、というイメージです。

本格的なグラフ DB サーバーを運用せず、ローカルで検査・バックアップしやすい知識グラフを扱うことを目的としています。

## 主な機能

- 人間にも読みやすいキー（例: `person:alice`）でノードを管理
- `source -> type -> target` 形式の有向エッジを保存
- 同じ始点・種類・終点を持つ複数のエッジを許容
- ノードとエッジに任意の JSON プロパティを付与
- 始点・終点・関係種別によるエッジ検索
- 方向、深さ、関係種別を指定した近傍グラフの取得
- 幅優先探索による最短有向パスの検索
- YAML プロファイルによるノード種別・エッジ形状の検証
- CLI と MCP サーバーで同じ基本操作を提供

## 必要環境とインストール

- Python 3.10 以上
- SQLite（Python 標準ライブラリの `sqlite3` を使用）

開発用にリポジトリを editable install します。

```console
python -m pip install -e .
```

MCP サーバーも使用する場合は、追加依存関係を含めてインストールします。

```console
python -m pip install -e ".[mcp]"
```

インストールすると、`kazura` と `kazura-mcp` の 2 コマンドが利用可能になります。

## クイックスタート

次の例では `graph.db` に 2 つのノードと、その間の関係を保存します。すべてのコマンドは JSON を標準出力へ出力します。エラーも `"error"` キーを持つ JSON として出力され、終了コードは 1 になります。

```console
kazura --db graph.db add-node agent:alice --label Alice --kind agent --props '{"role":"planner"}'
kazura --db graph.db add-node concept:graph-db --label "Graph DB" --kind concept
kazura --db graph.db add-edge agent:alice uses concept:graph-db --props '{"confidence":0.9}'
kazura --db graph.db find-edges --source agent:alice
```

`--db` を省略すると、カレントディレクトリの `graph.db` が使われます。指定した DB ファイルが存在しない場合、スキーマとファイルは自動的に作成されます。

### 近傍を調べる

`agent:alice` から入出力の両方向へ最大 2 ホップ探索します。

```console
kazura --db graph.db neighbors agent:alice --direction both --depth 2
```

`--direction` には `out`、`in`、`both` を指定できます。`--type uses` のように指定すると、対象の関係種別だけを探索します。

### 最短パスを調べる

始点から終点への有向エッジをたどり、最大 4 ホップ以内の最短パスを探します。

```console
kazura --db graph.db path agent:alice concept:graph-db --max-depth 4
```

見つからない場合は `found: false`、空の `nodes` と `edges`、`length: null` が返ります。

## CLI リファレンス

グローバルオプション `--db PATH` は、サブコマンドより前に指定してください。

| コマンド | 用途 | 主なオプション |
| --- | --- | --- |
| `add-node KEY` | ノードの作成または更新 | `--label`、`--kind`、`--props` |
| `add-edge SOURCE TYPE TARGET` | 有向エッジの作成 | `--props`、`--no-create-missing` |
| `find-edges` | エッジの絞り込み検索 | `--source`、`--target`、`--type`、`--limit` |
| `neighbors KEY` | 近傍サブグラフの取得 | `--direction`、`--depth`、`--type`、`--limit` |
| `path SOURCE TARGET` | 最短有向パスの検索 | `--max-depth`、`--type` |
| `get-node KEY` | ノード単体の取得 | なし |
| `delete-node KEY` | ノードと接続エッジの削除 | なし |
| `delete-edge EDGE_ID` | エッジの削除 | なし |
| `profile-info PROFILE` | YAML プロファイルの内容を JSON 表示 | なし |
| `validate-edge PROFILE SOURCE_KIND TYPE TARGET_KIND` | エッジ形状の検証 | なし |

詳細は `kazura --help` または `kazura <サブコマンド> --help` で確認できます。

### ノードの追加と更新

```console
kazura --db graph.db add-node person:alice --label Alice --kind person --props '{"team":"research"}'
```

- `key` は一意で、空文字列は使用できません。
- `--label` は省略可能です。
- `--kind` の既定値は `entity` です。
- `--props` は JSON オブジェクトでなければなりません。
- 同じキーを再度追加すると、既存ノードを更新します。プロパティはマージではなく置き換えです。ラベルを省略した場合だけ既存ラベルが維持されます。

### エッジの追加

```console
kazura --db graph.db add-edge person:alice works_on project:kazura --props '{"since":"2026-07"}'
```

既定では、始点または終点のノードが未登録でも `entity` ノードとして用意されます。未登録ノードをエラーにしたい場合は `--no-create-missing` を指定します。

```console
kazura --db graph.db add-edge person:alice works_on project:kazura --no-create-missing
```

同一の `source`、`type`、`target` を持つエッジも重複して保存できます。これにより、出典や信頼度、対象期間が異なる事実、相反する解釈を別々のエッジとして保持できます。

> [!CAUTION]
> 現在の実装では、自動ノード作成が有効な `add-edge` は既存の始点・終点にもノードの upsert を実行します。そのため、既存ノードの `kind` が `entity`、`props` が `{}` に更新されます。ノードのメタデータを維持したい場合は、両端のノードを先に作成し、`--no-create-missing` を指定してください。

## データモデル

中核となるテーブルは `nodes` と `edges` の 2 つです。

### ノード

ノードは次の情報を持ちます。

- `id`: SQLite 内部 ID
- `key`: 人やエージェントが参照する一意のキー
- `label`: 表示名（省略可）
- `kind`: 軽量な分類。既定値は `entity`
- `props`: 任意の JSON オブジェクト
- `created_at` / `updated_at`: DB 内部に保存されるタイムスタンプ

### エッジ

エッジは `source -> type -> target` の有向関係です。

- `id`: SQLite 内部 ID
- `source`: 始点ノードのキー
- `type`: `uses`、`depends_on` などの関係種別
- `target`: 終点ノードのキー
- `props`: 出典、信頼度、期間、抽出メモなどの任意情報
- `created_at` / `updated_at`: DB 内部に保存されるタイムスタンプ

関係種別は固定の列挙型ではなく文字列です。関係自体を知識として説明したい場合は、同じキーを持つ通常のノードを作成できます。

```console
kazura add-node relation:uses --kind relation_type --label uses
kazura add-node text:uses-definition --kind text --props '{"text":"source uses target"}'
kazura add-edge relation:uses description text:uses-definition --no-create-missing
```

## 宣言的プロファイル（実験的機能）

プロファイルは、汎用グラフの上に任意で重ねる YAML の検証ルールです。許可するノード種別と、`始点の kind + エッジ種別 + 終点の kind` の組み合わせを宣言できます。

```yaml
name: work_notes
description: 作品と制作者を扱う最小プロファイル

node_kinds:
  person:
    description: 人物
  work:
    description: 作品

edge_types:
  created:
    description: 人物が作品を制作した
    source_kinds: [person]
    target_kinds: [work]
    symmetric: false
```

内容の確認とエッジ形状の検証は次のように行います。

```console
kazura profile-info examples/work_notes/profile.yaml
kazura validate-edge examples/work_notes/profile.yaml person created work
```

検証に成功すると `valid: true` の JSON が出力されます。許可されていない kind、関係種別、始点・終点の組み合わせはエラーになります。

プロファイル利用時は、次の制約に注意してください。

- プロファイルはグラフの形を検証するだけで、事実の真偽は検証しません。
- `add-node` や `add-edge` に自動適用されません。保存前に `validate-edge` などで明示的に検証する必要があります。
- `symmetric: true` はメタデータとして読み込まれるだけです。逆向きエッジの自動作成や探索方向の変更は行いません。

完全なサンプルは [`examples/work_notes`](examples/work_notes) を参照してください。

## MCP サーバー

MCP 用の追加依存関係をインストールした後、環境変数 `KAZURA_DB` に DB パスを設定して起動します。省略時は `graph.db` が使われます。

PowerShell:

```powershell
$env:KAZURA_DB = "graph.db"
kazura-mcp
```

Bash:

```bash
export KAZURA_DB=graph.db
kazura-mcp
```

サーバーは次の MCP ツールを公開します。

- `add_node(key, label=None, kind="entity", props=None)`
- `add_edge(source, type_key, target, props=None, create_missing=True)`
- `find_edges(source=None, target=None, type_key=None, limit=100)`
- `neighbors(key, direction="both", depth=1, type_key=None, limit=100)`
- `path(source, target, max_depth=4, type_key=None)`
- `delete_node(key)`
- `delete_edge(edge_id)`

MCP サーバーは最初のツール呼び出し時に DB 接続を 1 つ作成し、CLI と同じ `GraphDB` 操作をエージェントへ公開します。プロファイル関連の操作は現在 MCP ツールとして公開されていません。

## Python から使う

`GraphDB` は Python API から直接利用することもできます。

```python
from kazura import GraphDB

db = GraphDB("graph.db")
try:
    db.add_node("person:alice", "Alice", kind="person")
    db.add_node("project:kazura", "kazura", kind="project")
    db.add_edge(
        "person:alice",
        "works_on",
        "project:kazura",
        {"role": "maintainer"},
        create_missing=False,
    )
    result = db.neighbors("person:alice", direction="out", depth=1)
    print(result)
finally:
    db.close()
```

一時的なインメモリ DB を使う場合は、パスを省略して `GraphDB()` を生成します。

## 現在の制約

- プロトタイプであり、認証、アクセス制御、ネットワーク API、マイグレーション機構はありません。
- CLI にはノードの一覧取得やエッジの更新コマンドがありません。
- DB にはタイムスタンプを保存しますが、現在の JSON 応答には含まれません。
- `path` は出力方向のエッジだけをたどります。
- `neighbors` と `find-edges` の `limit` は返すエッジ数に対する上限です。

## 開発

テストを実行します。

```console
python -m pytest
```

主な構成は次のとおりです。

```text
src/kazura/graphdb.py     SQLite スキーマとグラフ操作
src/kazura/cli.py         CLI
src/kazura/profile.py     YAML プロファイルの読み込みと検証
src/kazura/mcp_server.py  MCP サーバー
tests/                    自動テスト
examples/work_notes/      プロファイルのサンプル
docs/                     設計・構想資料
```

関連資料:

- [製品ビジョン](docs/VISION.md)
- [レイヤー型リレーションシップ DB 構想](docs/LAYERED_RELATIONSHIP_DB.md)
