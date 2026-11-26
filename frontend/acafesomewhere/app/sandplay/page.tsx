import CafeShell from "../../components/CafeShell";
import styles from "./page.module.css";

// Unityで作った sandtherapy(WebGLビルド)の場所。
// 既定は public/sandtherapy/index.html。別のURLに置く場合は NEXT_PUBLIC_SANDTHERAPY_URL で指定する。
const SANDTHERAPY_URL = process.env.NEXT_PUBLIC_SANDTHERAPY_URL ?? "/sandtherapy/index.html";

export default function SandplayPage() {
  return (
    <CafeShell title="箱庭" description="砂とミニチュアで、ことばにならない気持ちを置いてみる場所です。">
      <div className={styles.frameWrap}>
        <iframe
          src={SANDTHERAPY_URL}
          title="箱庭(sandtherapy)"
          className={styles.frame}
          allow="fullscreen"
          allowFullScreen
        />
      </div>
      <p className={styles.note}>
        表示されないときは <a href={SANDTHERAPY_URL}>こちらから直接開けます</a>。
      </p>
    </CafeShell>
  );
}
