const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function setup(call) {
  const nodes = new Map(), listeners = {};
  const node = key => {
    if (!nodes.has(key)) nodes.set(key, {value:'', disabled:false, style:{}, textContent:'', prepend(){}, after(){}, append(){}, setAttribute(){}, focus(){this.focused=true;}});
    return nodes.get(key);
  };
  const context = {document:{querySelector:node,getElementById:node,createElement:()=>node(Symbol()),head:node('head')},window:{addEventListener:(name,fn)=>listeners[name]=fn},localStorage:{getItem:()=>'',setItem(){}},render(){},call,refresh:async()=>{},act(){},toast(){},esc:String,duration:String};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'web/automation.js'),'utf8'),context);
  node('automation-mode').value='auto'; node('automation-repeat').value='once'; node('automation-scope').value='all';
  const state = {busy:false,automationVersion:5,sharedCameraVersion:1,phones:[]};
  context.render(state);
  return {node,context,state,listeners,feedback:()=>[...nodes.values()].find(n=>n.id==='automation-start-feedback')};
}
test('full Unicode task submitted once with immediate pending feedback',async()=>{
  let resolve, requests=[];
  const ui=setup((...args)=>{requests.push(args);return new Promise(r=>resolve=r)});
  ui.node('automation-task').value='Lavar Louça na Pia';
  const pending=ui.node('sync').onclick();
  assert.equal(ui.node('sync').disabled,true);
  await ui.node('sync').onclick();
  assert.equal(requests.length,1);
  assert.equal(requests[0][1].taskName,'Lavar Louça na Pia');
  assert.match(ui.feedback().textContent,/Enviando/);
  resolve(); await pending;
  assert.equal(ui.node('sync').disabled,false);
});
test('missing task and request errors appear beside the button',async()=>{
  const ui=setup(async()=>{throw Error('RAM insuficiente')});
  await ui.node('sync').onclick();
  assert.match(ui.feedback().textContent,/nome completo/);
  ui.node('automation-task').value='Lavar Louça na Pia';
  await ui.node('sync').onclick();
  assert.equal(ui.feedback().textContent,'RAM insuficiente');
});
test('disconnect blocks stale start; successful state restores it and shows job errors',()=>{
  const ui=setup(async()=>{});
  ui.listeners['panel-connection']({detail:{connected:false,message:'Sem conexão'}});
  assert.equal(ui.node('sync').disabled,true);
  assert.equal(ui.feedback().textContent,'Sem conexão');
  ui.context.render({...ui.state,operation:'sync',message:'Executável não encontrado'});
  assert.equal(ui.node('sync').disabled,false);
  assert.equal(ui.feedback().textContent,'Executável não encontrado');
  ui.context.render({...ui.state,busy:true,operation:'install',message:'Enviando vídeo'});
  assert.equal(ui.node('sync').disabled,true);
  assert.equal(ui.feedback().textContent,'Enviando vídeo');
});
