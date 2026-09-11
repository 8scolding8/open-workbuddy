import { setTimeout as sleep } from 'node:timers/promises';
const PORT = Number(process.env.PORT || 3000);
const TOKEN = process.env.MCP_ACCESS_TOKEN;
const ENABLED = process.env.IMA_SMOKE_TEST === '1';

async function rpc(method, params, id) {
  const res = await fetch(`http://127.0.0.1:${PORT}/mcp`, {
    method:'POST',
    headers:{ authorization:`Bearer ${TOKEN}`, 'content-type':'application/json', accept:'application/json, text/event-stream' },
    body:JSON.stringify({ jsonrpc:'2.0', id, method, params })
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} HTTP ${res.status}: ${text.slice(0,200)}`);
  const data = JSON.parse(text);
  if (data.error) throw new Error(JSON.stringify(data.error));
  return data.result;
}

async function callTool(name, args, id) {
  const r = await rpc('tools/call', { name, arguments:args }, id);
  if (r?.isError) throw new Error(`${name} isError`);
  const t = r?.content?.find?.(x => x?.type === 'text')?.text;
  try { return JSON.parse(t); } catch { return t; }
}

function walk(obj, visitor) {
  if (!obj || typeof obj !== 'object') return;
  visitor(obj);
  if (Array.isArray(obj)) for (const x of obj) walk(x, visitor);
  else for (const v of Object.values(obj)) walk(v, visitor);
}
function firstStringByKey(obj, keys) {
  let found = null;
  walk(obj, node => {
    if (found || !node || Array.isArray(node)) return;
    for (const k of keys) if (typeof node[k] === 'string' && node[k]) { found = node[k]; break; }
  });
  return found;
}

if (ENABLED) {
  await sleep(1500);
  try {
    await rpc('initialize', { protocolVersion:'2025-03-26', capabilities:{}, clientInfo:{name:'ima-full-enumerator',version:'1.0'} }, 1);
    const tools = await rpc('tools/list', {}, 2);
    console.log(`[IMA_TOOLS] ${JSON.stringify(tools?.tools?.map?.(x => x.name) || [])}`);

    const all = [];
    let cursor = '';
    let id = 3;
    for (let page = 1; page <= 100; page++) {
      const data = await callTool('search_knowledge_base', { query:'', cursor, limit:20 }, id++);
      const list = Array.isArray(data?.info_list) ? data.info_list : [];
      const pageItems = list.map(x => ({
        id:x.kb_id,
        name:x.kb_name,
        type:x.base_type,
        role:x.role_type,
        content_count:x.content_count
      }));
      all.push(...pageItems);
      console.log(`[IMA_KB_PAGE] ${JSON.stringify({ page, count:pageItems.length, names:pageItems.map(x => x.name), is_end:!!data?.is_end })}`);
      if (data?.is_end || !data?.next_cursor) break;
      cursor = data.next_cursor;
    }

    console.log(`[IMA_KB_ALL] ${JSON.stringify({ count:all.length, knowledgeBases:all })}`);

    const owned = all.find(x => x.role === '创建者') || all[0];
    if (owned?.id) {
      const listData = await callTool('get_knowledge_list', { knowledge_base_id:owned.id, cursor:'', limit:10 }, id++);
      const sampleTitle = firstStringByKey(listData, ['title','name','media_name','file_name']);
      const mediaId = firstStringByKey(listData, ['media_id','mediaId','doc_id','document_id']);
      console.log(`[IMA_BROWSE_CHECK] ${JSON.stringify({ knowledgeBase:owned.name, ok:true, sampleTitle:sampleTitle || null, hasReadableItem:!!mediaId })}`);
      if (sampleTitle) {
        const s = await callTool('search_knowledge', { query:sampleTitle.slice(0,32), knowledge_base_id:owned.id, cursor:'' }, id++);
        console.log(`[IMA_SEARCH_CHECK] ${JSON.stringify({ knowledgeBase:owned.name, query:sampleTitle.slice(0,32), ok:!!s })}`);
      }
      if (mediaId) {
        const m = await callTool('get_media_info', { media_id:mediaId }, id++);
        console.log(`[IMA_READ_CHECK] ${JSON.stringify({ knowledgeBase:owned.name, ok:!!m })}`);
      }
    }
  } catch (e) {
    console.error(`[IMA_ENUM_FAIL] ${e?.message || String(e)}`);
  }
}
