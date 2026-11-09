const STORE_KEY = 'twil.conversations.v1';
let chats = [];
let currentId = null;
let controller = null;
let busy = false;
let online = false;
let storageError = '';

function currentChat(){return chats.find(chat=>chat.id===currentId);}
function saveChats(){
 try{localStorage.setItem(STORE_KEY,JSON.stringify({version:1,currentId,chats}));storageError='';}
 catch{storageError='Browser storage is full or unavailable. Export this chat to keep a copy.';}
 if(storageError)$('metrics').textContent=storageError;
}
function restoreChats(){
 try{
  const saved=JSON.parse(localStorage.getItem(STORE_KEY)||'null');
  if(saved?.version===1&&Array.isArray(saved.chats)){
   chats=saved.chats.filter(chat=>typeof chat.id==='string'&&typeof chat.title==='string'&&Array.isArray(chat.messages)&&Array.isArray(chat.contextMessages)&&typeof chat.summary==='string');
   currentId=saved.currentId;
  }
 }catch{storageError='Saved chat data could not be read. Export any important conversations.';}
 if(!currentChat())currentId=chats[0]?.id;
 if(!currentChat())createChat();else showChat();
}
function scrollChat(){const el=$('conversation');el.scrollTop=el.scrollHeight;}
function message(role,text){
 const el=document.createElement('article');el.className='message '+role;
 const label=document.createElement('div');label.className='label';label.textContent=role==='user'?'You':'TwIL';
 const content=document.createElement('div');content.className=role==='assistant'?'content prose':'content';
 if(role==='assistant')renderAnswer(content,text);else content.textContent=text;
 el.append(label,content);$('messages').append(el);scrollChat();return {el,content};
}
function addCopy(answer,text){
 const button=document.createElement('button');button.className='copy';button.textContent='Copy response';
 button.onclick=async()=>{try{await navigator.clipboard.writeText(text);button.textContent='Copied';setTimeout(()=>button.textContent='Copy response',1500);}catch{button.textContent='Select the text to copy';}};
 answer.el.append(button);
}
function updateMemory(){
 const chat=currentChat();$('memoryInfo').classList.toggle('empty',!chat.summary);
 $('memoryText').textContent=chat.summary;
 $('memoryLabel').textContent='Earlier turns summarized · full transcript kept below';
}
function drawChatList(){
 $('chatList').replaceChildren();$('chatPicker').replaceChildren();
 for(const chat of chats){
  const row=document.createElement('div');row.className='chat-row'+(chat.id===currentId?' active':'');
  const title=document.createElement('button');title.className='chat-title';title.textContent=chat.title;title.title=chat.title;title.disabled=busy;title.onclick=()=>switchChat(chat.id);
  const rename=document.createElement('button');rename.className='chat-action';rename.textContent='✎';rename.setAttribute('aria-label','Rename '+chat.title);rename.disabled=busy;
  rename.onclick=()=>{const name=window.prompt('Conversation title',chat.title);if(name?.trim()){chat.title=name.trim().slice(0,80);saveChats();drawChatList();updateTitle();}};
  const remove=document.createElement('button');remove.className='chat-action';remove.textContent='×';remove.setAttribute('aria-label','Delete '+chat.title);remove.disabled=busy;
  remove.onclick=()=>{if(!window.confirm('Delete this saved conversation?'))return;chats=chats.filter(item=>item.id!==chat.id);if(chat.id===currentId){currentId=chats[0]?.id;if(!currentId){createChat();return;}}saveChats();showChat();};
  row.append(title,rename,remove);$('chatList').append(row);
  const option=document.createElement('option');option.value=chat.id;option.textContent=chat.title;option.selected=chat.id===currentId;$('chatPicker').append(option);
 }
}
function updateTitle(){$('chatTitle').textContent=currentChat().title;}
function showChat(){
 const chat=currentChat();$('messages').replaceChildren();
 for(const turn of chat.messages){const item=message(turn.role,turn.content);if(turn.role==='assistant')addCopy(item,turn.content);}
 $('welcome').classList.toggle('empty',chat.messages.length>0);$('metrics').textContent=storageError||'Saved in this browser';
 updateMemory();updateTitle();drawChatList();scrollChat();
}
function switchChat(id){if(busy)return;currentId=id;saveChats();showChat();$('prompt').value='';}
function createChat(){
 if(busy)return;
 const empty=chats.find(chat=>chat.messages.length===0);
 if(empty){currentId=empty.id;}else{
  const chat={id:crypto.randomUUID(),title:'New conversation',messages:[],contextMessages:[],summary:'',updatedAt:new Date().toISOString()};
  chats.unshift(chat);currentId=chat.id;
 }
 saveChats();showChat();$('prompt').value='';$('prompt').focus();
}
function exportChat(){
 const chat=currentChat();const url=URL.createObjectURL(new Blob([JSON.stringify(chat,null,2)],{type:'application/json'}));
 const link=document.createElement('a');link.href=url;link.download='twil-chat-'+chat.id+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function health(){
 try{online=(await fetch('/api/health',{cache:'no-store'})).ok;}catch{online=false;}
 $('status').className='status '+(online?'online':'offline');$('statusText').textContent=online?'Model online':'Model offline';
}
function setBusy(value){busy=value;$('send').textContent=value?'Stop ■':'Send ↑';$('send').classList.toggle('stop',value);$('prompt').disabled=value;$('newChat').disabled=value;$('mobileClear').disabled=value;$('chatPicker').disabled=value;$('exportChat').disabled=value;drawChatList();}
async function prepareChat(chat,maxTokens,signal){
 const response=await fetch('/api/context',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:chat.contextMessages,summary:chat.summary,max_tokens:maxTokens}),signal});
 const data=await response.json();if(!response.ok)throw new Error(data.error||'Context preparation failed.');
 chat.contextMessages=data.messages;chat.summary=data.summary;updateMemory();saveChats();return data;
}
async function sendChat(event){
 event.preventDefault();if(busy)return;const text=$('prompt').value.trim();if(!text)return;
 if(!online){await health();if(!online){$('metrics').textContent='Model offline. Start the model server first.';return;}}
 const chat=currentChat();const turn={role:'user',content:text};chat.messages.push(turn);chat.contextMessages.push(turn);
 if(chat.title==='New conversation')chat.title=text.slice(0,48);
 chat.updatedAt=new Date().toISOString();saveChats();$('welcome').classList.add('empty');message('user',text);$('prompt').value='';updateTitle();
 const answer=message('assistant','Preparing conversation…');answer.content.classList.add('pending');setBusy(true);controller=new AbortController();
 let output='',chunks=0,finishReason='',succeeded=false,prepared=null;const started=performance.now();
 try{
  const maxTokens=Number($('tokens').value);prepared=await prepareChat(chat,maxTokens,controller.signal);
  answer.content.textContent=prepared.compacted?'Earlier turns summarized. Thinking…':'Thinking…';
  const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:chat.contextMessages,summary:chat.summary,max_tokens:maxTokens,temperature:Number($('temperature').value)}),signal:controller.signal});
  if(!response.ok){let data;try{data=await response.json();}catch{}throw new Error(data?.error||'The model could not complete this request.');}
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
  function consume(frame){for(const line of frame.split('\n')){
   if(!line.startsWith('data:'))continue;const raw=line.slice(5).trim();if(!raw||raw==='[DONE]')continue;
   const data=JSON.parse(raw);if(data.error)throw new Error(data.error);const choice=data.choices?.[0];if(choice?.finish_reason)finishReason=choice.finish_reason;
   const delta=choice?.delta?.content;if(delta){output+=delta;chunks++;answer.content.classList.remove('pending');renderAnswer(answer.content,output);scrollChat();}
  }}
  while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});buffer=buffer.replace(/\r\n/g,'\n');let cut;while((cut=buffer.indexOf('\n\n'))!==-1){consume(buffer.slice(0,cut));buffer=buffer.slice(cut+2);}if(done){if(buffer.trim())consume(buffer);break;}}
  if(!output)throw new Error('No visible answer returned. Try again.');succeeded=true;
 }catch(error){
  if(error.name==='AbortError'){if(!output)answer.content.textContent='Response stopped.';}
  else{answer.el.classList.add('error');answer.content.textContent=output?output+'\n\n'+error.message:error.message;}
 }finally{
  answer.content.classList.remove('pending');
  if(output){const reply={role:'assistant',content:output};chat.messages.push(reply);chat.contextMessages.push(reply);addCopy(answer,output);}
  else{chat.messages.pop();chat.contextMessages.pop();$('prompt').value=text;}
  saveChats();const elapsed=((performance.now()-started)/1000).toFixed(1);
  $('metrics').textContent=storageError||(output?`${elapsed}s · ${chunks} chunks${prepared?.compacted?' · Summarized':''}${finishReason==='length'?' · Response limit reached':succeeded?' · Saved':' · Stopped'}`:'Ready to retry');
  setBusy(false);controller=null;$('prompt').focus();scrollChat();
 }
}
$('temperature').addEventListener('input',()=>$('tempValue').textContent=$('temperature').value);
$('newChat').onclick=createChat;$('mobileClear').onclick=createChat;$('exportChat').onclick=exportChat;
$('chatPicker').onchange=()=>switchChat($('chatPicker').value);
document.querySelectorAll('[data-prompt]').forEach(button=>button.onclick=()=>{if(!busy){$('prompt').value=button.dataset.prompt;$('prompt').focus();}});
$('prompt').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();if(!busy)$('chatForm').requestSubmit();}});
$('send').addEventListener('click',event=>{if(busy){event.preventDefault();controller.abort();}});
$('chatForm').addEventListener('submit',sendChat);
restoreChats();health();setInterval(health,15000);
