# sandtherapy (Unity WebGL)

Unityで作った箱庭(sandtherapy)のWebGLビルドをここに置く。`/sandplay` ページがこの `index.html` を埋め込んで表示する。

1. Unity で WebGL ビルドする(Build Settings → WebGL)。
2. 出力した中身(`index.html`, `Build/`, `TemplateData/`)を、このフォルダ直下に置く。
   → `public/sandtherapy/index.html` になる。
3. 圧縮(Brotli/Gzip)を有効にしたビルドは、配信側で `Content-Encoding` ヘッダーが必要になる。
   Next.js の開発サーバーでは付かないので、Unityの Player Settings → Publishing Settings で
   Compression Format を `Disabled` にするのが手軽。

別のURLに置く場合は、環境変数 `NEXT_PUBLIC_SANDTHERAPY_URL` にそのURLを指定する。
