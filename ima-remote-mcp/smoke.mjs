import { setTimeout as sleep } from 'node:timers/promises';
const PORT = Number(process.env.PORT || 3000);
const TOKEN = process.env.MCP_ACCESS_TOKEN;
const ENABLED = process.env.IMA_SMOKE_TEST === '1';

async function rpc(method, params, id) {
  const res = await fetch(`http://127.0.0.1:${PORT}/mcp`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${TOKEN}`,
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream'
    },
    body: JSON.stringify({ jsonrpc:'2.0', id, method, params })
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

if (ENABLED) {
  await sleep(1500);
  try {
    await rpc('initialize', { protocolVersion:'2025-03-26', capabilities:{}, clientInfo:{name:'ima-schema-probe',version:'1.0'} }, 1);
    const kb = await callTool('search_knowledge_base', { query:'', cursor:'', limit:20 }, 2);
    console.log(`[IMA_KB_RAW] ${JSON.stringify(kb)}`);
  } catch (e) {
    console.error(`[IMA_KB_RAW_FAIL] ${e?.message || String(e)}`);
  }
}
