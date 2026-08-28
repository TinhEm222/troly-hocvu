export interface StreamBuffer {
  push: (chunk: string) => void;
  flush: () => void;
  dispose: () => void;
}

type FrameHandle = {
  kind: 'raf' | 'timeout';
  id: number;
};

// Gom token trong một frame trước khi cập nhật React state, tránh re-render theo từng token.
export function createStreamBuffer(commit: (chunk: string) => void): StreamBuffer {
  let pending = '';
  let handle: FrameHandle | null = null;

  const schedule = (callback: () => void): FrameHandle => {
    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      return { kind: 'raf', id: window.requestAnimationFrame(callback) };
    }
    return { kind: 'timeout', id: globalThis.setTimeout(callback, 50) as unknown as number };
  };

  const cancel = (scheduled: FrameHandle) => {
    if (scheduled.kind === 'raf') window.cancelAnimationFrame(scheduled.id);
    else globalThis.clearTimeout(scheduled.id);
  };

  const flush = () => {
    handle = null;
    if (!pending) return;
    const chunk = pending;
    pending = '';
    commit(chunk);
  };

  const push = (chunk: string) => {
    pending += chunk;
    if (handle === null) handle = schedule(flush);
  };

  const dispose = () => {
    if (handle !== null) cancel(handle);
    handle = null;
    pending = '';
  };

  return { push, flush, dispose };
}
