// voicevision for Obsidian.
//
// Plain CommonJS, no build step. The plugin is desktop-only because it reads
// audio files with Node's `fs`; inference happens on the local
// voicevision-server, never in the plugin.

"use strict";

const { Plugin, Notice, Modal, Setting, PluginSettingTab, requestUrl } = require("obsidian");
const fs = require("fs");

const DEFAULT_SETTINGS = {
  serverUrl: "http://127.0.0.1:8765",
  token: "",
  language: "",
  maxTokens: 512,
};

class PathModal extends Modal {
  constructor(app, onSubmit) {
    super(app);
    this.onSubmit = onSubmit;
    this.input = null;
  }

  onOpen() {
    const { contentEl } = this;
    contentEl.createEl("h2", { text: "Transcribe an audio file" });
    new Setting(contentEl)
      .setName("WAV file")
      .setDesc("Absolute path to a 16 kHz mono WAV file.")
      .addText((text) => {
        this.input = text;
        text.setPlaceholder("/home/you/note.wav");
      });
    new Setting(contentEl).addButton((button) => {
      button
        .setButtonText("Transcribe")
        .setCta()
        .onClick(() => {
          const value = this.input ? this.input.getValue().trim() : "";
          this.close();
          if (value) {
            this.onSubmit(value);
          }
        });
    });
  }

  onClose() {
    this.contentEl.empty();
  }
}

class VoiceVisionSettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl)
      .setName("Server URL")
      .setDesc("Base URL of the local voicevision-server.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_SETTINGS.serverUrl)
          .setValue(this.plugin.settings.serverUrl)
          .onChange(async (value) => {
            this.plugin.settings.serverUrl = value.trim() || DEFAULT_SETTINGS.serverUrl;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Bearer token")
      .setDesc("Only needed when voicevision-server was started with a token.")
      .addText((text) => {
        text.inputEl.type = "password";
        text
          .setValue(this.plugin.settings.token)
          .onChange(async (value) => {
            this.plugin.settings.token = value.trim();
            await this.plugin.saveSettings();
          });
      });

    new Setting(containerEl)
      .setName("Language")
      .setDesc("STT language code (pt, en, …). Empty uses the server default.")
      .addText((text) =>
        text.setValue(this.plugin.settings.language).onChange(async (value) => {
          this.plugin.settings.language = value.trim();
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName("Maximum tokens")
      .setDesc("Answer length limit for Ask About Selection.")
      .addText((text) =>
        text.setValue(String(this.plugin.settings.maxTokens)).onChange(async (value) => {
          const parsed = Number.parseInt(value, 10);
          if (!Number.isNaN(parsed) && parsed > 0) {
            this.plugin.settings.maxTokens = parsed;
            await this.plugin.saveSettings();
          }
        })
      );
  }
}

class VoiceVisionPlugin extends Plugin {
  async onload() {
    await this.loadSettings();

    this.addCommand({
      id: "transcribe-audio-file",
      name: "Transcribe audio file",
      callback: () => this.transcribeAudioFile(),
    });

    this.addCommand({
      id: "ask-about-selection",
      name: "Ask about selection",
      editorCallback: (editor) => this.askAboutSelection(editor),
    });

    this.addSettingTab(new VoiceVisionSettingTab(this.app, this));
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  async post(pathname, payload) {
    const base = String(this.settings.serverUrl).replace(/\/+$/, "");
    const headers = { "Content-Type": "application/json" };
    if (this.settings.token) {
      headers.Authorization = `Bearer ${this.settings.token}`;
    }

    const response = await requestUrl({
      url: `${base}${pathname}`,
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      throw: false,
    });
    if (response.status >= 400) {
      let message = `HTTP ${response.status}`;
      try {
        message = response.json.error || message;
      } catch {
        // Non-JSON error body: keep the status.
      }
      throw new Error(message);
    }
    return response.json;
  }

  activeEditor() {
    const active = this.app.workspace.activeEditor;
    return active && active.editor ? active.editor : null;
  }

  insert(text) {
    const editor = this.activeEditor();
    if (!editor) {
      new Notice("voicevision: open a note first");
      return;
    }
    editor.replaceSelection(text);
  }

  async transcribeAudioFile() {
    new PathModal(this.app, async (path) => {
      try {
        const audio = fs.readFileSync(path);
        const payload = { audio_base64: audio.toString("base64") };
        if (this.settings.language) {
          payload.language = this.settings.language;
        }
        const result = await this.post("/transcribe", payload);
        this.insert(result.transcript || "");
      } catch (error) {
        new Notice(`voicevision: ${error.message || error}`);
      }
    }).open();
  }

  async askAboutSelection(editor) {
    const selection = editor.getSelection();
    if (!selection.trim()) {
      new Notice("voicevision: select some text first");
      return;
    }
    try {
      const result = await this.post("/converse", {
        text: selection,
        max_tokens: this.settings.maxTokens,
      });
      editor.replaceSelection(result.response || "");
    } catch (error) {
      new Notice(`voicevision: ${error.message || error}`);
    }
  }
}

module.exports = VoiceVisionPlugin;
