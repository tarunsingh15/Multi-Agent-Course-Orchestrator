// Keeping all the API call functions in one place

const API_BASE = 'https://profiles-api-536653873539.us-central1.run.app';

const LIST_PATH = `${API_BASE}/profiles/`;

const ITEM_PATH = (id) => `${API_BASE}/profiles/${encodeURIComponent(id)}`;


const jsonHeaders = { 'Content-Type': 'application/json' };

// Util to Handle errors
async function handle(res) {
    if (res.ok) {
        const text = await res.text();
        return text ? JSON.parse(text) : null;
    }

    let message = `HTTP ${res.status}`;

    try {
        const data = await res.json();
        if (data?.error) message = data.error;
    } catch { }
    throw new Error(message);
}

// Util to compute DIFF of fields (partial updates)
export function diffProfile(org, cur) {
    const changed = {};

    if (!org || !cur) return cur || {};

    (['complexity', 'tone', 'learningStyles']).forEach(
        (k) => {
            const a = org[k], b = cur[k];
            const isArray = Array.isArray(a) || Array.isArray(b);
            const equal = isArray
                ? JSON.stringify(a || []) === JSON.stringify(b || [])
                : a === b;
            if (!equal && b !== undefined) changed[k] = b;
        }
    );

    return changed;
}

export const profileApi = {
    async list() {
        const res = await fetch(LIST_PATH,
            {
                method: 'GET',
            }
        );
        return handle(res);
    },
    async create(profile) {
        const res = await fetch(LIST_PATH,
            {
                method: 'POST',

                headers: jsonHeaders,
                body: JSON.stringify(profile),
            }
        );
        return handle(res);
    },

    async read(id) {
        const res = await fetch(ITEM_PATH(id),
            {
                method: 'GET',
            }
        );
        return handle(res);
    },
    async update(id, profile) {
        const res = await fetch(ITEM_PATH(id),
            {
                method: 'PUT',
                headers: jsonHeaders,
                body: JSON.stringify(profile),
            }
        );
        return handle(res);
    },
    async patch(id, partial) {
        const res = await fetch(ITEM_PATH(id),
            {
                method: 'PATCH',

                headers: jsonHeaders,
                body: JSON.stringify(partial),
            }
        );
        return handle(res);
    },
    async remove(id) {
        const res = await fetch(ITEM_PATH(id),
            {
                method: 'DELETE',

            }
        );
        return handle(res);
    },
};