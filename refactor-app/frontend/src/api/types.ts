export type Row = Record<string, unknown> & { id?: string };

export type PageQuery = Record<string, string | number | boolean | undefined> & {
  page?: number;
  page_size?: number;
  sort?: string;
  q?: string;
};

export type PagedResult<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  sort: string;
};

export type OptionItem = {
  value: string;
  label: string;
  description?: string;
  status?: string;
};

export async function loadAllPages<T>(
  loader: (query: PageQuery) => Promise<PagedResult<T>>,
  query: PageQuery = {},
  pageSize = 200,
): Promise<T[]> {
  const first = await loader({ ...query, page: 1, page_size: pageSize });
  const items = [...first.items];
  const effectivePageSize = Math.max(1, Number(first.page_size || pageSize));
  const totalPages = Math.max(1, Math.ceil(Number(first.total || 0) / effectivePageSize));

  for (let page = 2; page <= totalPages; page += 1) {
    const result = await loader({ ...query, page, page_size: effectivePageSize });
    items.push(...result.items);
  }
  return items;
}

export function withQuery(path: string, params: PageQuery = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || String(value).trim() === "") return;
    query.set(key, String(value));
  });
  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
}
