import {
  type SubmitEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import {
  deleteConversation,
  getConversations,
  getMessages,
  getRoles,
  getUsers,
  renameConversation,
  sendMessage,
  uploadDocument,
} from "./api";

import type {
  ChatMessage,
  Conversation,
  DemoUser,
} from "./types";

import "./index.css";


function App() {
  // ==========================================================
  // DATA STATE
  // ==========================================================

  const [users, setUsers] = useState<DemoUser[]>([]);
  const [roles, setRoles] = useState<string[]>([]);

  const [selectedUser, setSelectedUser] =
    useState<DemoUser | null>(null);

  const [conversations, setConversations] =
    useState<Conversation[]>([]);

  const [activeThreadId, setActiveThreadId] =
    useState<string | null>(null);

  const [messages, setMessages] =
    useState<ChatMessage[]>([]);


  // ==========================================================
  // UI STATE
  // ==========================================================

  const [input, setInput] = useState("");

  const [loadingUsers, setLoadingUsers] =
    useState(true);

  const [loadingChat, setLoadingChat] =
    useState(false);

  const [loadingMessages, setLoadingMessages] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);


  // ==========================================================
  // FILE UPLOAD STATE
  // ==========================================================

  const [selectedFile, setSelectedFile] =
    useState<File | null>(null);

  const [allowedRoles, setAllowedRoles] =
    useState<string[]>(["admin"]);

  const [uploading, setUploading] =
    useState(false);


  // ==========================================================
  // CHAT SCROLL
  // ==========================================================

  const messagesEndRef =
    useRef<HTMLDivElement>(null);


  // ==========================================================
  // LOAD USERS
  // ==========================================================

  useEffect(() => {
    async function loadInitialData() {
      try {
        setLoadingUsers(true);
        setError(null);

        const [usersData, rolesData] =
          await Promise.all([
            getUsers(),
            getRoles(),
          ]);

        setUsers(usersData);
        setRoles(rolesData);

        if (usersData.length > 0) {
          setSelectedUser(usersData[0]);
        }

      } catch (error) {
        setError(
          error instanceof Error
            ? error.message
            : "Failed to load users"
        );
      } finally {
        setLoadingUsers(false);
      }
    }

    loadInitialData();
  }, []);


  // ==========================================================
  // LOAD CONVERSATIONS WHEN USER CHANGES
  // ==========================================================

  useEffect(() => {
    if (!selectedUser) {
      return;
    }

    loadConversations();

    setActiveThreadId(null);
    setMessages([]);

  }, [selectedUser?.email]);


  // ==========================================================
  // AUTO SCROLL
  // ==========================================================

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, loadingChat]);


  // ==========================================================
  // LOAD CONVERSATIONS
  // ==========================================================

  async function loadConversations() {
    if (!selectedUser) {
      return;
    }

    try {
      const data = await getConversations(
        selectedUser.workspace_id,
        selectedUser.email
      );

      setConversations(data);

    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Failed to load conversations"
      );
    }
  }


  // ==========================================================
  // USER CHANGE
  // ==========================================================

  function handleUserChange(
    event: React.ChangeEvent<HTMLSelectElement>
  ) {
    const user = users.find(
      (item) =>
        item.email === event.target.value
    );

    if (!user) {
      return;
    }

    setSelectedUser(user);

    setActiveThreadId(null);
    setMessages([]);
    setError(null);
  }


  // ==========================================================
  // NEW CHAT
  // ==========================================================

  function handleNewChat() {
    setActiveThreadId(null);
    setMessages([]);
    setInput("");
    setError(null);
  }


  // ==========================================================
  // OPEN CONVERSATION
  // ==========================================================

  async function handleConversationClick(
    threadId: string
  ) {
    if (!selectedUser) {
      return;
    }

    try {
      setLoadingMessages(true);
      setError(null);

      const conversationMessages =
        await getMessages(
          threadId,
          selectedUser.workspace_id,
          selectedUser.email
        );

      setActiveThreadId(threadId);

      setMessages(conversationMessages);

    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Failed to load conversation"
      );
    } finally {
      setLoadingMessages(false);
    }
  }


  // ==========================================================
  // SEND MESSAGE
  // ==========================================================

  async function handleSubmit(
    event: SubmitEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    if (
      !input.trim() ||
      !selectedUser ||
      loadingChat
    ) {
      return;
    }

    const userMessage = input.trim();

    setInput("");
    setError(null);

    const temporaryUserMessage: ChatMessage = {
      role: "user",
      content: userMessage,
    };

    setMessages((previous) => [
      ...previous,
      temporaryUserMessage,
    ]);

    try {
      setLoadingChat(true);

      const response =
        await sendMessage(
          userMessage,
          selectedUser.email,
          selectedUser.workspace_id,
          activeThreadId
        );

      const assistantMessage: ChatMessage = {
        role: "assistant",
        content: response.response,
        metadata: {
          confidence: response.confidence,
          citations: response.citations,
          abstained: response.abstained,
          model_used: response.model_used,
        },
      };

      setMessages((previous) => [
        ...previous,
        assistantMessage,
      ]);

      setActiveThreadId(
        response.thread_id
      );

      await loadConversations();

    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Chat request failed"
      );
    } finally {
      setLoadingChat(false);
    }
  }


  // ==========================================================
  // ENTER TO SEND
  // ==========================================================

  function handleInputKeyDown(
    event: KeyboardEvent<HTMLTextAreaElement>
  ) {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      event.preventDefault();

      const form =
        event.currentTarget.form;

      form?.requestSubmit();
    }
  }


  // ==========================================================
  // RENAME CONVERSATION
  // ==========================================================

  async function handleRename(
    conversation: Conversation
  ) {
    if (!selectedUser) {
      return;
    }

    const title = window.prompt(
      "Conversation title",
      conversation.title
    );

    if (
      !title ||
      title.trim() === conversation.title
    ) {
      return;
    }

    try {
      await renameConversation(
        conversation.id,
        selectedUser.email,
        title.trim()
      );

      await loadConversations();

    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Failed to rename conversation"
      );
    }
  }


  // ==========================================================
  // DELETE CONVERSATION
  // ==========================================================

  async function handleDelete(
    conversation: Conversation
  ) {
    if (!selectedUser) {
      return;
    }

    const confirmed =
      window.confirm(
        "Delete this conversation?"
      );

    if (!confirmed) {
      return;
    }

    try {
      await deleteConversation(
        conversation.id,
        selectedUser.email
      );

      if (
        activeThreadId === conversation.id
      ) {
        handleNewChat();
      }

      await loadConversations();

    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Failed to delete conversation"
      );
    }
  }


  // ==========================================================
  // ROLE TOGGLE FOR DOCUMENT
  // ==========================================================

  function toggleAllowedRole(
    role: string
  ) {
    setAllowedRoles((previous) => {
      if (previous.includes(role)) {
        return previous.filter(
          (item) => item !== role
        );
      }

      return [
        ...previous,
        role,
      ];
    });
  }


  // ==========================================================
  // FILE UPLOAD
  // ==========================================================

  async function handleUpload() {
    if (
      !selectedUser ||
      !selectedFile ||
      allowedRoles.length === 0
    ) {
      return;
    }

    try {
      setUploading(true);
      setError(null);

      const result =
        await uploadDocument(
          selectedFile,
          selectedUser.workspace_id,
          selectedUser.email,
          allowedRoles
        );

      alert(
        `Document ingested successfully.\n\n` +
        `File: ${result.filename}\n` +
        `Chunks stored: ${result.chunks_stored}`
      );

      setSelectedFile(null);

    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Document upload failed"
      );
    } finally {
      setUploading(false);
    }
  }


  // ==========================================================
  // GET ACTIVE TITLE
  // ==========================================================

  const activeConversation =
    conversations.find(
      (conversation) =>
        conversation.id === activeThreadId
    );


  // ==========================================================
  // LOADING
  // ==========================================================

  if (loadingUsers) {
    return (
      <div className="loading-page">
        Loading InquireAI...
      </div>
    );
  }


  // ==========================================================
  // MAIN UI
  // ==========================================================

  return (
    <div className="app">

      {/* ================================================== */}
      {/* SIDEBAR */}
      {/* ================================================== */}

      <aside className="sidebar">

        <div className="sidebar-header">
          <h1>InquireAI</h1>
          <p>
            Enterprise Knowledge Assistant
          </p>
        </div>


        <div className="sidebar-section">

          <label>
            User
          </label>

          <select
            value={
              selectedUser?.email || ""
            }
            onChange={handleUserChange}
          >
            {users.map((user) => (
              <option
                key={user.id}
                value={user.email}
              >
                {user.display_name}
              </option>
            ))}
          </select>

        </div>


        <div className="sidebar-section">

          <label>
            Role
          </label>

          <div className="readonly-field">
            {selectedUser?.role}
          </div>

        </div>


        <div className="workspace">

          <span>
            Workspace
          </span>

          <code>
            {selectedUser?.workspace_id}
          </code>

        </div>


        <button
          className="new-chat-button"
          onClick={handleNewChat}
        >
          New Chat
        </button>


        {/* ================================================= */}
        {/* CONVERSATIONS */}
        {/* ================================================= */}

        <div className="conversations-header">

          <span>
            Conversations
          </span>

          <button
            className="refresh-button"
            onClick={loadConversations}
          >
            Refresh
          </button>

        </div>


        <div className="conversation-list">

          {conversations.length === 0 && (
            <div className="empty-conversations">
              No conversations
            </div>
          )}

          {conversations.map(
            (conversation) => (

              <div
                key={conversation.id}
                className={
                  "conversation-item " +
                  (
                    activeThreadId ===
                    conversation.id
                      ? "active"
                      : ""
                  )
                }
              >

                <button
                  className="conversation-title"
                  onClick={() =>
                    handleConversationClick(
                      conversation.id
                    )
                  }
                >
                  {conversation.title}
                </button>


                <div className="conversation-actions">

                  <button
                    onClick={() =>
                      handleRename(
                        conversation
                      )
                    }
                  >
                    Rename
                  </button>

                  <button
                    onClick={() =>
                      handleDelete(
                        conversation
                      )
                    }
                  >
                    Delete
                  </button>

                </div>

              </div>

            )
          )}

        </div>

      </aside>


      {/* ================================================== */}
      {/* MAIN */}
      {/* ================================================== */}

      <main className="main">

        {/* =============================================== */}
        {/* HEADER */}
        {/* =============================================== */}

        <header className="main-header">

          <div>

            <h2>
              {activeConversation
                ? activeConversation.title
                : "New Conversation"}
            </h2>

            <p>
              {selectedUser?.display_name}
              {" · "}
              {selectedUser?.role}
            </p>

          </div>

        </header>


        {/* =============================================== */}
        {/* ADMIN UPLOAD */}
        {/* =============================================== */}

        {selectedUser?.role === "admin" && (

          <section className="upload-panel">

            <div className="upload-header">

              <div>

                <h3>
                  Document Ingestion
                </h3>

                <p>
                  Upload documents to the
                  workspace knowledge base.
                </p>

              </div>

            </div>


            <input
              type="file"
              onChange={(event) => {
                setSelectedFile(
                  event.target.files?.[0] ||
                  null
                );
              }}
            />


            <div className="roles-section">

              <span>
                Allowed roles
              </span>

              <div className="role-options">

                {roles.map((role) => (

                  <label
                    key={role}
                    className="role-checkbox"
                  >

                    <input
                      type="checkbox"
                      checked={
                        allowedRoles.includes(
                          role
                        )
                      }
                      onChange={() =>
                        toggleAllowedRole(
                          role
                        )
                      }
                    />

                    {role}

                  </label>

                ))}

              </div>

            </div>


            <button
              className="upload-button"
              onClick={handleUpload}
              disabled={
                !selectedFile ||
                uploading ||
                allowedRoles.length === 0
              }
            >

              {uploading
                ? "Ingesting..."
                : "Ingest Document"}

            </button>

          </section>

        )}


        {/* =============================================== */}
        {/* ERROR */}
        {/* =============================================== */}

        {error && (

          <div className="error">
            {error}
          </div>

        )}


        {/* =============================================== */}
        {/* MESSAGES */}
        {/* =============================================== */}

        <section className="messages">

          {loadingMessages && (
            <div className="status">
              Loading conversation...
            </div>
          )}


          {!loadingMessages &&
            messages.length === 0 && (

              <div className="empty-chat">

                <h3>
                  How can I help?
                </h3>

                <p>
                  Ask questions about documents
                  available in your workspace.
                </p>

              </div>

            )}


          {messages.map(
            (message, index) => (

              <Message
                key={index}
                message={message}
              />

            )
          )}


          {loadingChat && (

            <div className="message assistant-message">

              <div className="message-label">
                InquireAI
              </div>

              <div className="typing">
                Thinking...
              </div>

            </div>

          )}


          <div
            ref={messagesEndRef}
          />

        </section>


        {/* =============================================== */}
        {/* INPUT */}
        {/* =============================================== */}

        <form
          className="chat-input-container"
          onSubmit={handleSubmit}
        >

          <textarea
            value={input}
            onChange={(event) =>
              setInput(
                event.target.value
              )
            }
            onKeyDown={handleInputKeyDown}
            placeholder="Ask a question..."
            disabled={loadingChat}
            rows={1}
          />

          <button
            type="submit"
            disabled={
              loadingChat ||
              !input.trim()
            }
          >
            Send
          </button>

        </form>

      </main>

    </div>
  );
}


// ============================================================
// MESSAGE COMPONENT
// ============================================================

function Message({
  message,
}: {
  message: ChatMessage;
}) {
  const isUser =
    message.role === "user";

  const metadata =
    message.metadata;

  const citations =
    metadata?.citations || [];


  return (
    <div
      className={
        "message " +
        (
          isUser
            ? "user-message"
            : "assistant-message"
        )
      }
    >

      <div className="message-label">

        {isUser
          ? "You"
          : "InquireAI"}

      </div>


      <div className="message-content">
        {message.content}
      </div>


      {!isUser && metadata && (

        <div className="message-details">

          {metadata.confidence !== null &&
            metadata.confidence !== undefined && (

              <span>
                Confidence:{" "}
                {Number(
                  metadata.confidence
                ).toFixed(2)}
              </span>

            )}


          {metadata.model_used && (

            <span>
              Model:{" "}
              {metadata.model_used}
            </span>

          )}

        </div>

      )}


      {!isUser &&
        citations.length > 0 && (

          <div className="citations">

            <div className="citations-title">
              Sources
            </div>


            {citations.map(
              (citation, index) => {

                const source =
                  citation.filename ||
                  citation.source ||
                  citation.document_name ||
                  "Document";

                const page =
                  citation.page_number ||
                  citation.page;


                return (
                  <div
                    key={index}
                    className="citation"
                  >

                    <span>
                      {source}
                    </span>

                    {page && (
                      <span>
                        Page {page}
                      </span>
                    )}

                  </div>
                );
              }
            )}

          </div>

        )}

    </div>
  );
}


export default App;