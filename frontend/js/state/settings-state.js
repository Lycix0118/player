import { readSettings, writeSettings } from '../utils/storage.js';

export function createSettingsState() {
    return readSettings();
}

export function updateSetting(settings, key, value) {
    const next = { ...settings, [key]: value };
    writeSettings(next);
    return next;
}

export function applyServerSettings(currentSettings, serverSettings) {
    const next = { ...currentSettings };
    if (!serverSettings || typeof serverSettings !== 'object') {
        return next;
    }
    if (typeof serverSettings.autoplay === 'boolean') {
        next.autoplay = serverSettings.autoplay;
    }
    if (typeof serverSettings.subtitles === 'boolean') {
        next.subtitles = serverSettings.subtitles;
    }
    if (typeof serverSettings.theme === 'string' && serverSettings.theme.trim()) {
        next.theme = serverSettings.theme.trim();
    }
    writeSettings(next);
    return next;
}

