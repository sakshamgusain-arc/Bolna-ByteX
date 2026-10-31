import re

code_commands = [
    "Write a Python program that prints Hello World",
    "Write code in C++ to reverse an array",
    "Write a function in Python to calculate fibonacci",
    "Write a C++ script that prints even numbers"
]

CODE_LANG_PATTERN = r"(?:python|py|c\+\+|cpp|c|java|javascript|typescript|js|ts|rust|go|golang|c#|csharp|html|css|sql|bash|sh|ruby|php|kotlin|swift)"
CODE_NOUN_PATTERN = r"(?:program|script|solution|function|code|app|algorithm|class|method)"

for cmd in code_commands:
    clause = cmd.strip()
    is_code_gen = False
    if re.match(r"^print\s+(?:all\s+)?(?:prime\s+numbers|primes|fibonacci|even\s+numbers|odd\s+numbers)\b", clause, flags=re.IGNORECASE):
        is_code_gen = True
    elif re.match(r"^(?:code|implement)\s+(?:a\s+|an\s+)?(?:solution|algorithm|function|code|program)?\s*(?:to|for|that|which)?\s*(.+)$", clause, flags=re.IGNORECASE):
        is_code_gen = True
    elif re.match(rf"^(?:write|create|generate|build)\s+(?:a\s+|an\s+)?(?:{CODE_LANG_PATTERN}\s+)?{CODE_NOUN_PATTERN}\b", clause, flags=re.IGNORECASE):
        is_code_gen = True
    elif re.match(rf"^(?:write|create|generate|build|code)\s+(?:code\s+)?in\s+{CODE_LANG_PATTERN}\b", clause, flags=re.IGNORECASE):
        is_code_gen = True
    elif re.search(rf"\b(?:in|using|with)\s+{CODE_LANG_PATTERN}\b", clause, flags=re.IGNORECASE) and any(w in clause.lower() for w in ["write", "code", "create", "implement", "generate", "build", "reverse", "sort", "algorithm", "fibonacci", "primes", "factorial"]):
        is_code_gen = True

    print(f"'{cmd}' -> is_code_gen = {is_code_gen}")
    assert is_code_gen, f"Failed for code command: {cmd}"

print("\nALL CODE GENERATION DISAMBIGUATION TESTS PASSED!")

