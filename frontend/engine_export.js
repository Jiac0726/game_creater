(() => {
  const manifestLink = document.getElementById("manifestLink");
  const godotLink = document.getElementById("godotLink");
  if (!manifestLink || !godotLink) return;

  function sync() {
    const href = manifestLink.getAttribute("href") || "";
    const match = href.match(/\/workspace\/([0-9a-f]{12})\/scene\.json/);
    if (!match) {
      godotLink.classList.add("hidden");
      godotLink.removeAttribute("href");
      return;
    }
    const sceneId = match[1];
    godotLink.href = `/api/v1/scenes/${sceneId}/export/godot.zip`;
    godotLink.classList.remove("hidden");
  }

  new MutationObserver(sync).observe(manifestLink, {
    attributes: true,
    attributeFilter: ["href", "class"],
  });
  sync();
})();
