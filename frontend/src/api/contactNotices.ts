// 联络事项 API，与页面共享明确的接收范围和状态类型。
import { http, unwrap } from "./http";
import type { ApiResponse } from "../types/api";

export interface Notice {
  source: 'store' | 'headquarters';
  store_id: number | null;
  target_store_ids: number[];
  can_view_recipients: boolean;
  id: number;
  title: string;
  content: string;
  priority: string;
  target_type: string;
  department_id: number | null;
  department_name: string | null;
  publisher_id: number;
  publisher_name: string;
  starts_at: string;
  deadline_at: string | null;
  close_on_all_confirmed: boolean;
  status: string;
  closed_at: string | null;
  close_reason: string | null;
  version: number;
  created_at: string;
  read_at: string | null;
  confirmed_at: string | null;
  recipient_count: number;
  confirmed_count: number;
  can_manage: boolean;
  can_confirm: boolean;
  employee_ids?: number[];
  recipients?: {
    store_id: number | null;
    employee_id: number;
    name: string;
    department_name: string | null;
    confirmed_at: string | null;
    light: string;
  }[];
}
export interface NoticePayload {
  store_ids?: number[];
  title: string;
  content: string;
  priority: string;
  target_type: string;
  department_id: number | null;
  employee_ids: number[];
  starts_at: string | null;
  deadline_at: string | null;
  close_on_all_confirmed: boolean;
  expected_version?: number;
  reason?: string | null;
}
export async function getNotices(params: Record<string, unknown>) {
  return unwrap(
    (
      await http.get<
        ApiResponse<{ items: Notice[]; total: number; total_pages: number }>
      >("/contact-notices/list", { params })
    ).data,
  );
}
export async function getNotice(id: number) {
  return unwrap(
    (await http.get<ApiResponse<Notice>>(`/contact-notices/${id}`)).data,
  );
}
export async function getNoticeAudience() {
  return unwrap(
    (
      await http.get<
        ApiResponse<{
          employees: {
            id: number;
            name: string;
            department_id: number | null;
            store_id: number | null;
          }[];
          departments: { id: number; name: string }[];
        }>
      >("/contact-notices/audience")
    ).data,
  );
}
export async function saveNotice(payload: NoticePayload, id?: number) {
  const response = id
    ? await http.put<ApiResponse<Notice>>(`/contact-notices/${id}`, payload)
    : await http.post<ApiResponse<Notice>>("/contact-notices", payload);
  return unwrap(response.data);
}
export async function noticeAction(notice: Notice, action: string) {
  const path = `/contact-notices/${notice.id}`;
  const response =
    action === "delete"
      ? await http.delete(path, { data: { expected_version: notice.version } })
      : await http.post(`${path}/${action}`, {
          expected_version: notice.version,
        });
  return unwrap(response.data) as Notice;
}
export async function getNoticeSummary() {
  return unwrap(
    (
      await http.get<ApiResponse<{ unread: number; pending: number }>>(
        "/contact-notices/summary",
      )
    ).data,
  );
}
