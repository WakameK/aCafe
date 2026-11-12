import "./globals.css";
import SiteHeader from "@/components/SiteHeader";   // ← 追加
import SiteFooter from "@/components/SiteFooter";   // ← 追加

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <SiteHeader />   {/* ← 追加 */}
        {children}
        <SiteFooter />   {/* ← 追加 */}
      </body>
    </html>
  );
}