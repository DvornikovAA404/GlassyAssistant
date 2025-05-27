function saveCurrentUrl() {
    chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === "complete" && tab.active) {
        let currentUrl = tab.url;
        console.log("📤 Обновлённый URL:", currentUrl);

        if (!currentUrl.startsWith("about:")) {  // 👈 Игнорируем системные страницы
            fetch("http://localhost:5000/save_url", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: currentUrl })
            })
            .then(response => response.text())
            .then(data => console.log("✅ Ответ сервера:", data))
            .catch(error => console.error("❌ Ошибка HTTP-запроса:", error));
        }
    }
});

}

setInterval(saveCurrentUrl, 2000);
