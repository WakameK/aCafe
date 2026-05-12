document.addEventListener("DOMContentLoaded", function() {
    const downloadBtn = document.getElementById("download-chat-log-btn");
    const statusMsg = document.getElementById("download-status");

    if (downloadBtn) {
        downloadBtn.addEventListener("click", function() {
            downloadChatLog();
        });
    }
});

function downloadChatLog() {
    const statusMsg = document.getElementById("download-status");
    statusMsg.style.display = "block";
    statusMsg.textContent = "ダウンロード中...";
    statusMsg.style.color = "blue";

    fetch("/export-chat-log/")
        .then(response => {
            if (!response.ok) {
                throw new Error("ダウンロードに失敗しました: " + response.statusText);
            }
            return response.json();
        })
        .then(data => {
            // JSON ファイルをダウンロード
            const jsonString = JSON.stringify(data, null, 2);
            const blob = new Blob([jsonString], { type: "application/json;charset=utf-8" });
            const link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.download = `chat_log_${new Date().toISOString().split("T")[0]}.json`;
            link.click();

            statusMsg.textContent = "✓ ダウンロード完了";
            statusMsg.style.color = "green";
            setTimeout(() => {
                statusMsg.style.display = "none";
            }, 3000);
        })
        .catch(error => {
            console.error("エラー:", error);
            statusMsg.textContent = "✗ エラー: " + error.message;
            statusMsg.style.color = "red";
        });
}


function updateNickname() {
    const nicknameInput = document.getElementById("nickname");
    const newNickname = nicknameInput.value.trim();
}
