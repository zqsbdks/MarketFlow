import type { PageResult } from '../types/api'

/** Load complete selection options; table rows use server pagination separately. */
export async function loadAllPages<T>(fetchPage: (page: number) => Promise<PageResult<T>>) {
  const first = await fetchPage(1)
  const items = [...first.items]
  for (let page = 2; page <= first.total_pages; page++) {
    items.push(...(await fetchPage(page)).items)
  }
  return items
}
