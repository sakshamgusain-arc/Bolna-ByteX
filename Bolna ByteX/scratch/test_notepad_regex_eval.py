import re

commands = [
    "Open Notepad and write Hello I am Negasaurus.",
    "Open Notepad and write. Hello I am Negasaurus.",
    "Open Notepad and type Hello I am Negasaurus.",
    "Write Hello I am Negasaurus in Notepad.",
    "Open Notepad and write: Hello I am Negasaurus.",
    "Open Notepad and type. Hello I am Negasaurus.",
    "Write. Hello I am Negasaurus in Notepad.",
    "Open Notepad. Write Hello I am Negasaurus."
]

def test_parse(cmd):
    print(f"\nTesting: '{cmd}'")
    clean_goal = cmd.strip()
    goal_lower = clean_goal.lower()

    # 1. Atomic App Typing
    m_app_type = re.match(
        r"^(?:write|type|enter|input)[.:,]?\s+(.+?)\s+(?:in|into|inside|on)\s+(?:the\s+)?([a-zA-Z0-9_\-]+(?:\s+[a-zA-Z0-9_\-]+)?)[.!?]*$",
        clean_goal,
        flags=re.IGNORECASE
    )
    if m_app_type:
        raw_text = m_app_type.group(1).strip().strip('"\'')
        raw_text = re.sub(r"^[.:,\s]+", "", raw_text)
        raw_target = m_app_type.group(2).strip().strip('"\'')
        print(f"  [ATOMIC] App: '{raw_target}', Text: '{raw_text}'")
        return {"step1_app": raw_target, "step2_text": raw_text}

    # 2. Compound Decomposition
    action_verbs = r"(?:open|launch|start|run|write|type|enter|input|close|quit|save|search|click|press)"
    parts = re.split(
        rf',\s*(?:and\s+|then\s+)?|\s+and\s+then\s+|\s+then\s+|\s+and\s+(?!(?:run|execute)\b)|\.\s+(?={action_verbs}\b)|;\s*',
        clean_goal,
        flags=re.IGNORECASE
    )
    parts = [p.strip() for p in parts if p.strip()]
    print(f"  [PARTS]: {parts}")

    seq_steps = []
    for idx, clause in enumerate(parts, 1):
        m_open = re.match(r"^(?:open|launch|start|run)\s+(.+?)[.!?]*$", clause, flags=re.IGNORECASE)
        if m_open:
            app_name = m_open.group(1).strip().rstrip('.!?')
            seq_steps.append({"skill": "open_application", "app": app_name})
            continue

        m_type = re.match(
            r"^(?:type|write|enter|input)[.:,]?\s+(.+?)(?:\s+(?:in|into|on)\s+(?:the\s+)?([a-zA-Z0-9_\-]+(?:\s+[a-zA-Z0-9_\-]+)?))?$",
            clause,
            flags=re.IGNORECASE
        )
        if m_type:
            text_val = m_type.group(1).strip().strip('"\'')
            text_val = re.sub(r"^[.:,\s]+", "", text_val)
            target_val = m_type.group(2).strip().strip('"\'') if m_type.group(2) else None
            if not target_val:
                for s in seq_steps:
                    if s["skill"] == "open_application" and s.get("app"):
                        target_val = s["app"]
                        break
            seq_steps.append({"skill": "screen_vision", "action": "visual_type", "text": text_val, "target": target_val})
            continue

    print(f"  [STEPS]: {seq_steps}")
    assert len(seq_steps) == 2, f"Expected 2 steps, got {len(seq_steps)}"
    assert seq_steps[0]["skill"] == "open_application" and seq_steps[0]["app"].lower() == "notepad"
    assert seq_steps[1]["skill"] == "screen_vision" and "Hello I am Negasaurus" in seq_steps[1]["text"]
    assert seq_steps[1]["target"].lower() == "notepad"
    return seq_steps

for c in commands:
    test_parse(c)
print("\nALL EVALUATION REGEX TESTS PASSED!")

