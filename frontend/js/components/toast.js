export function createToast({ toastId = 'error-toast', messageId = 'error-message', duration = 3000 } = {}) {
    let timer;
    return (message) => {
        const toast = document.getElementById(toastId);
        const label = document.getElementById(messageId);
        if (!toast || !label) return;
        label.textContent = message;
        toast.classList.remove('hidden');
        clearTimeout(timer);
        timer = setTimeout(() => toast.classList.add('hidden'), duration);
    };
}

