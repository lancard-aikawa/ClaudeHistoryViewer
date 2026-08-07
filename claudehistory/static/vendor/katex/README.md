# KaTeX (vendored)

- Version: **0.18.1** (npm `katex@0.18.1`)
- Source: https://registry.npmjs.org/katex/-/katex-0.18.1.tgz (`package/dist/`)
- License: MIT — see [LICENSE](LICENSE)

## 同梱しているもの

| ファイル | 出所 |
|---|---|
| `katex.min.js` | `dist/katex.min.js` |
| `katex.min.css` | `dist/katex.min.css`（無改変） |
| `fonts/*.woff2` | `dist/fonts/*.woff2`（20 ファイル） |

`.ttf` / `.woff` は同梱していない。`katex.min.css` の `@font-face` は
`woff2 → woff → ttf` の順に列挙しているが、モダンブラウザは woff2 を選ぶため
残り 2 形式はリクエストされない。CSS を無改変で置いておくことで、
バージョン更新時は上記 3 種を上書きコピーするだけで済む。

## 更新手順

```sh
curl -sSL -o katex.tgz https://registry.npmjs.org/katex/-/katex-<VER>.tgz
tar xzf katex.tgz
cp package/dist/katex.min.js  package/dist/katex.min.css  <this dir>/
cp package/dist/fonts/*.woff2 <this dir>/fonts/
cp package/LICENSE            <this dir>/
```

配信は [`server.py`](../../../server.py) の `/vendor/...` ルート
（`_send_file`）が担当する。
