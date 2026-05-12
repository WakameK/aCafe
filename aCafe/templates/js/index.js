document.addEventListener("DOMContentLoaded", () => {
    // すでに入店済みなら演出スキップ
    if (document.cookie.includes("entered=true")) {
        document.getElementById("intro-screen").style.display = "none";
        return;
    }

    const staticUrl = window.STATIC_URL || "/static/";
    const introImage = document.getElementById("intro-image");
    const introScreen = document.getElementById("intro-screen");
    const step1 = staticUrl + "images/step1.jpg";
    const step2 = staticUrl + "images/step2.jpg";

    // 先読みしてスムーズに切り替える
    [step1, step2].forEach(src => {
        const img = new Image();
        img.src = src;
    });

    introImage.src = step1;
    introImage.style.opacity = 1;
    introImage.style.transition = "opacity 0.8s ease";

    const changeImage = (newSrc) => {
        introImage.style.opacity = 0;
        setTimeout(() => {
            introImage.src = newSrc;
            introImage.style.opacity = 1;
        }, 800);
    };

    // 2秒後に step2 に切り替え
    setTimeout(() => {
        changeImage(step2);
    }, 2000);

    // さらに2秒後にフェードアウトしてイントロを閉じる
    setTimeout(() => {
        introScreen.style.transition = "opacity 1.5s ease";
        introScreen.style.opacity = 0;

        setTimeout(() => {
            introScreen.style.display = "none";
            document.cookie = "entered=true; max-age=31536000; path=/"; // 1年
        }, 1500);
    }, 4200);

    console.log("入店演出を開始");
});
