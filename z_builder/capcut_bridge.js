'use strict';
const fs = require('fs');
const path = require('path');
const engine = require('./capcut-draft.js');
function main() {
  if (process.argv.length !== 4) throw Error('Usage: node capcut_bridge.js request.json result.json');
  const req = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const info = engine.detect();
  const drafts = req.drafts_root || info.draftsRoot;
  if (!drafts) throw Error('CapCut draft location not found. Set a custom drafts folder.');
  const plan = engine.makePlan(req.payload, req.media || {});
  if (!plan.images.length) throw Error('No video/image clips in resolved timeline');
  const result = engine.writeProject({plan, drafts, folderName: req.payload.name});
  const issues = engine.verifyProject(result.folder, plan);
  const output = { ...result, verify_issues: issues, notes: plan.notes,
    capcut: { ...info, compatibility: engine.compat(info) },
    launched: !!(req.launch && info.exe && engine.launch(info.exe)) };
  fs.writeFileSync(process.argv[3], JSON.stringify(output, null, 2));
  if (issues.length) process.exitCode = 2;
}
try {main()} catch(e) {console.error(e.stack || String(e));process.exitCode=1}
