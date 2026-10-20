// localStorage — только для удобства в этом браузере (список «моих заявок», токен аналитика).
// Он может быть недоступен (приватный режим, запрет cookies), поэтому каждое обращение в try/catch:
// сайт должен работать и без него.
const KEY_APPS = "hp.myApplications";
const KEY_TOKEN = "hp.analystToken";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* хранилище недоступно — просто не запоминаем */
  }
}

export interface SavedApplication {
  id: string;
  farm: string;
  createdAt: string;
}

export function getMyApplications(): SavedApplication[] {
  try {
    return JSON.parse(read(KEY_APPS) ?? "[]") as SavedApplication[];
  } catch {
    return [];
  }
}

export function rememberApplication(app: SavedApplication) {
  const list = [app, ...getMyApplications().filter((a) => a.id !== app.id)].slice(0, 20);
  write(KEY_APPS, JSON.stringify(list));
}

export const getAnalystToken = () => read(KEY_TOKEN) ?? "";
export const setAnalystToken = (token: string | null) => write(KEY_TOKEN, token);
