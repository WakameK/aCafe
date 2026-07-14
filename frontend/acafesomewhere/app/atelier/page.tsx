import Image from "next/image";
import CafeShell from "../../components/CafeShell";
import styles from "./page.module.css";

const artworks = [
  "/image/atelier-sample-1.jpg",
  "/image/atelier-sample-2.jpg",
  "/image/atelier-sample-3.jpg",
];

export default function AtelierPage() {
  return (
    <CafeShell
      title="女性のアトリエ"
      description='「女性」が作ったモノが無造作に置かれている。'
    >
      <p>『持って帰るもぶっ壊すもご自由にどうぞ！それもうアタシのじゃないから！』</p>
      <div className={styles.actions}>
        <a href="#">持って帰る</a>
        <a href="#">ぶっ壊してみる</a>
      </div>

      <h3 className={styles.heading}>作品たち</h3>
      <ul className={styles.atelierImages}>
        {artworks.map((src, index) => (
          <li key={src}>
            <Image src={src} alt={`作品画像 ${index + 1}`} width={200} height={200} />
          </li>
        ))}
      </ul>
    </CafeShell>
  );
}
