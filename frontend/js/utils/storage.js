const SETTINGS_KEY = 'player-settings';

export const DEFAULT_SETTINGS = Object.freeze({
    autoplay: false,
    subtitles: true,
    theme: 'candy'
});

export function readSettings() {
    try {
        const value = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
        return { ...DEFAULT_SETTINGS, ...(value && typeof value === 'object' ? value : {}) };
    } catch (_) {
        return { ...DEFAULT_SETTINGS };
    }
}

export function writeSettings(settings) {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...DEFAULT_SETTINGS, ...settings }));
}

