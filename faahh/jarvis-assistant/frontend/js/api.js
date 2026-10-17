async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });

  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!response.ok) {
    const message = data?.detail || data?.message || 'Request failed';
    throw new Error(message);
  }

  return data;
}

async function apiForm(path, params = {}) {
  const query = new URLSearchParams(params);
  const response = await fetch(`${path}?${query}`, { method: 'POST' });
  const text = await response.text();
  if (!text) return null;
  try {
    const json = JSON.parse(text);
    if (!response.ok) {
      throw new Error(json?.detail || 'Request failed');
    }
    return json;
  } catch (error) {
    if (!response.ok) {
      throw error;
    }
    return text;
  }
}
