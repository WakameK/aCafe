"use client";

import { useCallback, useEffect } from "react";
import { Unity, useUnityContext } from "react-unity-webgl";

type Props = {
  // 「この作品を見てもらう」が押されたときに、作品データを受け取る
  onSubmit: (payload: unknown) => void;
  // 前回の作品(あれば、読み込み完了後に Unity へ渡す)
  initialWork?: unknown;
};

export default function SandplayEmbed({ onSubmit, initialWork }: Props) {
  const {
    unityProvider,
    isLoaded,
    loadingProgression,
    sendMessage,
    addEventListener,
    removeEventListener,
  } = useUnityContext({
    loaderUrl: "/unity/sandplay/Build/sandplay.loader.js",
    dataUrl: "/unity/sandplay/Build/sandplay.data",
    frameworkUrl: "/unity/sandplay/Build/sandplay.framework.js",
    codeUrl: "/unity/sandplay/Build/sandplay.wasm",
  });

  const handleSubmit = useCallback(
    (json: unknown) => onSubmit(JSON.parse(String(json))),
    [onSubmit]
  );

  // Unity の「この作品を見てもらう」ボタンから届くイベント
  useEffect(() => {
    addEventListener("SubmitSandplay", handleSubmit);
    return () => removeEventListener("SubmitSandplay", handleSubmit);
  }, [addEventListener, removeEventListener, handleSubmit]);

  // 読み込みが終わったら、前回の作品を Unity に渡す
  useEffect(() => {
    if (isLoaded && initialWork) {
      sendMessage("Manager", "LoadFromJson", JSON.stringify(initialWork));
    }
  }, [isLoaded, initialWork, sendMessage]);

  return (
    <div style={{ width: "100%", maxWidth: 1100 }}>
      {!isLoaded && <p>読み込み中… {Math.round(loadingProgression * 100)}%</p>}
      <Unity
        unityProvider={unityProvider}
        style={{ width: "100%", aspectRatio: "16 / 9" }}
      />
    </div>
  );
}