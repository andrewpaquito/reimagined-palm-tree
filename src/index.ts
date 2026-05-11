#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
    CallToolRequestSchema,
    ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { SpeechifyClient, Speechify } from "@speechify/api";
import { createWriteStream } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, resolve } from "node:path";
import { pipeline } from "node:stream/promises";

const SERVER_NAME = "speechify-mcp";
const SERVER_VERSION = "0.1.0";

const DEFAULT_VOICE = "george";
const DEFAULT_AUDIO_FORMAT = "mp3";

const SPEECH_FORMATS = ["mp3", "wav", "ogg", "aac", "pcm"] as const;
const STREAM_FORMATS = ["mp3", "ogg", "aac", "pcm"] as const;
const MODELS = ["simba-english", "simba-multilingual"] as const;

type SpeechFormat = (typeof SPEECH_FORMATS)[number];
type StreamFormat = (typeof STREAM_FORMATS)[number];

const STREAM_ACCEPT_BY_FORMAT: Record<StreamFormat, Speechify.tts.AudioStreamRequestAccept> = {
    mp3: "audio/mpeg",
    ogg: "audio/ogg",
    aac: "audio/aac",
    pcm: "audio/pcm",
};

function getApiKey(): string {
    const key = process.env.SPEECHIFY_API_KEY;
    if (!key || !key.trim()) {
        console.error(
            "[speechify-mcp] SPEECHIFY_API_KEY is not set. Get one at https://console.sws.speechify.com/ and pass it via --env when registering the server.",
        );
        process.exit(1);
    }
    return key.trim();
}

const client = new SpeechifyClient({ token: getApiKey() });

const server = new Server(
    { name: SERVER_NAME, version: SERVER_VERSION },
    { capabilities: { tools: {} } },
);

const TOOLS = [
    {
        name: "text_to_speech",
        description:
            "Synthesize audio from text using Speechify and write it to disk. Suited for short-to-medium passages (the non-streaming endpoint accepts up to ~2000 characters). Returns the resolved output path and byte size. For longer text, prefer `stream_text_to_speech`.",
        inputSchema: {
            type: "object",
            additionalProperties: false,
            properties: {
                input: {
                    type: "string",
                    description: "Plain text or SSML to synthesize. Max ~2000 characters.",
                    minLength: 1,
                },
                output_path: {
                    type: "string",
                    description:
                        "Where to write the audio file. Absolute paths are used as-is; relative paths resolve against the OS temp dir. The file extension should match `audio_format`.",
                    minLength: 1,
                },
                voice_id: {
                    type: "string",
                    description: `Speechify voice id. Call list_voices to discover available ids. Defaults to "${DEFAULT_VOICE}".`,
                },
                audio_format: {
                    type: "string",
                    enum: SPEECH_FORMATS,
                    description: `Output audio format. Defaults to "${DEFAULT_AUDIO_FORMAT}".`,
                },
                model: {
                    type: "string",
                    enum: MODELS,
                    description:
                        'Synthesis model. Use "simba-english" for English-only (highest quality) or "simba-multilingual" for 50+ languages.',
                },
                language: {
                    type: "string",
                    description:
                        'BCP-47 language code (e.g. "en-US", "es-MX"). Only meaningful when model="simba-multilingual".',
                },
            },
            required: ["input", "output_path"],
        },
    },
    {
        name: "stream_text_to_speech",
        description:
            "Stream long-form text to an audio file via Speechify's streaming endpoint. Supports up to ~20000 characters per call. WAV is not available for streaming — use mp3, ogg, aac, or pcm.",
        inputSchema: {
            type: "object",
            additionalProperties: false,
            properties: {
                input: {
                    type: "string",
                    description: "Plain text or SSML to synthesize. Max ~20000 characters.",
                    minLength: 1,
                },
                output_path: {
                    type: "string",
                    description:
                        "Where to write the streamed audio. Absolute paths are used as-is; relative paths resolve against the OS temp dir.",
                    minLength: 1,
                },
                voice_id: {
                    type: "string",
                    description: `Speechify voice id. Defaults to "${DEFAULT_VOICE}".`,
                },
                audio_format: {
                    type: "string",
                    enum: STREAM_FORMATS,
                    description: `Streaming output format. Defaults to "${DEFAULT_AUDIO_FORMAT}". WAV is intentionally excluded.`,
                },
                model: {
                    type: "string",
                    enum: MODELS,
                    description: "Synthesis model.",
                },
                language: {
                    type: "string",
                    description: "BCP-47 language code.",
                },
            },
            required: ["input", "output_path"],
        },
    },
    {
        name: "list_voices",
        description:
            "List the voices available on the authenticated Speechify account, including built-in voices and any cloned/personal voices. Returns each voice's id, display name, gender, locale, type, and supported models.",
        inputSchema: {
            type: "object",
            additionalProperties: false,
            properties: {},
        },
    },
] as const;

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: rawArgs } = request.params;
    const args = (rawArgs ?? {}) as Record<string, unknown>;
    try {
        switch (name) {
            case "text_to_speech":
                return await handleTextToSpeech(args);
            case "stream_text_to_speech":
                return await handleStreamTextToSpeech(args);
            case "list_voices":
                return await handleListVoices();
            default:
                return errorResult(`Unknown tool: ${name}`);
        }
    } catch (err) {
        return errorResult(formatError(err));
    }
});

function errorResult(message: string) {
    return {
        isError: true,
        content: [{ type: "text" as const, text: message }],
    };
}

function textResult(text: string) {
    return { content: [{ type: "text" as const, text }] };
}

function formatError(err: unknown): string {
    if (err instanceof Error) {
        const detail = (err as { body?: unknown }).body;
        const suffix =
            detail && typeof detail === "object" ? ` — ${JSON.stringify(detail)}` : "";
        return `${err.name}: ${err.message}${suffix}`;
    }
    return String(err);
}

function requireString(args: Record<string, unknown>, key: string): string {
    const value = args[key];
    if (typeof value !== "string" || value.length === 0) {
        throw new Error(`Argument "${key}" is required and must be a non-empty string.`);
    }
    return value;
}

function optionalString(args: Record<string, unknown>, key: string): string | undefined {
    const value = args[key];
    if (value === undefined || value === null) return undefined;
    if (typeof value !== "string") {
        throw new Error(`Argument "${key}" must be a string when provided.`);
    }
    return value;
}

function resolveOutputPath(outputPath: string): string {
    return isAbsolute(outputPath) ? outputPath : resolve(tmpdir(), outputPath);
}

async function handleTextToSpeech(args: Record<string, unknown>) {
    const input = requireString(args, "input");
    const outputPath = requireString(args, "output_path");
    const voiceId = optionalString(args, "voice_id") ?? DEFAULT_VOICE;
    const audioFormat = (optionalString(args, "audio_format") ?? DEFAULT_AUDIO_FORMAT) as SpeechFormat;
    if (!SPEECH_FORMATS.includes(audioFormat)) {
        return errorResult(`Unsupported audio_format "${audioFormat}". Use one of: ${SPEECH_FORMATS.join(", ")}.`);
    }
    const model = optionalString(args, "model") as Speechify.tts.GetSpeechRequestModel | undefined;
    const language = optionalString(args, "language");

    const resolvedPath = resolveOutputPath(outputPath);
    await mkdir(dirname(resolvedPath), { recursive: true });

    const response = await client.tts.audio.speech({
        input,
        voiceId,
        audioFormat,
        ...(model ? { model } : {}),
        ...(language ? { language } : {}),
    });

    const buffer = Buffer.from(response.audioData, "base64");
    await writeFile(resolvedPath, buffer);

    return textResult(
        [
            `Wrote ${buffer.byteLength} bytes of ${audioFormat} audio to ${resolvedPath}`,
            `Billable characters: ${response.billableCharactersCount}`,
            `Voice: ${voiceId}${model ? ` (model: ${model})` : ""}${language ? ` (language: ${language})` : ""}`,
        ].join("\n"),
    );
}

async function handleStreamTextToSpeech(args: Record<string, unknown>) {
    const input = requireString(args, "input");
    const outputPath = requireString(args, "output_path");
    const voiceId = optionalString(args, "voice_id") ?? DEFAULT_VOICE;
    const audioFormat = (optionalString(args, "audio_format") ?? DEFAULT_AUDIO_FORMAT) as StreamFormat;
    if (!STREAM_FORMATS.includes(audioFormat)) {
        return errorResult(
            `Unsupported streaming audio_format "${audioFormat}". Streaming supports: ${STREAM_FORMATS.join(", ")}.`,
        );
    }
    const model = optionalString(args, "model") as Speechify.tts.GetStreamRequestModel | undefined;
    const language = optionalString(args, "language");

    const resolvedPath = resolveOutputPath(outputPath);
    await mkdir(dirname(resolvedPath), { recursive: true });

    const stream = await client.tts.audio.stream({
        input,
        voiceId,
        accept: STREAM_ACCEPT_BY_FORMAT[audioFormat],
        ...(model ? { model } : {}),
        ...(language ? { language } : {}),
    });

    const writer = createWriteStream(resolvedPath);
    await pipeline(stream, writer);

    return textResult(
        [
            `Streamed ${writer.bytesWritten} bytes of ${audioFormat} audio to ${resolvedPath}`,
            `Voice: ${voiceId}${model ? ` (model: ${model})` : ""}${language ? ` (language: ${language})` : ""}`,
        ].join("\n"),
    );
}

async function handleListVoices() {
    const voices = await client.tts.voices.list();
    if (voices.length === 0) {
        return textResult("No voices available on this account.");
    }
    const lines = voices.map((v) => {
        const models = v.models.map((m) => m.name).join(", ");
        return `- ${v.id} | ${v.displayName} | ${v.gender} | locale=${v.locale} | type=${v.type} | models=${models}`;
    });
    return textResult(`Found ${voices.length} voice(s):\n${lines.join("\n")}`);
}

async function main() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error(`[speechify-mcp] ${SERVER_NAME} v${SERVER_VERSION} running on stdio`);
}

main().catch((err) => {
    console.error("[speechify-mcp] Fatal error:", err);
    process.exit(1);
});
