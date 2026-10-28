import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
const code=await readFile(new URL('../extension/collector.js',import.meta.url),'utf8');
function img(src,w=1600,h=900,alt='Photo') {return {tagName:'IMG',src,currentSrc:src,naturalWidth:w,naturalHeight:h,alt,getAttribute:()=>null,closest:()=>null};}
function anchor(href,image) {return {tagName:'A',href,getAttribute:()=>null,querySelector:s=>s==='img'?image:null,closest(){return this;}};}
function collect({url,images=[],links=[],attributes=[],scripts=[]}) {
  const context=vm.createContext({URL,location:new URL(url),document:{title:'Search page',images,querySelectorAll:s=>s==='a[href]'?links:s.startsWith('[data-ou]')?attributes:s.startsWith('script[')?scripts:[]}});
  return vm.runInContext(code+'\ncollectPageImages();',context);
}
test('Google result imgurl preserves full original and independent source URL',()=>{
  const thumb=img('https://encrypted-tbn0.gstatic.com/images?q=abc',250,140);
  const a=anchor('https://www.google.com/imgres?imgurl='+encodeURIComponent('https://photos.example/full.jpg')+'&imgrefurl='+encodeURIComponent('https://publisher.example/story'),thumb);
  const data=collect({url:'https://www.google.com/search?tbm=isch&q=tennis',links:[a],images:[thumb]});
  const original=data.items.find(c=>c.url==='https://photos.example/full.jpg');
  assert.equal(data.source,'google');assert.equal(original.original,true);assert.equal(original.sourcePage,'https://publisher.example/story');
  assert.equal(original.width,0,'thumbnail dimensions must not masquerade as original dimensions');
  assert.equal(data.items.find(c=>c.url.includes('encrypted-tbn')).original,false);
});
test('Google external preview image becomes an original with actual dimensions',()=>{
  const preview=img('https://photos.example/preview-original.webp',2000,1200,'Tennis match');
  const data=collect({url:'https://www.google.com/search?tbm=isch&q=tennis',images:[preview]});
  assert.equal(data.items[0].original,true);assert.equal(data.items[0].width,2000);assert.equal(data.items[0].height,1200);
});
test('Getty images remain license-required previews; no page actions are invoked',()=>{
  const preview=img('https://media.gettyimages.com/id/123/photo.jpg');
  const data=collect({url:'https://www.gettyimages.com/photos/tennis',images:[preview]});
  assert.equal(data.source,'getty');assert.equal(data.items[0].licenseRequired,true);assert.equal(data.items[0].original,false);
});
test('JSON-LD and page images dedupe exact URLs and ignore non-HTTP content',()=>{
  const url='https://photos.example/original.png';
  const scripts=[{textContent:JSON.stringify({'@graph':[{'@type':'ImageObject',contentUrl:url,mainEntityOfPage:{'@id':'https://publisher.example/article'}}]})}];
  const data=collect({url:'https://publisher.example/article',images:[img(url),img('data:image/png;base64,abcd')],scripts});
  assert.equal(data.items.length,1);assert.equal(data.items[0].url,url);assert.equal(data.items[0].sourcePage,'https://publisher.example/article');
});
