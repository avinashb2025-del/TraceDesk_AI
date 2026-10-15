
import streamlit as st
from agent import ask_agent

st.set_page_config(
    page_title="TraceDesk AI",
    page_icon="🔎",
    layout="wide"
)

st.title("🔎 TraceDesk AI")
st.caption(
    "Graph-powered company knowledge and incident investigation"
)

with st.sidebar:
    st.header("About TraceDesk")
    st.write(
        "TraceDesk connects services, owners, incidents, "
        "and solutions using FalkorDB."
    )

    st.divider()

    st.subheader("Try asking")
    st.write("• Who owns the Payments API?")
    st.write("• What incident affected the Payments API?")
    st.write("• What is the solution for the Payments API?")

    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

question = st.chat_input("Ask about a service or incident...")

if question:
    st.session_state.messages.append(
        {"role": "user", "content": question}
    )

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Investigating the knowledge graph..."):
            try:
                answer = ask_agent(question)
            except Exception as error:
                answer = (
                    "I couldn't query FalkorDB. "
                    "Check that Docker and FalkorDB are running. "
                    f"Details: {error}"
                )

            st.markdown(answer)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer}
    )
