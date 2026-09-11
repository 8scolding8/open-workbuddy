import { setTimeout as sleep } from 'node:timers/promises';

const PORT = Number(process.env.PORT || 3000);
const TOKEN = process.env.MCP_ACCESS_TOKEN;
const ENABLED = process.env.IMA_SMOKE_TEST === '1';

async function rpc(method, params, id) {
  const res = await fetch(`http://127.0.0.1:${PORT}/mcp`, {
    method: 'POST',
    headers: {
      'authorization': `Bearer ${TOKEN}`,
      'content-type': 'application/json',
      'accept': 'application/json, text/event-stream'
    },
    body: JSON.stringify({ jsonrpc: '2.0', id, method, params })
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} HTTP ${res.status}: ${text.slice(0,160)}`);
  let data;
  try { data = JSON.parse(text); }
  catch { throw new Error(`${method} returned non-JSON: ${text.slice(0,160)}`); }
  if (data.error) throw new Error(`${method} RPC error: ${JSON.stringify(data.error)}`);
  return data.result;
}

function parseToolText(result) {
  const t = result?.content?.find?.(x => x?.type === 'text')?.text;
  if (!t) return null;
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

function collectNamedObjects(obj, idKeys, nameKeys) {
  const out = [];
  const seen = new Set();
  walk(obj, node => {
    if (!node || Array.isArray(node)) return;
    let id = '';
    let name = '';
    for (const k of idKeys) if (typeof node[k] === 'string' && node[k]) { id = node[k]; break; }
    for (const k of nameKeys) if (typeof node[k] === 'string' && node[k]) { name = node[k]; break; }
    if (id && name && !seen.has(id)) {
      seen.add(id);
      out.push({ id, name });
    }
  });
  return out;
}

function findNextCursor(obj) {
  return firstStringByKey(obj, ['next_cursor','nextCursor','next_page_cursor','nextPageCursor']);
}

async function callTool(name, args, id) {
  const r = await rpc('tools/call', { name, arguments: args }, id);
  if (r?.isError) throw new Error(`${name} tool returned isError`);
  return parseToolText(r);
}

async function main() {
  if (!ENABLED) return;
  await sleep(1500);
  const summary = { initialize:false, tools:false, knowledgeBases:false, browse:false, search:false, read:false };
  try {
    await rpc('initialize', {
      protocolVersion: '2025-03-26',
      capabilities: {},
      clientInfo: { name:'ima-smoke-test', version:'1.1.0' }
    }, 1);
    summary.initialize = true;

    const tools = await rpc('tools/list', {}, 2);
    summary.tools = Array.isArray(tools?.tools) && tools.tools.length >= 6;

    const allKbs = [];
    const seenKb = new Set();
    let cursor = '';
    let rpcId = 3;
    for (let page = 0; page < 20; page++) {
      const kbData = await callTool('search_knowledge_base', { query:'', cursor, limit:20 }, rpcId++);
      summary.knowledgeBases = true;
      const found = collectNamedObjects(
        kbData,
        ['knowledge_base_id','knowledgeBaseId','kb_id','id'],
        ['knowledge_base_name','knowledgeBaseName','name','title']
      );
      for (const kb of found) if (!seenKb.has(kb.id)) { seenKb.add(kb.id); allKbs.push(kb); }
      const next = findNextCursor(kbData);
      if (!next || next === cursor) break;
      cursor = next;
    }

    console.log(`[IMA_KB_ENUM] ${JSON.stringify({ count: allKbs.length, knowledgeBases: allKbs })}`);

    const firstKb = allKbs[0];
    let mediaId = null;
    let title = null;
    if (firstKb?.id) {
      const listData = await callTool('get_knowledge_list', { knowledge_base_id:firstKb.id, cursor:'', limit:20 }, rpcId++);
      summary.browse = true;
      const items = collectNamedObjects(
        listData,
        ['media_id','mediaId','doc_id','document_id','folder_id','folderId','id'],
        ['title','name']
      ).slice(0,5);
      console.log(`[IMA_KB_SAMPLE] ${JSON.stringify({ knowledgeBase: firstKb, sampleItems: items })}`);
      mediaId = firstStringByKey(listData, ['media_id','mediaId','doc_id','document_id']);
      title = firstStringByKey(listData, ['title','name']);

      if (title) {
        const searchData = await callTool('search_knowledge', { query:title.slice(0,32), knowledge_base_id:firstKb.id, cursor:'' }, rpcId++);
        summary.search = true;
        const hits = collectNamedObjects(
          searchData,
          ['media_id','mediaId','doc_id','document_id','id'],
          ['title','name']
        ).slice(0,5);
        console.log(`[IMA_KB_SEARCH] ${JSON.stringify({ query:title.slice(0,32), hitCount:hits.length, hits })}`);
      }
      if (mediaId) {
        await callTool('get_media_info', { media_id:mediaId }, rpcId++);
        summary.read = true;
      }
    }

    console.log(`[IMA_SMOKE] PASS ${JSON.stringify({ ...summary, knowledgeBaseCount: allKbs.length })}`);
  } catch (e) {
    console.error(`[IMA_SMOKE] FAIL ${JSON.stringify(summary)} :: ${e?.message || String(e)}`);
  }
}

main();
