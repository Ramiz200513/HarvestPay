// Тонкий клиент к API. Все запросы идут на относительный путь /api/... —
// в разработке его проксирует Vite, в Docker — nginx.
import type {
  Application,
  ApplicationListItem,
  DealAction,
  Farm,
  FieldCheck,
  GeoPolygon,
  Product,
  Portfolio,
  PublicConfig,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public reasons: string[] = [],
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    // FastAPI кладёт ошибку в поле detail: это либо строка, либо {message, reasons},
    // либо массив ошибок валидации Pydantic.
    let message = `Ошибка ${res.status}`;
    let reasons: string[] = [];
    try {
      const body = await res.json();
      const detail = body?.detail;
      if (typeof detail === "string") message = detail;
      else if (detail?.message) {
        message = detail.message;
        reasons = detail.reasons ?? [];
      } else if (Array.isArray(detail)) {
        message = "Проверьте заполнение формы";
        reasons = detail.map((d: { msg: string }) => d.msg);
      }
    } catch {
      /* тело ответа не JSON — оставляем общее сообщение */
    }
    throw new ApiError(message, res.status, reasons);
  }
  return res.json() as Promise<T>;
}

export const api = {
  config: () => request<PublicConfig>("/api/config"),

  verifyBin: (bin: string) =>
    request<Farm>("/api/farms/verify", { method: "POST", body: JSON.stringify({ bin }) }),

  products: () => request<Product[]>("/api/products"),

  // Проверка контура до отправки: площадь по версии сервера + пересечения с чужими полями
  checkField: (geometry: GeoPolygon, bin?: string) =>
    request<FieldCheck>("/api/fields/check", { method: "POST", body: JSON.stringify({ geometry, bin }) }),

  createApplication: (payload: {
    bin: string;
    field: { geometry: GeoPolygon; crop: string; cadastral_number?: string };
    items: { product_id: number; quantity: number }[];
  }) =>
    request<{ id: string; status: string }>("/api/applications", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  application: (id: string) => request<Application>(`/api/applications/${id}`),

  analyst: {
    list: (token: string, status?: string) =>
      request<ApplicationListItem[]>(
        `/api/analyst/applications${status ? `?status=${status}` : ""}`,
        { headers: { "X-Analyst-Token": token } },
      ),
    get: (token: string, id: string) =>
      request<Application>(`/api/analyst/applications/${id}`, {
        headers: { "X-Analyst-Token": token },
      }),
    decide: (
      token: string,
      id: string,
      body: { action: "approve" | "reject"; approved_amount?: number; comment?: string },
    ) =>
      request<Application>(`/api/analyst/applications/${id}/decision`, {
        method: "POST",
        headers: { "X-Analyst-Token": token },
        body: JSON.stringify(body),
      }),
    retry: (token: string, id: string) =>
      request<Application>(`/api/analyst/applications/${id}/retry`, {
        method: "POST",
        headers: { "X-Analyst-Token": token },
      }),
    portfolio: (token: string) =>
      request<Portfolio>("/api/analyst/portfolio", { headers: { "X-Analyst-Token": token } }),
    dealAction: (token: string, id: string, action: DealAction, amount?: number) =>
      request<Application>(`/api/analyst/deals/${id}/action`, {
        method: "POST",
        headers: { "X-Analyst-Token": token },
        body: JSON.stringify({ action, amount }),
      }),
    refreshMonitoring: (token: string, id: string) =>
      request<Application>(`/api/analyst/deals/${id}/monitoring`, {
        method: "POST",
        headers: { "X-Analyst-Token": token },
      }),
  },
};
