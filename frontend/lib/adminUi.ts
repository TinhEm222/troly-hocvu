export interface ReindexStatusView {
  running: boolean;
  last_error?: string | null;
}

export const REINDEX_MAX_WAIT_MS = 5 * 60 * 1000;

export function isReindexFinished(status: ReindexStatusView): boolean {
  return !status.running;
}

export function getReindexStatusMessage(status: ReindexStatusView): string {
  if (status.last_error) return `Re-index thất bại: ${status.last_error}`;
  return 'Đã re-index xong.';
}

export function shouldStopReindexPolling(
  startedAt: number,
  now: number,
  maxWaitMs: number = REINDEX_MAX_WAIT_MS,
): boolean {
  return now - startedAt >= maxWaitMs;
}

export async function uploadFilesSequentially<T>(
  files: File[],
  upload: (file: File, index: number) => Promise<T>,
): Promise<{
  uploaded: T[];
  failed: Array<{ file: File; error: unknown }>;
}> {
  const uploaded: T[] = [];
  const failed: Array<{ file: File; error: unknown }> = [];

  for (const [index, file] of files.entries()) {
    try {
      uploaded.push(await upload(file, index));
    } catch (error) {
      failed.push({ file, error });
    }
  }

  return { uploaded, failed };
}
