import axios from "axios";

import type {
  ChatMessage,
  ChatResponse,
  Conversation,
  DemoUser,
  UploadResponse,
} from "./types";


const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000";


const api = axios.create({
  baseURL: API_BASE_URL,
});


function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    return (
      error.response?.data?.detail ||
      error.message ||
      "Request failed"
    );
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected error occurred";
}


// ============================================================
// USERS
// ============================================================

export async function getUsers(): Promise<DemoUser[]> {
  try {
    const response = await api.get<DemoUser[]>(
      "/api/users/users"
    );

    return response.data;
  } catch (error) {
    throw new Error(getErrorMessage(error));
  }
}


export async function getRoles(): Promise<string[]> {
  try {
    const response = await api.get<string[]>(
      "/api/users/roles"
    );

    return response.data;
  } catch (error) {
    throw new Error(getErrorMessage(error));
  }
}


// ============================================================
// CONVERSATIONS
// ============================================================

export async function getConversations(
  workspaceId: string,
  userEmail: string
): Promise<Conversation[]> {
  try {
    const response = await api.get<Conversation[]>(
      "/api/conversations",
      {
        params: {
          workspace_id: workspaceId,
          user_email: userEmail,
        },
      }
    );

    return response.data;
  } catch (error) {
    throw new Error(getErrorMessage(error));
  }
}


export async function getMessages(
  threadId: string,
  workspaceId: string,
  userEmail: string
): Promise<ChatMessage[]> {
  try {
    const response = await api.get<ChatMessage[]>(
      `/api/conversations/${threadId}/messages`,
      {
        params: {
          workspace_id: workspaceId,
          user_email: userEmail,
        },
      }
    );

    return response.data;
  } catch (error) {
    throw new Error(getErrorMessage(error));
  }
}


export async function renameConversation(
  threadId: string,
  userEmail: string,
  title: string
): Promise<void> {
  try {
    await api.patch(
      `/api/conversations/${threadId}`,
      {
        title,
      },
      {
        params: {
          user_email: userEmail,
        },
      }
    );
  } catch (error) {
    throw new Error(getErrorMessage(error));
  }
}


export async function deleteConversation(
  threadId: string,
  userEmail: string
): Promise<void> {
  try {
    await api.delete(
      `/api/conversations/${threadId}`,
      {
        params: {
          user_email: userEmail,
        },
      }
    );
  } catch (error) {
    throw new Error(getErrorMessage(error));
  }
}


// ============================================================
// CHAT
// ============================================================

export async function sendMessage(
  message: string,
  userEmail: string,
  workspaceId: string,
  threadId: string | null
): Promise<ChatResponse> {
  try {
    const response = await api.post<ChatResponse>(
      "/api/chat/",
      {
        message,
        user_email: userEmail,
        workspace_id: workspaceId,
        thread_id: threadId,
      },
      {
        timeout: 300000,
      }
    );

    return response.data;
  } catch (error) {
    throw new Error(getErrorMessage(error));
  }
}


// ============================================================
// FILE UPLOAD
// ============================================================

export async function uploadDocument(
  file: File,
  workspaceId: string,
  userEmail: string,
  allowedRoles: string[]
): Promise<UploadResponse> {
  const formData = new FormData();

  formData.append("file", file);
  formData.append("workspace_id", workspaceId);
  formData.append("user_email", userEmail);

  formData.append(
    "allowed_role_ids",
    allowedRoles.join(",")
  );

  try {
    const response = await api.post<UploadResponse>(
      "/files",
      formData,
      {
        timeout: 600000,
      }
    );

    return response.data;
  } catch (error) {
    throw new Error(getErrorMessage(error));
  }
}