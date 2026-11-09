// voicevision for VS Code.
//
// Plain CommonJS, no build step and no third-party dependency: the extension
// runs directly in VS Code's Node runtime. Microphone capture is delegated to
// `voicevision-listen`; file transcription and LLM answers go through the
// local HTTP server (T035).

"use strict";

const vscode = require("vscode");
const { spawn } = require("child_process");
const fs = require("fs/promises");

const COMMAND_DICTATE = "voicevision.dictate";
const COMMAND_TRANSCRIBE_FILE = "voicevision.transcribeFile";
const COMMAND_ASK = "voicevision.ask";

function configuration() {
  return vscode.workspace.getConfiguration("voicevision");
}

function serverUrl() {
  return String(configuration().get("serverUrl", "http://127.0.0.1:8765")).replace(/\/+$/, "");
}

async function post(pathname, payload) {
  const headers = { "Content-Type": "application/json" };
  const token = configuration().get("token", "");
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${serverUrl()}${pathname}`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  const text = await response.text();

  let body;
  try {
    body = JSON.parse(text);
  } catch {
    body = { error: text };
  }
  if (!response.ok) {
    throw new Error(body.error || `HTTP ${response.status}`);
  }
  return body;
}

function insertAtCursor(text) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("voicevision: no active editor");
    return false;
  }
  editor.edit((builder) => builder.insert(editor.selection.active, text));
  return true;
}

function runListen() {
  const command = String(configuration().get("listenCommand", "voicevision-listen"));
  const args = [...configuration().get("listenArgs", ["--quiet"])];
  const language = configuration().get("language", "");
  if (language) {
    args.push("--language", language);
  }

  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve(stdout.trim());
      } else {
        reject(new Error(stderr.trim() || `voicevision-listen exited with ${code}`));
      }
    });
  });
}

async function dictate() {
  const transcript = await runListen();
  if (!transcript) {
    vscode.window.showInformationMessage("voicevision: nothing transcribed");
    return;
  }
  insertAtCursor(transcript);
}

async function transcribeFile() {
  const picked = await vscode.window.showOpenDialog({
    canSelectMany: false,
    filters: { Audio: ["wav"] },
  });
  if (!picked || picked.length === 0) {
    return;
  }

  const audio = await fs.readFile(picked[0].fsPath);
  const language = configuration().get("language", "");
  const payload = { audio_base64: audio.toString("base64") };
  if (language) {
    payload.language = language;
  }

  const result = await post("/transcribe", payload);
  insertAtCursor(result.transcript || "");
}

async function ask() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("voicevision: no active editor");
    return;
  }
  const selection = editor.document.getText(editor.selection);
  if (!selection.trim()) {
    vscode.window.showWarningMessage("voicevision: select some text first");
    return;
  }

  const result = await post("/converse", {
    text: selection,
    max_tokens: configuration().get("maxTokens", 512),
  });
  insertAtCursor(result.response || "");
}

function guarded(action) {
  return async (...args) => {
    try {
      await action(...args);
    } catch (error) {
      const message = error && error.message ? error.message : String(error);
      vscode.window.showErrorMessage(`voicevision: ${message}`);
    }
  };
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand(COMMAND_DICTATE, guarded(dictate)),
    vscode.commands.registerCommand(COMMAND_TRANSCRIBE_FILE, guarded(transcribeFile)),
    vscode.commands.registerCommand(COMMAND_ASK, guarded(ask)),
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
