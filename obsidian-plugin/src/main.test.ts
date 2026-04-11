// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Paul Chen / axoviq.com
import { describe, it, expect, vi, afterEach } from "vitest";

vi.mock("obsidian", () => ({
    Plugin: class {
        app: any;
        addCommand    = vi.fn();
        addRibbonIcon = vi.fn();
        addSettingTab = vi.fn();
        loadData      = vi.fn().mockResolvedValue({});
        saveData      = vi.fn().mockResolvedValue(undefined);
        constructor(app?: any) { this.app = app; }
    },
    PluginSettingTab: class {
        app: any; plugin: any;
        containerEl = { empty: vi.fn(), createEl: vi.fn().mockReturnValue({ style: {}, setText: vi.fn() }) };
        constructor(app: any, plugin: any) { this.app = app; this.plugin = plugin; }
        display() {}
    },
    Setting: class {
        constructor(_el: any) {}
        setName  = vi.fn().mockReturnThis();
        setDesc  = vi.fn().mockReturnThis();
        addText  = vi.fn().mockReturnThis();
    },
    Modal: class {
        app: any;
        contentEl = {
            createEl: vi.fn().mockReturnValue({
                style: {}, onclick: null, disabled: false, setText: vi.fn(), value: "",
            }),
            empty: vi.fn(),
        };
        open = vi.fn(); close = vi.fn();
        constructor(app: any) { this.app = app; }
    },
    Notice: vi.fn(),
    TFile: class {},
    App: class {},
}));

vi.mock("./api", () => ({
    api: {
        ingest: vi.fn(), lint: vi.fn(), lintReport: vi.fn(), status: vi.fn(),
        query: vi.fn(), health: vi.fn(), jobs: vi.fn(),
    },
    setBase: vi.fn(),
}));

afterEach(() => vi.clearAllMocks());

describe("SynthadocPlugin.onload", () => {
    it("calls setBase with default serverUrl when no saved settings exist", async () => {
        const { setBase } = await import("./api");
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.onload();
        expect(setBase).toHaveBeenCalledWith("http://127.0.0.1:7070");
    });

    it("calls setBase with persisted serverUrl from loadData", async () => {
        const { setBase } = await import("./api");
        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        (plugin.loadData as any).mockResolvedValueOnce({ serverUrl: "http://127.0.0.1:7071" });
        await plugin.onload();
        expect(setBase).toHaveBeenCalledWith("http://127.0.0.1:7071");
    });
});

describe("SynthadocPlugin.ingestFile", () => {
    it("calls api.ingest with file path and shows Notice with job_id", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.ingest as any).mockResolvedValueOnce({ job_id: "job-xyz" });

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.ingestFile({ path: "notes/paper.md" } as any);

        expect(api.ingest).toHaveBeenCalledWith("notes/paper.md");
        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("job-xyz"));
    });

    it("shows error Notice when api.ingest throws", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.ingest as any).mockRejectedValueOnce(new Error("connection refused"));

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        await plugin.ingestFile({ path: "notes/paper.md" } as any);

        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("failed"));
    });
});

describe("SynthadocPlugin.ingestAllSources", () => {
    it("queues every file under rawSourcesFolder and shows summary", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.ingest as any).mockResolvedValue({ job_id: "job-1" });

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        plugin.app = {
            vault: {
                getFiles: () => [
                    { path: "raw_sources/file-a.pdf", extension: "pdf" },
                    { path: "raw_sources/file-b.png", extension: "png" },
                    { path: "wiki/page.md",           extension: "md"  },  // excluded (wrong folder)
                    { path: "raw_sources/script.py",  extension: "py"  },  // excluded (unsupported)
                ],
            },
        } as any;
        await plugin.ingestAllSources();

        expect(api.ingest).toHaveBeenCalledTimes(2);
        expect(api.ingest).toHaveBeenCalledWith("raw_sources/file-a.pdf");
        expect(api.ingest).toHaveBeenCalledWith("raw_sources/file-b.png");
        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("2 job(s) queued"));
    });

    it("shows warning when no files found in folder", async () => {
        const { Notice } = await import("obsidian");

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        plugin.app = {
            vault: { getFiles: () => [{ path: "wiki/page.md", extension: "md" }] },
        } as any;
        await plugin.ingestAllSources();

        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("no files found"));
    });

    it("reports partial failures", async () => {
        const { api } = await import("./api");
        const { Notice } = await import("obsidian");
        (api.ingest as any)
            .mockResolvedValueOnce({ job_id: "job-1" })
            .mockRejectedValueOnce(new Error("timeout"));

        const { default: SynthadocPlugin } = await import("./main");
        const plugin = new SynthadocPlugin();
        plugin.app = {
            vault: {
                getFiles: () => [
                    { path: "raw_sources/ok.pdf",  extension: "pdf" },
                    { path: "raw_sources/bad.pdf", extension: "pdf" },
                ],
            },
        } as any;
        await plugin.ingestAllSources();

        expect(Notice).toHaveBeenCalledWith(expect.stringContaining("1 queued, 1 failed"));
    });
});
