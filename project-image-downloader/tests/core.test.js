import test from 'node:test';
import assert from 'node:assert/strict';
import {safeName,imageURL,searchURL,newProject,normalizeRow,counts,nextFilename,sniffImage,enqueueSelected,parseCSV,keywordCSV,reports} from '../extension/core.js';
test('separate query/prefix/count survive CSV and escaped text',()=>{
  const rows=parseCSV('Search Keyword,Image Name,Qty\r\n"Sabalenka, US Open 2026",Sabalenka,5\r\n"Iga ""interview""",Iga,8');
  assert.equal(rows[0].query,'Sabalenka, US Open 2026');assert.equal(rows[0].prefix,'Sabalenka');assert.equal(rows[0].qty,5);
  const p=newProject('Tennis');p.rows=rows;
  const roundtrip=parseCSV(keywordCSV(p));assert.deepEqual(roundtrip.map(({id,...r})=>r),rows.map(({id,...r})=>r));
});
test('bulk import supports tabs, rejects bad rows atomically',()=>{
  assert.equal(parseCSV('Search Keyword\tImage Name\tQty\nSabalenka finals\tPlayer\t5')[0].prefix,'Player');
  for(const input of ['query,name,0','query,name,-1','query,name,1.5','query,,3','"unclosed,name,3','query,name,1001'])assert.throws(()=>parseCSV(input));
});
test('direct search URLs encode query without filename coupling',()=>{
  assert.equal(new URL(searchURL('A&B / tennis?','google')).searchParams.get('q'),'A&B / tennis?');
  const editorial=new URL(searchURL('Sabalenka US Open 2026','getty'));
  assert.equal(editorial.pathname,'/search/2/image');
  assert.equal(editorial.searchParams.get('family'),'editorial');
  assert.equal(editorial.searchParams.get('phrase'),'Sabalenka US Open 2026');
  assert.equal(editorial.searchParams.get('sort'),'mostpopular');
  assert.equal(new URL(searchURL('Iga & interview / 2026?','getty')).searchParams.get('phrase'),'Iga & interview / 2026?');
});
test('safe Windows names cannot escape folder or use reserved device names',()=>{
  assert.equal(safeName('../../CON:*?'),'.. .. CON');assert.equal(safeName('CON'),'_CON');
  assert.equal(safeName('NUL.jpg'),'_NUL.jpg');assert.equal(safeName('...'),'Untitled');
  assert.ok(!safeName('a/b\\c').includes('/'));
});
test('HTTP(S) public image URLs only; fragments dedupe, signed query stays intact',()=>{
  assert.equal(imageURL('https://img.example/photo?q=abc#x'),'https://img.example/photo?q=abc');
  for(const u of ['javascript:alert(1)','file:///a','data:image/png,x','http://127.0.0.1/x','http://10.2.3.4/a','https://user:secret@example.com/a','http://[::1]/x'])assert.equal(imageURL(u),null);
});
test('same sanitized filename keyword shares monotonic numbering across rows',()=>{
  const p=newProject('Tennis');const r1=normalizeRow({query:'match',prefix:'Player/A',qty:2}),r2=normalizeRow({query:'interview',prefix:'player:a',qty:2});
  assert.ok(nextFilename(p,r1,'jpg').endsWith('Player A 1.jpg'));
  assert.ok(nextFilename(p,r2,'png').endsWith('player a 2.png'));
  const restored=JSON.parse(JSON.stringify(p));assert.ok(nextFilename(restored,r1,'webp').endsWith('Player A 3.webp'));
});
test('sniff actual image bytes, never save HTML masquerading as JPEG',()=>{
  assert.equal(sniffImage(Uint8Array.from([255,216,255,224])).ext,'jpg');
  assert.equal(sniffImage(Uint8Array.from([137,80,78,71,13,10,26,10])).ext,'png');
  assert.throws(()=>sniffImage(new TextEncoder().encode('<html>Not an image</html>')));
});
test('queue caps per-row targets, dedupes URLs across project, blocks Getty previews',()=>{
  const p=newProject('News');p.rows=[normalizeRow({query:'a',prefix:'A',qty:2}),normalizeRow({query:'b',prefix:'B',qty:2})];
  p.candidates=[0,1,2].map(i=>({id:'a'+i,rowId:p.rows[0].id,url:'https://example.com/'+i,selected:true}));
  p.candidates.push({id:'b',rowId:p.rows[1].id,url:'https://example.com/0',selected:true},{id:'getty',rowId:p.rows[1].id,url:'https://media.gettyimages.com/a',selected:true,licenseRequired:true});
  assert.equal(enqueueSelected(p),2);assert.equal(enqueueSelected(p),0);assert.equal(counts(p).downloaded,0);assert.equal(counts(p).queued,2);
  p.jobs[0].status='complete';p.jobs[1].status='failed';assert.equal(counts(p).downloaded,1);assert.equal(counts(p).remaining,3);
});
test('reports preserve source attribution and report real shortages',()=>{
  const p=newProject('News');p.rows=[normalizeRow({query:'player interview',prefix:'Player',qty:5})];
  p.jobs=[{id:'1',rowId:p.rows[0].id,status:'complete',actualFilename:'/Downloads/Player 1.png',url:'https://example.com/a.png',sourcePage:'https://example.com/article',hash:'123'}];
  const {txt,csv}=reports(p);assert.match(txt,/Downloaded: 1 \/ 5/);assert.match(txt,/Still required: 4/);assert.match(csv,/https:\/\/example.com\/article/);
});
