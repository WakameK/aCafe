// ヘッダーとトップ画像のクリック範囲、両方でこのリストを使う。
// ページを増やしたらここに1行足すだけでOK。
export type NavLink = {
  href: string;
  label: string;
  // トップ画像上のクリック範囲（画像に対する % 指定）。
  // 画像に置かない（ヘッダーだけの）リンクは spot を省略する。
  spot?: { x: number; y: number; w: number; h: number };
};

export const navLinks: NavLink[] = [
  { href: "/counter", label: "カウンター", spot: { x: 38, y: 42, w: 24, h: 26 } },
  { href: "/hakoniwa", label: "箱庭", spot: { x: 8, y: 55, w: 18, h: 22 } },
  { href: "/takibi", label: "焚火", spot: { x: 72, y: 52, w: 18, h: 24 } },
  { href: "/about", label: "このお店について" },
];
