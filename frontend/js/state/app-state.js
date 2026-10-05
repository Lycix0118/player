export function createAppState() {
    return {
        screen: 'loading',
        currentPath: [],
        currentFolder: null,
        currentVideo: null,
        currentVideos: [],
        libraryVideos: [],
        watchProgress: {},
        foldersLoaded: false
    };
}

