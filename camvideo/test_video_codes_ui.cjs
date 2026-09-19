const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function setup(){
  const nodes=new Map(),calls=[];
  function node(id){if(!nodes.has(id))nodes.set(id,{style:{},value:'',checked:false,before(){},addEventListener(){},focus(){}});return nodes.get(id);}
  const state={videoCodesVersion:1,videoCodesOnlineVersion:1,videos:[{name:'a.mov',videoCode:'VC1-a'},{name:'b.mov',videoCode:'VC1-b'}]};
  const context={document:{createElement:()=>node(Symbol()),querySelector:node},$:node,localStorage:{getItem:()=>'',setItem(){}},render(){},app:{video:'a.mov',state},toast(){},call:async(...args)=>calls.push(args),refresh:async()=>{}};
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'web/video-codes.js'),'utf8'),context);
  context.render(state);return {context,state,node,calls};
}
test('online download requires no shared folder',async()=>{
  const ui=setup();ui.node('asset-online-code').value='VC2.example.hash';
  await ui.node('asset-online-import').onclick();
  assert.equal(ui.calls[0][0],'video_code_online_import');
  assert.equal(ui.calls[0][1].code,'VC2.example.hash');
  assert.equal(ui.calls[0][1].folder,undefined);
});
test('publication requires consent and resets when selected video changes',async()=>{
  const ui=setup();assert.equal(ui.node('asset-github-publish').disabled,true);
  ui.node('asset-confirm-public').checked=true;ui.node('asset-confirm-public').onchange();
  assert.equal(ui.node('asset-github-publish').disabled,false);
  ui.context.app.video='b.mov';
  await ui.node('asset-github-publish').onclick();
  assert.equal(ui.calls.length,0);assert.equal(ui.node('asset-confirm-public').checked,false);
});
test('old backend and active jobs block online actions',()=>{
  const ui=setup();ui.context.render({...ui.state,videoCodesOnlineVersion:undefined});
  assert.equal(ui.node('asset-online-import').disabled,true);
  ui.context.render({...ui.state,busy:true});assert.equal(ui.node('asset-online-import').disabled,true);
});
