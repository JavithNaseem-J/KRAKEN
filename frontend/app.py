import os
import uuid

import httpx
import streamlit as st

st.set_page_config(page_title="AKEA Chat", page_icon="🤖", layout="centered")

st.title("🤖 AKEA Helpdesk Agent")
st.markdown("Interact with the Autonomous Knowledge Execution Agent.")

# Sidebar Configuration
with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input("Gateway API Key", value="dev-key-alice", type="password")
    gateway_url = st.text_input(
        "Gateway URL", value=os.getenv("GATEWAY_URL", "http://localhost:8000")
    )

    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())

    st.text_input("Session ID", value=st.session_state.session_id, disabled=True)
    if st.button("New Session"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "metadata" in message:
            with st.expander("Agent Reasoning & Metadata"):
                st.json(message["metadata"])
        if "approval_id" in message:
            st.warning(
                f"⚠️ Action Requires Approval. [Click here to review](http://localhost:8004/approve/{message['approval_id']})"
            )

# React to user input
if prompt := st.chat_input("How can I help you today?"):
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"), st.spinner("Agent is thinking..."):
            try:
                response = httpx.post(
                    f"{gateway_url.rstrip('/')}/v1/run",
                    headers={"X-API-Key": api_key, "Content-Type": "application/json"},
                    json={"message": prompt, "session_id": st.session_state.session_id},
                    timeout=120.0,
                )

                if response.status_code == 200:
                    data = response.json()

                    if data.get("status") == "pending_approval":
                        st.markdown(
                            "Your request triggered a CRITICAL action that requires human approval."
                        )
                        approval_id = data.get("approval_id")
                        st.warning(
                            f"⚠️ [Review and Approve Action](http://localhost:8004/approve/{approval_id})"
                        )
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": "Your request triggered a CRITICAL action that requires human approval.",
                                "approval_id": approval_id,
                            }
                        )
                    else:
                        answer = data.get("answer", "No answer provided.")
                        st.markdown(answer)

                        metadata = {
                            "Reasoning": data.get("reasoning", ""),
                            "Action Taken": data.get("action_taken", ""),
                            "Action Result": data.get("action_result", {}),
                            "Sources": data.get("sources", []),
                        }

                        with st.expander("Agent Reasoning & Metadata"):
                            st.json(metadata)

                        st.session_state.messages.append(
                            {"role": "assistant", "content": answer, "metadata": metadata}
                        )
                else:
                    st.error(f"Error {response.status_code}: {response.text}")

            except Exception as e:
                st.error(f"Failed to connect to gateway: {e}")
