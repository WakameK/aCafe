document.getElementById("loginForm").addEventListener("submit", function(e) {
    e.preventDefault();

    const formData = new FormData(this);

    fetch("/login/", {
        method: "POST",
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === "ok") {
            // ログイン成功 → チャットページへ
            window.location.href = "/chat/";
        } else {
            document.getElementById("error").innerText = data.error;
        }
    });
});