from app.protocols.agent_message import ALL_AGENT_MESSAGE_TYPES


def test_all_agent_message_types_count() -> None:
    assert len(ALL_AGENT_MESSAGE_TYPES) == 13
