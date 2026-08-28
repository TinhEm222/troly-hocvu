export type StreamStageId = 'retrieving' | 'reranking' | 'generating';
export type StreamStageState = 'pending' | 'active' | 'done';

export interface StreamStageDefinition {
  id: StreamStageId;
  label: string;
}

export interface StreamStageView extends StreamStageDefinition {
  state: StreamStageState;
}

export const STREAM_STAGES: StreamStageDefinition[] = [
  { id: 'retrieving', label: 'Tìm tài liệu liên quan' },
  { id: 'reranking', label: 'Kiểm tra độ phù hợp' },
  { id: 'generating', label: 'Soạn câu trả lời' },
];

export function buildStageViews(activeStage: StreamStageId | null): StreamStageView[] {
  const activeIndex = activeStage === null
    ? -1
    : STREAM_STAGES.findIndex((stage) => stage.id === activeStage);

  return STREAM_STAGES.map((stage, index) => ({
    ...stage,
    state: index < activeIndex ? 'done' : index === activeIndex ? 'active' : 'pending',
  }));
}
