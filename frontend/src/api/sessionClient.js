
const API_BASE = 'https://profiles-api-536653873539.us-central1.run.app';
const jsonHeaders = { 'Content-Type': 'application/json' };


// Calls the endpoint that looksup user's email. Return the uid and the user profile
export async function resolveEmail(email) {
    const res = await fetch(`${API_BASE}/session/resolve-email`,
    {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({email})

    });

    if(!res.ok) {
        throw new Error((await res.text()) || 'Failed to resolve email');
    }

    return res.json();
}

