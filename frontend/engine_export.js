(() => {
  const manifestLink = document.getElementById("manifestLink");
  const godotLink = document.getElementById("godotLink");
  const unityLink = document.getElementById("unityLink");
  if (!manifestLink || !godotLink || !unityLink) return;

  function hide(link) {
    link.classList.add("hidden");
    link.removeAttribute("href");
  }

  function sync() {
    const href = manifestLink.getAttribute("href") || "";
    const match = href.match(/\/workspace\/([0-9a-f]{12})\/scene\.json/);
    if (!match) {
      hide(godotLink);
      hide(unityLink);
      return;
    }

    const sceneId = match[1];
    godotLink.href = `/api/v1/scenes/${sceneId}/export/godot.zip`;
    unityLink.href = `/api/v1/scenes/${sceneId}/export/unity.zip`;
    godotLink.classList.remove("hidden");
    unityLink.classList.remove("hidden");
  }

  function loadExtension(src) {
    if (document.querySelector(`script[data-game-creater-extension="${src}"]`)) return;
    const script = document.createElement("script");
    script.src = src;
    script.dataset.gameCreaterExtension = src;
    document.body.appendChild(script);
  }

  new MutationObserver(sync).observe(manifestLink, {
    attributes: true,
    attributeFilter: ["href", "class"],
  });
  sync();

  loadExtension("/workflow.js");
  loadExtension("/completion.js");
  loadExtension("/asset_library.js");
  loadExtension("/asset_workflow.js");
  loadExtension("/store.js");
})();
