export interface DemoUser {
  id: string;
  email: string;
  display_name: string;
  workspace_id: string;
  role: string;
}

export interface Conversation {
  id: string;
  title: string;
}

export interface Citation {
  chunk_id: string;
  file_id: string;
  filename?: string | null;
  section_title?: string | null;
  page_start?: number | null;
  page_end?: number | null;
}

export interface MessageMetadata {
  citations?: Citation[];
  confidence?: number | null;
  abstained?: boolean;
  model_used?: string | null;
}

export interface ChatMessage {
  id?: string;
  role: "user" | "assistant";
  content: string;
  metadata?: MessageMetadata | null;
}

export interface ChatResponse {
  thread_id: string;
  response: string;
  source: string;
  citations: Citation[];
  confidence: number | null;
  abstained: boolean;
  model_used: string | null;
  processing_time: number;
}

export interface UploadResponse {
  file_id: string;
  filename: string;
  status: string;
  chunks_stored: number;
}