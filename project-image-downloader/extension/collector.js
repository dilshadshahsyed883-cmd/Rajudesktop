// Runs only when the user presses Collect on the active page. No clicks, typing or scrolling.
function collectPageImages() {
  const host=location.hostname;
  const getty=/(^|\.)gettyimages\.[a-z.]+$/i.test(host);
  const google=/(^|\.)google\.[a-z.]+$/i.test(host);
  const source=getty?'getty':google?'google':'page';
  const out=new Map();
  function add(raw, el, original=false, page='') {
    if(!raw) return;
    try {
      const u=new URL(raw,location.href);
      if(!['http:','https:'].includes(u.protocol)) return;
      if(/gstatic\.com|googleusercontent\.com/.test(u.hostname) && /encrypted-tbn|favicon/.test(u.href)) original=false;
      const im=el?.tagName==='IMG'?el:el?.querySelector?.('img');
      const dimensionsKnown=im && (!original || im.currentSrc===u.href || im.src===u.href);
      const width=Number(el?.getAttribute?.('data-ow') || (original && el?.getAttribute?.('data-width')) || (dimensionsKnown && im?.naturalWidth) || 0);
      const height=Number(el?.getAttribute?.('data-oh') || (original && el?.getAttribute?.('data-height')) || (dimensionsKnown && im?.naturalHeight) || 0);
      if(!original && width && height && (width<100 || height<75)) return;
      const sourcePage=page || el?.closest?.('a')?.href || location.href;
      const title=(im?.alt || el?.getAttribute?.('aria-label') || document.title || '').slice(0,300);
      const candidate={url:u.href,preview:im?.currentSrc || im?.src || u.href,width,height,title,original,source,sourcePage,licenseRequired:getty || /(^|\.)gettyimages\.|(^|\.)gettyimages\.[a-z.]+|(^|\.)istockphoto\.com/.test(u.hostname)};
      if(!out.has(u.href) || original) out.set(u.href,candidate);
    }catch{}
  }
  // Google legacy and current preview links; source URL and image URL are independent.
  for(const a of document.querySelectorAll('a[href]')) {
    try {
      const u=new URL(a.href,location.href);
      const original=u.searchParams.get('imgurl') || u.searchParams.get('mediaurl');
      if(original) add(original,a,true,u.searchParams.get('imgrefurl') || '');
      else if(/\.(jpe?g|png|webp|gif|avif)(?:$|[?#])/i.test(a.href)) add(a.href,a,true);
    }catch{}
  }
  for(const el of document.querySelectorAll('[data-ou], [data-original], [data-original-src], [data-iurl]')) {
    add(el.getAttribute('data-ou')||el.getAttribute('data-original')||el.getAttribute('data-original-src')||el.getAttribute('data-iurl'),el,true,el.getAttribute('data-ru')||'');
  }
  // Structured metadata is parsed as JSON, never evaluated as JavaScript.
  for(const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    if(script.textContent.length>2000000) continue;
    try {
      const walk=(obj,depth=0)=>{
        if(!obj||typeof obj!=='object'||depth>15) return;
        if(obj['@type']==='ImageObject') add(obj.contentUrl || obj.url,null,true,obj.mainEntityOfPage?.['@id'] || location.href);
        for(const v of Object.values(obj)) if(typeof v==='object') walk(v,depth+1);
      }; walk(JSON.parse(script.textContent));
    }catch{}
  }
  for(const img of document.images) {
    const src=img.currentSrc || img.getAttribute('data-src') || img.src;
    const original=!getty && (!google || !/encrypted-tbn|gstatic\.com|googleusercontent\.com/.test(src || ''));
    add(src,img,original);
  }
  return {page:location.href,title:document.title,source,items:[...out.values()].slice(0,600)};
}
