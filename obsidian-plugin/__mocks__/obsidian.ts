import { vi } from "vitest";

export class Plugin {
    app: any;
    addCommand = vi.fn();
    addRibbonIcon = vi.fn();
    addSettingTab = vi.fn();
    loadData = vi.fn().mockResolvedValue({});
    saveData = vi.fn().mockResolvedValue(undefined);
    constructor(app?: any) { this.app = app; }
}

export class Modal {
    app: any;
    contentEl = {
        createEl: vi.fn().mockReturnValue({
            style: {},
            onclick: null,
            disabled: false,
            setText: vi.fn(),
            value: "",
        }),
        empty: vi.fn(),
    };
    open = vi.fn();
    close = vi.fn();
    constructor(app: any) { this.app = app; }
}

export class PluginSettingTab {
    app: any;
    plugin: any;
    containerEl = {
        empty: vi.fn(),
        createEl: vi.fn().mockReturnValue({ style: {}, setText: vi.fn() }),
    };
    constructor(app: any, plugin: any) { this.app = app; this.plugin = plugin; }
    display() {}
}

export class Setting {
    constructor(_containerEl: any) {}
    setName  = vi.fn().mockReturnThis();
    setDesc  = vi.fn().mockReturnThis();
    addText  = vi.fn().mockReturnThis();
}

export const Notice = vi.fn();

export class TFile {}

export class App {}
