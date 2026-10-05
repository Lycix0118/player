import { readSettings, writeSettings } from '../utils/storage.js';

export function createSettingsState() {
    return readSettings();
}

export function updateSetting(settings, key, value) {
    const next = { ...settings, [key]: value };
    writeSettings(next);
    return next;
}

