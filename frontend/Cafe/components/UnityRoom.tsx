"use client";

import { useEffect } from "react";
import { Unity, useUnityContext } from "react-unity-webgl";

type Props = {
  roomSlug: string;
};

// Unity側は ws://.../ws/space/campfire/ に固定でつなぐ作りになっている。
// そこで、このページを開いている間だけブラウザの WebSocket を差し替えて
//   1. 接続先の部屋名を、いま開いている部屋(roomSlug)に書き換える
//   2. 作られたソケットを覚えておき、ページを離れるときに確実に閉じる
// を行う。2をしないと、Unityが終了したあとに届いたメッセージを
// 消えたUnityのメモリに書き込もうとして "memory access out of bounds" になり、
// サーバー側にも幽霊プレイヤーが残って人数が減らなくなる。
const SPACE_WS_PATH = /\/ws\/space\/[^/]+\/?/;

const NativeWebSocket = typeof window !== "undefined" ? window.WebSocket : undefined;

function installSpaceSocketPatch(roomSlug: string) {
  if (!NativeWebSocket) return () => {};

  const sockets = new Set<WebSocket>();

  const Patched = function (url: string | URL, protocols?: string | string[]) {
    const original = url.toString();
    const rewritten = SPACE_WS_PATH.test(original)
      ? original.replace(SPACE_WS_PATH, `/ws/space/${encodeURIComponent(roomSlug)}/`)
      : original;

    // protocols が空配列だと接続に失敗するブラウザがあるので、空なら渡さない
    const ws =
      protocols && (!Array.isArray(protocols) || protocols.length > 0)
        ? new NativeWebSocket(rewritten, protocols)
        : new NativeWebSocket(rewritten);

    sockets.add(ws);
    ws.addEventListener("close", () => sockets.delete(ws));
    return ws;
  } as unknown as typeof WebSocket;

  // WebSocket.OPEN などの定数や instanceof がそのまま使えるようにする
  Object.setPrototypeOf(Patched, NativeWebSocket);
  Patched.prototype = NativeWebSocket.prototype;

  window.WebSocket = Patched;

  return () => {
    window.WebSocket = NativeWebSocket;
    sockets.forEach((ws) => {
      // Unityへの通知を止めてから閉じる(終了済みのUnityを呼ばないように)
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      if (ws.readyState === NativeWebSocket.CONNECTING || ws.readyState === NativeWebSocket.OPEN) {
        ws.close(1000, "leave room");
      }
    });
    sockets.clear();
  };
}

export default function UnityRoom({ roomSlug }: Props) {
  // Unityが接続する前に差し替えておく必要があるので、読み込み開始と同時に入れる
  useEffect(() => installSpaceSocketPatch(roomSlug), [roomSlug]);

  const { unityProvider, isLoaded, loadingProgression } = useUnityContext({
    loaderUrl: "/unity-room/Build/WebBuild.loader.js",
    dataUrl: "/unity-room/Build/WebBuild.data",
    frameworkUrl: "/unity-room/Build/WebBuild.framework.js",
    codeUrl: "/unity-room/Build/WebBuild.wasm",
  });

  return (
    <div style={{ position: "relative", width: "100%", maxWidth: 960, aspectRatio: "16 / 9" }}>
      {!isLoaded && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          読み込み中… {Math.round(loadingProgression * 100)}%
        </div>
      )}
      <Unity
        unityProvider={unityProvider}
        style={{ width: "100%", height: "100%", visibility: isLoaded ? "visible" : "hidden" }}
      />
    </div>
  );
}
