# speechify-mcp

A [Model Context Protocol](https://modelcontextprotocol.io) server that wraps the
[Speechify text-to-speech API](https://docs.sws.speechify.com/). It runs locally on
stdio and exposes three tools to MCP clients (Claude Code, Claude Desktop, etc.):

| Tool | Purpose |
| --- | --- |
| `text_to_speech` | Synthesize a short/medium passage (≤ ~2000 chars) and write it to disk. |
| `stream_text_to_speech` | Stream a longer passage (≤ ~20000 chars) to disk. |
| `list_voices` | List voices available on the authenticated account. |

## Prerequisites

- Node.js 18 or newer
- A Speechify API key — create one at <https://console.sws.speechify.com/>

## Install and build

```bash
git clone https://github.com/andrewpaquito/reimagined-palm-tree.git speechify-mcp
cd speechify-mcp
npm install
npm run build
```

The compiled entry point is `dist/index.js`. It expects `SPEECHIFY_API_KEY` to be
provided in the environment when the MCP client launches it.

## Register with Claude Code

PowerShell (Windows):

```powershell
claude mcp add speechify `
  --env SPEECHIFY_API_KEY=<your-key> `
  -- node "C:\path\to\speechify-mcp\dist\index.js"
```

bash / zsh:

```bash
claude mcp add speechify \
  --env SPEECHIFY_API_KEY=<your-key> \
  -- node "$(pwd)/dist/index.js"
```

To register it for the current project only, append `--scope project` (writes to
`.mcp.json` in the project root). Use `--scope user` for a global registration.

## Manual config (Claude Desktop, other MCP clients)

Add an entry like this to your client's MCP server config:

```json
{
  "mcpServers": {
    "speechify": {
      "command": "node",
      "args": ["/absolute/path/to/speechify-mcp/dist/index.js"],
      "env": {
        "SPEECHIFY_API_KEY": "<your-key>"
      }
    }
  }
}
```

## Tool reference

### `text_to_speech`

| Field | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `input` | string | yes | — | Plain text or SSML. Max ~2000 chars. |
| `output_path` | string | yes | — | Absolute path, or relative path resolved against the OS temp dir. |
| `voice_id` | string | no | `george` | See `list_voices`. |
| `audio_format` | enum | no | `mp3` | `mp3` \| `wav` \| `ogg` \| `aac` \| `pcm`. |
| `model` | enum | no | server default | `simba-english` \| `simba-multilingual`. |
| `language` | string | no | — | BCP-47 (e.g. `en-US`). Only useful with `simba-multilingual`. |

Returns the byte count, the resolved path, and the billable character count.

### `stream_text_to_speech`

Same arguments as `text_to_speech` except:

- `input` may be up to ~20000 characters.
- `audio_format` does **not** support `wav` (streaming limitation).

Use this for longer passages — audio is written progressively as it arrives.

### `list_voices`

No arguments. Returns one line per voice with id, display name, gender, locale,
type (built-in vs cloned), and supported models.

## Local development

```bash
npm run dev      # tsc --watch
npm run start    # node dist/index.js (requires SPEECHIFY_API_KEY)
npm run clean    # remove dist/
```

To quickly probe the server without an MCP client:

```bash
SPEECHIFY_API_KEY=<key> node dist/index.js
# Then send JSON-RPC messages on stdin, one per line.
```

## Troubleshooting

- **`SPEECHIFY_API_KEY is not set`** — the server exits immediately if the env var
  is missing or empty. Make sure your MCP client passes it through.
- **401 / 403 errors** — the key is rejected; verify it in the Speechify console
  and rotate if it leaked.
- **WAV streaming error** — use `text_to_speech` (the non-streaming endpoint
  supports WAV) or pick another format for streaming.

## License

MIT
