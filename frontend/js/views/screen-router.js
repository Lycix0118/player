export class ScreenRouter {
    constructor({ onLeavePlayer } = {}) {
        this.current = 'loading';
        this.onLeavePlayer = onLeavePlayer;
    }

    show(name) {
        if (this.current === 'player' && name !== 'player') this.onLeavePlayer?.();
        ['folders', 'videos', 'player', 'settings'].forEach((screenName) => {
            document.getElementById(`${screenName}-screen`)?.classList.add('hidden');
        });
        document.getElementById(`${name}-screen`)?.classList.remove('hidden');
        this.current = name;
    }
}

