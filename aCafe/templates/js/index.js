document.addEventListener("DOMContentLoaded", () => {
    // すでに入店済みなら演出スキップ
    if (document.cookie.includes("entered=true")) {
        document.getElementById("intro-screen").style.display = "none";
        return;
    }

    const introImage = document.getElementById("intro-image");
    const introScreen = document.getElementById("intro-screen");

    // 画像1 → 画像2 に切り替え
    setTimeout(() => {
        introImage.src = "/static/images/step2.jpg";
    }, 2000); // 2秒後に切り替え

    // フェードアウト
    setTimeout(() => {
        introScreen.style.transition = "opacity 1.5s";
        introScreen.style.opacity = 0;

        // 完全に消えたら非表示
        setTimeout(() => {
            introScreen.style.display = "none";
            document.cookie = "entered=true; max-age=31536000"; // 1年
        }, 1500);
    }, 4000); // 4秒後にフェードアウト開始

    console.log("入店演出を開始");
});
