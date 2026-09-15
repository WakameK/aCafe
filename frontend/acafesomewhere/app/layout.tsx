import "./globals.css";

export const metadata = {
  title: "くまの隠れ家",
  description: "静かな時間を過ごせる、くまの隠れ家。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
