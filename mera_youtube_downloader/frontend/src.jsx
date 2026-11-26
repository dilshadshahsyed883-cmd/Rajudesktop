import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ConfigProvider,theme,Button,Input,Select,Checkbox,Progress,Card,Space,Typography,Modal,Alert,Tag,message} from 'antd';
import {DownloadOutlined,FolderOpenOutlined,CopyOutlined,StopOutlined,QuestionCircleOutlined,YoutubeOutlined} from '@ant-design/icons';
import 'antd/dist/reset.css';import './style.css';
const {Title,Text}=Typography;
const defaults={busy:false,status:'Ready',detail:'Connecting to desktop engine...',progress:0,speed:'—',eta:'—',size:'—',logs:[],outcome:''};
function App(){
 const [config,setConfig]=useState({url:'',folder:'',quality:'720p',playlist:false});
 const [qualities,setQualities]=useState([]),[ready,setReady]=useState(false),[state,setState]=useState(defaults),[help,setHelp]=useState(false),[starting,setStarting]=useState(false);
 const [msg,context]=message.useMessage(); const logRef=useRef(null); const api=()=>window.pywebview?.api;
 useEffect(()=>{let alive=true,timer,initializing=false; const boot=async()=>{if(!api()||initializing)return;initializing=true;try{let r=await api().init();if(!alive)return;setConfig(c=>({...c,...r.settings}));setQualities(r.qualities);setReady(true);const tick=async()=>{try{let s=await api().poll();if(alive)setState(s);}catch(e){if(alive)setState(s=>({...s,detail:'Desktop connection lost: '+String(e)}));}finally{if(alive)timer=setTimeout(tick,200)}};tick();}catch(e){if(alive)setState(s=>({...s,detail:String(e)}));}};window.addEventListener('pywebviewready',boot);boot();return()=>{alive=false;clearTimeout(timer);window.removeEventListener('pywebviewready',boot)}},[]);
 useEffect(()=>{if(!ready)return;const t=setTimeout(()=>api().save(config).then(r=>{if(!r.ok)msg.error(r.error)}).catch(e=>msg.error(String(e))),350);return()=>clearTimeout(t)},[ready,config.folder,config.quality,config.playlist]);
 useEffect(()=>{if(logRef.current)logRef.current.scrollTop=logRef.current.scrollHeight},[state.logs.length,state.logs.at(-1)]);
 const set=(key,v)=>setConfig(c=>({...c,[key]:v})); const act=async(fn)=>{try{let r=await fn();if(!r.ok)msg.error(r.error);return r}catch(e){msg.error(String(e));return {ok:false}}};
 const busy=state.busy||starting,disabled=busy||!ready;
 const start=async()=>{setStarting(true);try{let r=await act(()=>api().start(config));if(r.ok){setState(await api().poll())}}finally{setStarting(false)}};
 return <ConfigProvider theme={{algorithm:theme.darkAlgorithm,token:{colorPrimary:'#35c39e',colorBgBase:'#101727',colorText:'#eef4ff',borderRadius:9,fontFamily:'Segoe UI, system-ui, sans-serif'}}}>
 {context}<main><header><div className="brand"><div className="brandicon"><YoutubeOutlined/></div><div><Title level={2}>Mera YouTube Downloader</Title><Text type="secondary">Direct download · Windows desktop</Text></div></div><Button icon={<QuestionCircleOutlined/>} onClick={()=>setHelp(true)}>Help / Guide</Button></header>
 <Card className="panel" title="Download source" extra={<Tag color={ready?'green':'default'}>{ready?'Engine ready':'Starting engine'}</Tag>}>
 <label>YouTube video / playlist link</label><Space.Compact block><Input size="large" autoFocus value={config.url} placeholder="https://www.youtube.com/watch?v=..." disabled={disabled} onChange={e=>set('url',e.target.value)} onPressEnter={()=>!disabled&&start()}/><Button size="large" icon={<CopyOutlined/>} disabled={disabled} onClick={async()=>{let r=await act(()=>api().paste());if(r.ok)set('url',r.text)}}>Paste</Button></Space.Compact>
 <label>Save files in folder</label><Space.Compact block><Input value={config.folder} disabled={disabled} onChange={e=>set('folder',e.target.value)}/><Button disabled={disabled} icon={<FolderOpenOutlined/>} onClick={async()=>{let r=await act(()=>api().browse());if(r.ok&&r.folder)set('folder',r.folder)}}>Browse</Button></Space.Compact>
 <div className="options"><div><label>Video / audio quality</label><Select disabled={disabled} value={config.quality} options={qualities.map(q=>({value:q,label:q}))} onChange={v=>set('quality',v)} style={{width:'100%'}}/></div><Checkbox disabled={disabled} checked={config.playlist} onChange={e=>set('playlist',e.target.checked)}>Download full playlist</Checkbox></div>
 <div className="actions"><Button type="primary" size="large" icon={<DownloadOutlined/>} disabled={disabled} onClick={start}>Download Now</Button><Button size="large" icon={<StopOutlined/>} disabled={!state.busy||state.cancelling} onClick={()=>act(()=>api().cancel())}>Cancel</Button><Button size="large" icon={<FolderOpenOutlined/>} disabled={!ready} onClick={()=>act(()=>api().open_folder(config.folder))}>Open Folder</Button></div></Card>
 <Card className="panel" title="Download progress" extra={<Tag color={state.outcome==='success'?'green':state.outcome==='error'?'red':state.busy?'blue':'default'}>{state.status}</Tag>}>
 <Progress percent={Math.round(state.progress)} status={state.outcome==='error'?'exception':state.busy?'active':state.outcome==='success'?'success':'normal'}/>
 <div className="stats">{[['Downloaded',state.size],['Speed',state.speed],['ETA',state.eta]].map(([l,v])=><div key={l}><small>{l}</small><strong>{v}</strong></div>)}</div>
 <Alert showIcon type={state.outcome==='error'?'error':state.outcome==='success'?'success':'info'} message={state.detail}/></Card>
 <Card className="panel logpanel" title="Activity log" extra={<Text type="secondary">Latest 500 entries</Text>}><div ref={logRef} className="log" role="log">{state.logs.map((line,i)=><div key={i}>{line}</div>)}</div></Card>
 <footer>Only download content you own or have permission to save.</footer>
 <Modal title="Help / Guide" open={help} onCancel={()=>setHelp(false)} footer={<Button type="primary" onClick={()=>setHelp(false)}>Close</Button>}><p>Paste a YouTube link, choose a folder and quality, then select Download Now.</p><p>Enable the playlist option to download a full playlist. MP3 audio is available at 192 kbps. Cancelled downloads may resume from partial files when retried.</p><p>Downloads use direct yt-dlp extraction. No browser login or CAPTCHA verification is built in. If YouTube denies access, the actual error is displayed in the log.</p></Modal>
 </main></ConfigProvider>
}
createRoot(document.getElementById('root')).render(<App/>);
