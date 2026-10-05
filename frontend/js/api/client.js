export class ApiError extends Error {
    constructor(message, response = null) {
        super(message);
        this.name = 'ApiError';
        this.status = response?.status ?? 0;
        this.response = response;
    }
}

export class ApiClient {
    constructor(baseUrl = window.location.origin, { timeout = 30000 } = {}) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.timeout = timeout;
    }

    resolve(path) {
        return /^https?:\/\//i.test(path) ? path : `${this.baseUrl}${path}`;
    }

    async request(path, options = {}) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), options.timeout ?? this.timeout);
        try {
            const response = await fetch(this.resolve(path), { ...options, signal: options.signal || controller.signal });
            return response;
        } catch (error) {
            if (error.name === 'AbortError') throw new ApiError('请求超时');
            throw error;
        } finally {
            clearTimeout(timer);
        }
    }

    async json(path, options = {}) {
        const response = await this.request(path, options);
        if (!response.ok) throw new ApiError(`HTTP ${response.status}`, response);
        return response.json();
    }
}

