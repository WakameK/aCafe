"use client";

import { Unity, useUnityContext } from "react-unity-webgl";

export default function UnityRoom() {
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