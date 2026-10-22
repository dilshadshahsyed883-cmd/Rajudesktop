/* Desktop SML: mirror every VPS tab but explicitly disable online-only controls.
 * The loopback FastAPI service ALSO denies these routes. This script is not
 * treated as a security boundary and cannot enable network access.
 */
(() => {
  "use strict";
  const onlineSelectors=[
    ".sml-remote-card", ".sml-batch-card",
    "#smlProxyOptions", "#smlProxyManager",
    "#submitImport", "#smlOpenProxyManager"
  ];
  const block=()=>{
    for(const el of document.querySelectorAll(onlineSelectors.join(","))){
      if(!el.dataset.offlineMarked){
        el.dataset.offlineMarked="1";
        el.classList.add("sml-online-blocked");
        el.title="Unavailable in offline-only desktop SML. Use Local Videos, Images or Folder import.";
      }
      for(const control of el.querySelectorAll("input, select, textarea, button")){
        control.disabled=true;
        control.title="Online import or proxy disabled in offline mode";
      }
      if(el.matches("button,input,select"))el.disabled=true;
    }
    const info=document.querySelector("#smlImportHelp");
    if(info)info.textContent="Offline desktop: YouTube/Drive/proxy imports cannot run. Use local Video, Image or Folder upload.";
  };
  document.addEventListener("DOMContentLoaded",block);
  window.addEventListener("load",block);
  // Existing UI scripts can reconstruct panels; keep network-only controls disabled.
  new MutationObserver(()=>block()).observe(document.documentElement,{childList:true,subtree:true});
})();