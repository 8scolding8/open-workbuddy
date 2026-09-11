import express from "express";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { ListToolsRequestSchema, CallToolRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const PORT = Number(process.env.PORT || 3000);
const BASE_URL = "https://ima.qq.com";
const API_PREFIX = "openapi/wiki/v1";
const NOTE_PREFIX = "openapi/note/v1";
const SERVER_NAME = "ima-remote-mcp";
const SERVER_VERSION = "1.0.0";

function credentials() {
  const clientId = process.env.IMA_CLIENT_ID || process.env.IMA_OPENAPI_CLIENTID;
  const apiKey = process.env.IMA_API_KEY || process.env.IMA_OPENAPI_APIKEY;
  if (!clientId || !apiKey) throw new Error("IMA credentials are not configured");
  return { clientId, apiKey };
}

function requireBearer(req, res, next) {
  const expected = process.env.MCP_ACCESS_TOKEN;
  if (!expected) return res.status(503).json({ error: "MCP_ACCESS_TOKEN is not configured" });
  const auth = req.headers.authorization || "";
  if (auth !== `Bearer ${expected}`) {
    res.setHeader("WWW-Authenticate", "Bearer");
    return res.status(401).json({ error: "Unauthorized" });
  }
  next();
}

async function imaPost(apiPath, body, prefix = API_PREFIX) {
  const { clientId, apiKey } = credentials();
  const res = await fetch(`${BASE_URL}/${prefix}/${apiPath}`, {
    method: "POST",
    headers: {
      "ima-openapi-clientid": clientId,
      "ima-openapi-apikey": apiKey,
      "ima-openapi-ctx": `mcp_server=${SERVER_VERSION}`,
      "content-type": "application/json"
    },
    body: JSON.stringify(body || {})
  });
  const text = await res.text();
  let parsed;
  try { parsed = JSON.parse(text); }
  catch { throw new Error(`IMA returned non-JSON (${res.status}): ${text.slice(0, 200)}`); }
  if (!res.ok) throw new Error(`IMA HTTP ${res.status}: ${parsed?.msg || text.slice(0, 200)}`);
  if (parsed?.code !== undefined && parsed.code !== 0) throw new Error(`IMA API error [${parsed.code}]: ${parsed.msg || "unknown"}`);
  return parsed?.data ?? parsed;
}

const TOOLS = [
  { name: "search_knowledge_base", description: "Search IMA knowledge bases. Empty query returns all visible knowledge bases.", inputSchema: { type: "object", properties: { query: { type: "string", default: "" }, cursor: { type: "string", default: "" }, limit: { type: "integer", minimum: 1, maximum: 20, default: 20 } } } },
  { name: "get_knowledge_base", description: "Get details for one or more IMA knowledge bases.", inputSchema: { type: "object", properties: { ids: { type: "array", items: { type: "string" }, minItems: 1, maxItems: 20 } }, required: ["ids"] } },
  { name: "get_knowledge_list", description: "Browse files and folders in an IMA knowledge base.", inputSchema: { type: "object", properties: { knowledge_base_id: { type: "string" }, cursor: { type: "string", default: "" }, limit: { type: "integer", minimum: 1, maximum: 50, default: 20 }, folder_id: { type: "string" } }, required: ["knowledge_base_id"] } },
  { name: "search_knowledge", description: "Search content inside a specific IMA knowledge base.", inputSchema: { type: "object", properties: { query: { type: "string" }, knowledge_base_id: { type: "string" }, cursor: { type: "string", default: "" } }, required: ["query", "knowledge_base_id"] } },
  { name: "get_media_info", description: "Get an IMA knowledge item source URL or note content when available.", inputSchema: { type: "object", properties: { media_id: { type: "string" } }, required: ["media_id"] } },
  { name: "get_note_content", description: "Read the full plain-text body of an IMA note.", inputSchema: { type: "object", properties: { note_id: { type: "string" }, target_content_format: { type: "integer", default: 0 } }, required: ["note_id"] } }
];

async function dispatch(name, args = {}) {
  switch (name) {
    case "search_knowledge_base": return imaPost("search_knowledge_base", { query: args.query ?? "", cursor: args.cursor ?? "", limit: args.limit ?? 20 });
    case "get_knowledge_base": return imaPost("get_knowledge_base", { ids: args.ids });
    case "get_knowledge_list": {
      const body = { knowledge_base_id: args.knowledge_base_id, cursor: args.cursor ?? "", limit: args.limit ?? 20 };
      if (args.folder_id) body.folder_id = args.folder_id;
      return imaPost("get_knowledge_list", body);
    }
    case "search_knowledge": return imaPost("search_knowledge", { query: args.query, knowledge_base_id: args.knowledge_base_id, cursor: args.cursor ?? "" });
    case "get_media_info": {
      const info = await imaPost("get_media_info", { media_id: args.media_id });
      const noteId = info?.notebook_ext_info?.notebook_id;
      if (noteId) {
        try {
          const doc = await imaPost("get_doc_content", { note_id: String(noteId), target_content_format: 0 }, NOTE_PREFIX);
          info.note_content = doc?.content ?? "";
        } catch (e) { info.note_content_error = e?.message || String(e); }
      }
      return info;
    }
    case "get_note_content": return imaPost("get_doc_content", { note_id: String(args.note_id), target_content_format: args.target_content_format ?? 0 }, NOTE_PREFIX);
    default: throw new Error(`Unknown tool: ${name}`);
  }
}

function createMcpServer() {
  const server = new Server({ name: SERVER_NAME, version: SERVER_VERSION }, { capabilities: { tools: {} } });
  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    try {
      const result = await dispatch(request.params.name, request.params.arguments || {});
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return { isError: true, content: [{ type: "text", text: `IMA error: ${error?.message || String(error)}` }] };
    }
  });
  return server;
}

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "2mb" }));
app.get("/health", (_req, res) => res.json({ ok: true, service: SERVER_NAME, version: SERVER_VERSION }));
app.post("/mcp", requireBearer, async (req, res) => {
  const server = createMcpServer();
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
  res.on("close", () => { void server.close(); });
  try {
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  } catch (error) {
    if (!res.headersSent) res.status(500).json({ error: error?.message || String(error) });
  }
});
app.get("/mcp", requireBearer, (_req, res) => res.status(405).set("Allow", "POST").send("Method Not Allowed"));
app.delete("/mcp", requireBearer, (_req, res) => res.status(405).set("Allow", "POST").send("Method Not Allowed"));
app.listen(PORT, "0.0.0.0", () => console.log(`${SERVER_NAME} listening on :${PORT}`));
